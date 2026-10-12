"""Candidate feature extraction and scoring (spec sections 21-24, 39).

The invariants here are what keep SPLM from flattering itself:

* a feature with no evidence contributes exactly zero, not a neutral-looking 0.5;
* an ablated feature contributes exactly zero;
* every reported contribution sums to the adjustment actually applied;
* with every feature off, SPLM reproduces the base model exactly.

No Transformer is needed: candidates are constructed directly, so these run fast and
deterministically.
"""

from __future__ import annotations

import pytest

from splm.config import Config
from splm.model.base_llm import Candidate
from splm.model.candidate_features import (
    FEATURE_ORDER,
    CandidateFeatureExtractor,
    ScoringContext,
)
from splm.model.candidate_scorer import PhraseCandidateScorer, WeightedScorer
from splm.phrase.slot_predictor import HeuristicSlotPredictor, SlotContext


def _candidate(word: str, *, logit: float = 4.0, rank: int = 1, probability: float = 0.2):
    """Build a candidate the way the tokenizer would: leading space, decoded surface."""
    return Candidate(
        token_id=abs(hash(word)) % 50000,
        token=f"Ġ{word}",
        logit=logit,
        probability=probability,
        rank=rank,
        surface=f" {word}",
    )


@pytest.fixture(scope="module")
def context(registry, builder, sentence_for):
    """Scoring context for "John will meet Sarah in" - the spec's worked example."""
    text = "John will meet Sarah in"
    sentence = sentence_for(text)
    frame = builder.build(sentence)
    slots = HeuristicSlotPredictor(registry).predict(
        SlotContext(text=text, language="en", frame=frame, sentence=sentence)
    )
    return ScoringContext(
        text=text,
        language="en",
        frame=frame,
        slots=slots,
        trailing_word="in",
    )


@pytest.fixture(scope="module")
def extractor(registry, config):
    return CandidateFeatureExtractor(registry, config=config)


# ---------------------------------------------------------------------------
# feature extraction
# ---------------------------------------------------------------------------


def test_location_candidate_fits_the_expected_slot(extractor, context):
    features = extractor.extract(_candidate("Paris"), context, max_logit=4.0)
    assert features.word == "Paris"
    assert features.informative["semantic"]
    assert features.semantic > 0.8
    assert features.phrase_slot > 0.8
    assert features.best_slot in {"location", "destination", "source"}
    assert features.reasons


def test_adjective_is_less_compatible_not_impossible(extractor, context):
    """"in beautiful" is an incomplete phrase, not an illegal one.

    The scorer implements no hard rules, so an adjective after a preposition must score
    *lower* than a noun while staying well above zero.
    """
    adjective = extractor.extract(_candidate("beautiful"), context, max_logit=4.0)
    noun = extractor.extract(_candidate("Paris"), context, max_logit=4.0)
    assert adjective.syntax < noun.syntax
    assert adjective.syntax > 0.0


def test_whitespace_token_yields_no_word_features(extractor, context):
    """A newline is not a capitalised proper noun.

    Byte-level BPE spells a newline "C" with a diacritic, whose first character is an
    uppercase letter. Judging tokens by their raw symbol promoted it as a name.
    """
    newline = Candidate(
        token_id=201, token="Ċ", logit=2.0, probability=0.01, rank=9, surface="\n"
    )
    features = extractor.extract(newline, context, max_logit=4.0)
    assert features.word == ""
    assert features.pos_estimate.pos is None
    assert not features.informative.get("semantic", False)
    assert features.semantic == pytest.approx(0.5)


def test_determiner_is_recognised(extractor, context):
    features = extractor.extract(_candidate("the"), context, max_logit=4.0)
    assert features.pos_estimate.pos == "DET"


def test_missing_lexicon_is_neutral_not_negative(extractor, context):
    """With no lexicon built, the lexical feature must not penalise anything."""
    features = extractor.extract(_candidate("Paris"), context, max_logit=4.0)
    assert features.lexical_status == "unknown"
    assert features.lexicon == pytest.approx(0.5)
    assert features.informative["lexicon"] is False


def test_llm_feature_is_relative_to_the_best_candidate(extractor, context):
    top = extractor.extract(_candidate("Paris", logit=6.0), context, max_logit=6.0)
    tail = extractor.extract(_candidate("Paris", logit=0.0), context, max_logit=6.0)
    assert top.llm == pytest.approx(1.0)
    assert tail.llm < top.llm


def test_feature_order_is_stable(extractor, context):
    """A trained scorer's inputs are positional; reordering would silently corrupt it."""
    features = extractor.extract(_candidate("Paris"), context, max_logit=4.0)
    vector = features.vector()
    assert len(vector) == len(FEATURE_ORDER)
    assert FEATURE_ORDER[0] == "llm"
    assert set(FEATURE_ORDER) == set(features.model_dump().keys()) & set(FEATURE_ORDER)


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------


def test_contributions_sum_to_the_adjustment(config: Config, registry, context):
    scorer = PhraseCandidateScorer.from_config(config, registry=registry)
    scored = scorer.score_candidates([_candidate("Paris")], context)[0]
    total = sum(c.contribution for c in scored.contributions)
    assert total == pytest.approx(scored.delta_logit, abs=0.01)
    assert scored.splm_logit == pytest.approx(scored.base_logit + scored.delta_logit)


def test_uninformative_feature_contributes_nothing(config, registry, context):
    scorer = PhraseCandidateScorer.from_config(config, registry=registry)
    scored = scorer.score_candidates([_candidate("Paris")], context)[0]
    for contribution in scored.contributions:
        if not contribution.informative:
            assert contribution.contribution == 0.0, (
                f"{contribution.feature} had no evidence yet moved the logit"
            )


def test_location_beats_adjective_after_a_preposition(config, registry, context):
    scorer = PhraseCandidateScorer.from_config(config, registry=registry)
    scored = scorer.score_candidates(
        [
            _candidate("Paris", logit=4.0, rank=1),
            _candidate("beautiful", logit=4.0, rank=2),
        ],
        context,
    )
    by_word = {score.word: score for score in scored}
    assert by_word["Paris"].delta_logit > by_word["beautiful"].delta_logit
    assert by_word["Paris"].splm_rank < by_word["beautiful"].splm_rank


def test_ranks_and_probabilities_are_consistent(config, registry, context):
    scorer = PhraseCandidateScorer.from_config(config, registry=registry)
    scored = scorer.score_candidates(
        [
            _candidate("Paris", logit=3.0, rank=3, probability=0.05),
            _candidate("the", logit=5.0, rank=1, probability=0.4),
            _candidate("London", logit=2.0, rank=5, probability=0.02),
        ],
        context,
    )
    assert sum(score.splm_probability for score in scored) == pytest.approx(1.0, abs=0.01)
    ordered = sorted(scored, key=lambda s: s.splm_rank)
    logits = [score.splm_logit for score in ordered]
    assert logits == sorted(logits, reverse=True)


def test_adjustment_is_capped(registry, context):
    """A confident base model must not be steamrolled by the structural layer."""
    scorer = WeightedScorer(
        {name: 100.0 for name in FEATURE_ORDER},
        neutral=0.5,
        logit_scale=10.0,
        max_logit_delta=3.0,
    )
    extractor = CandidateFeatureExtractor(registry)
    features = extractor.extract(_candidate("Paris"), context, max_logit=4.0)
    delta, _ = scorer.delta(features)
    assert abs(delta) <= 3.0


# ---------------------------------------------------------------------------
# ablation (spec section 39)
# ---------------------------------------------------------------------------


def test_all_features_off_reproduces_the_base_model(config, registry, context):
    """The central control: with everything ablated, SPLM must change nothing.

    If this fails, no comparison in the project means anything, because the SPLM arm
    would differ from the base arm even with the structural layer disabled.
    """
    ablated = config.ablation("base_only")
    scorer = PhraseCandidateScorer.from_config(ablated, registry=registry)
    candidates = [
        _candidate("Paris", logit=3.0, rank=2),
        _candidate("the", logit=5.0, rank=1),
    ]
    scored = scorer.score_candidates(candidates, context)

    for score in scored:
        assert score.delta_logit == pytest.approx(0.0)
        assert score.splm_logit == pytest.approx(score.base_logit)
        assert score.splm_rank == score.base_rank


def test_ablating_one_feature_zeroes_only_that_feature(config, registry, context):
    scorer = PhraseCandidateScorer.from_config(
        config.with_features({"semantics": False}), registry=registry
    )
    scored = scorer.score_candidates([_candidate("Paris")], context)[0]
    by_name = {c.feature: c for c in scored.contributions}
    assert by_name["semantic"].enabled is False
    assert by_name["semantic"].contribution == 0.0
    assert by_name["syntax"].enabled is True


def test_phrase_structure_ablation_changes_the_outcome(config, registry, context):
    """Turning off Phrase DNA must measurably reduce the adjustment.

    Otherwise the feature is not doing anything and the ablation ladder would be
    reporting a difference that does not exist.
    """
    full = PhraseCandidateScorer.from_config(config, registry=registry)
    without = PhraseCandidateScorer.from_config(
        config.with_features({"phrase_structure": False}), registry=registry
    )
    candidate = _candidate("Paris")
    assert full.score_candidates([candidate], context)[0].delta_logit > (
        without.score_candidates([candidate], context)[0].delta_logit
    )


def test_untrained_neural_scorer_falls_back_to_weights(config, registry, context):
    from splm.model.candidate_scorer import NeuralScorer

    backend = NeuralScorer(config.scoring_weights, checkpoint=None, features_enabled=config.features)
    assert not backend.is_trained

    extractor = CandidateFeatureExtractor(registry, config=config)
    features = extractor.extract(_candidate("Paris"), context, max_logit=4.0)
    delta, contributions = backend.delta(features)
    assert contributions
    assert delta == pytest.approx(
        sum(c.contribution for c in contributions), abs=0.01
    )


# ---------------------------------------------------------------------------
# advantage metrics
# ---------------------------------------------------------------------------


def test_semantic_focus_reports_coverage(config, registry, context):
    """The metric must say how many candidates it could actually classify."""
    from splm.model.advantage import compute_semantic_focus

    scorer = PhraseCandidateScorer.from_config(config, registry=registry)
    scored = scorer.score_candidates(
        [
            _candidate("Paris", logit=3.0, rank=2, probability=0.1),
            _candidate("London", logit=2.5, rank=3, probability=0.08),
            _candidate("the", logit=5.0, rank=1, probability=0.5),
        ],
        context,
    )
    focus = compute_semantic_focus(scored, context.slots)
    assert focus is not None
    assert focus.total == 3
    assert focus.evaluated <= focus.total
    assert 0.0 <= focus.coverage <= 1.0
    # Re-scoring should move mass toward the expected slot for this prompt.
    assert focus.splm_mass >= focus.base_mass


def test_funnel_marks_only_real_filters_as_hard(config, registry, context):
    """Re-scoring is down-ranking, not filtering, and the data model must say so."""
    from splm.model.advantage import compute_search_space

    scorer = PhraseCandidateScorer.from_config(config, registry=registry)
    scored = scorer.score_candidates([_candidate("Paris"), _candidate("the")], context)
    search = compute_search_space(scored, context.slots, vocabulary_size=50000)

    hard = [stage for stage in search.stages if stage.hard]
    soft = [stage for stage in search.stages if not stage.hard]
    assert {stage.name for stage in hard} == {"candidates retrieved", "selected"}
    assert soft, "the scoring stages must be present"
    for stage in soft:
        assert "down-rank" in stage.label or stage.label == "available"


def test_target_outcome_reports_absence_honestly(config, registry, context):
    from splm.model.advantage import compute_target_outcome

    scorer = PhraseCandidateScorer.from_config(config, registry=registry)
    scored = scorer.score_candidates([_candidate("Paris"), _candidate("the")], context)

    found = compute_target_outcome(scored, "Paris")
    assert found.found and found.base_rank is not None
    assert found.verdict in {"win", "loss", "tie"}

    missing = compute_target_outcome(scored, "Ouagadougou")
    assert not missing.found
    assert missing.verdict == "not_found"
    assert missing.rank_improvement is None
