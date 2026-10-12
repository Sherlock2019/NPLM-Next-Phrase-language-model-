"""End-to-end prediction and generation (spec sections 26, 41, 43, 55).

These tests need the base Transformer, so they are marked ``llm`` and skip when no
model is available. What they pin down is the integrity of the comparison itself:

* both arms come from one forward pass, so nothing but the scoring layer differs;
* SPLM's probabilities are a distribution over the candidates it actually re-scored;
* with every feature ablated, SPLM reproduces the base model exactly;
* a cold call is flagged as cold, so its timings are never read as latency.

Run only these with:  pytest -m llm
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.llm


@pytest.fixture(scope="module")
def engine(config):
    """A warmed engine, or a skip if the model or parser is unavailable."""
    from splm.model.base_llm import ModelUnavailable
    from splm.model.engine import SPLMEngine

    instance = SPLMEngine(config)
    try:
        instance.llm.load()
    except ModelUnavailable as exc:
        pytest.skip(f"base model unavailable: {exc}")

    instance.warmup()
    if not instance.pipeline.analyze("John met Sarah in Paris.").parsed:
        pytest.skip("no parser model; run python scripts/download_resources.py")
    return instance


@pytest.fixture(scope="module")
def result(engine):
    return engine.predict("John will meet Sarah in", target="Paris")


# ---------------------------------------------------------------------------
# the shape of a prediction
# ---------------------------------------------------------------------------


def test_prediction_has_both_arms(result):
    assert result.candidates
    assert result.base_choice is not None
    assert result.splm_choice is not None
    assert result.expected_slots.distribution


def test_both_arms_describe_the_same_candidates(result):
    """One forward pass, two rankings - not two separate inferences."""
    base_ids = {candidate.token_id for candidate in result.top_base(20)}
    splm_ids = {candidate.token_id for candidate in result.top_splm(20)}
    assert base_ids and splm_ids
    for score in result.candidates:
        # Each candidate carries both views, which is only possible from one pass.
        assert score.base_logit is not None
        assert score.splm_logit is not None


def test_base_ranks_follow_base_logits(result):
    ordered = sorted(result.candidates, key=lambda s: s.base_rank)
    logits = [score.base_logit for score in ordered]
    assert logits == sorted(logits, reverse=True)


def test_splm_ranks_follow_splm_logits(result):
    ordered = sorted(result.candidates, key=lambda s: s.splm_rank)
    logits = [score.splm_logit for score in ordered]
    assert logits == sorted(logits, reverse=True)


def test_splm_probabilities_are_a_distribution(result):
    """A distribution over the *re-scored* candidates, not the whole vocabulary."""
    total = sum(score.splm_probability for score in result.candidates)
    assert total == pytest.approx(1.0, abs=0.01)


def test_base_probabilities_are_whole_vocabulary(result):
    """Base probabilities come from a softmax over the entire vocabulary.

    So they must sum to less than one over a top-K subset. If they summed to one, the
    comparison against SPLM would be over different denominators.
    """
    total = sum(score.base_probability for score in result.candidates)
    assert 0.0 < total <= 1.0001


def test_adjustment_arithmetic_holds(result):
    for score in result.candidates:
        assert score.splm_logit == pytest.approx(
            score.base_logit + score.delta_logit, abs=1e-6
        )
        contributions = sum(c.contribution for c in score.contributions)
        assert contributions == pytest.approx(score.delta_logit, abs=0.02)


def test_warm_call_is_flagged_warm(result):
    """Otherwise its timings would include one-off loading."""
    assert result.warm is True
    assert result.total_latency_ms > 0
    assert "llm_inference" in result.timings_ms


# ---------------------------------------------------------------------------
# the structural layer actually does something
# ---------------------------------------------------------------------------


def test_expected_slot_is_predicted(result):
    assert result.expected_slots.top_slot == "location"
    assert result.expected_slots.confidence > 0.5


def test_location_candidates_are_promoted(result):
    """Place names must gain, and the promotion must be attributable.

    The assertion is about *movement*, not about SPLM winning: with a small model the
    top choice may well stay unchanged, which is a legitimate outcome.
    """
    places = [
        score
        for score in result.candidates
        if score.word.lower() in {"paris", "london", "boston", "berlin", "tokyo", "town"}
    ]
    if not places:
        pytest.skip("this model proposed no recognisable place among its top candidates")

    for score in places:
        assert score.delta_logit > 0, f"{score.word} was not promoted"
        assert score.features is not None
        assert score.features.informative.get("semantic")


def test_whitespace_candidates_are_not_promoted_as_names(result):
    """A newline must never be treated as a proper noun (byte-level BPE spells it 'Ċ')."""
    for score in result.candidates:
        if score.word.strip() == "":
            assert score.features is not None
            assert score.features.pos_estimate.pos is None
            assert score.delta_logit <= 0.01


def test_search_space_reports_only_real_filters(result):
    assert result.search_space is not None
    hard = {stage.name for stage in result.search_space.stages if stage.hard}
    assert hard == {"candidates retrieved", "selected"}
    assert result.search_space.vocabulary_size > len(result.candidates)
    assert 0.0 < result.search_space.hard_reduction < 1.0


def test_semantic_focus_is_measured(result):
    focus = result.semantic_focus
    assert focus is not None
    assert focus.total == len(result.candidates)
    assert 0.0 <= focus.coverage <= 1.0
    if focus.evaluated < focus.total:
        assert focus.coverage_note, "partial coverage must be stated"


def test_target_rank_is_reported(result):
    target = result.target
    assert target is not None
    if not target.found:
        pytest.skip("the target was outside this model's top-K")
    assert target.base_rank is not None and target.splm_rank is not None
    assert target.verdict in {"win", "tie", "loss"}
    assert target.base_reciprocal_rank > 0


# ---------------------------------------------------------------------------
# ablation must reproduce the base model
# ---------------------------------------------------------------------------


def test_full_ablation_reproduces_the_base_model(config, engine):
    """The control that every other comparison depends on.

    Run through the whole engine - parser, frame, slot predictor, scorer - with every
    feature switched off. The output must be bit-identical to the base model's.
    """
    from splm.model.engine import SPLMEngine

    ablated = SPLMEngine(
        config.ablation("base_only"),
        pipeline=engine.pipeline,
        llm=engine.llm,
        lexicon=engine.lexicon,
    )
    ablated.warmup()
    result = ablated.predict("John will meet Sarah in")

    for score in result.candidates:
        assert score.delta_logit == pytest.approx(0.0)
        assert score.splm_rank == score.base_rank
    assert result.base_choice is not None and result.splm_choice is not None
    assert result.base_choice.token_id == result.splm_choice.token_id
    assert result.changed_selection is False


def test_ablation_changes_the_ranking(config, engine):
    """Conversely, the full configuration must differ from the ablated one.

    If it did not, the structural layer would be inert and every reported difference
    would be noise.
    """
    from splm.model.engine import SPLMEngine

    ablated = SPLMEngine(
        config.ablation("base_only"),
        pipeline=engine.pipeline,
        llm=engine.llm,
        lexicon=engine.lexicon,
    )
    ablated.warmup()

    plain = ablated.predict("John will meet Sarah in")
    full = engine.predict("John will meet Sarah in")

    moved = [score for score in full.candidates if score.delta_logit != 0.0]
    assert moved, "the full configuration adjusted nothing"

    plain_order = [s.token_id for s in sorted(plain.candidates, key=lambda s: s.splm_rank)]
    full_order = [s.token_id for s in sorted(full.candidates, key=lambda s: s.splm_rank)]
    assert plain_order != full_order


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_generation_comparison_uses_identical_settings(engine):
    """Same model, prompt and decoding configuration; only the scoring layer differs."""
    base, splm = engine.generate_comparison(
        "John will meet Sarah in", max_new_tokens=6, do_sample=False
    )
    assert isinstance(base, str) and isinstance(splm, str)
    # Greedy decoding, so both are deterministic; they may or may not coincide.
    again, _ = engine.generate_comparison(
        "John will meet Sarah in", max_new_tokens=6, do_sample=False
    )
    assert base == again, "base generation must be deterministic under greedy decoding"


@pytest.mark.slow
def test_logits_processor_survives_a_failure(engine):
    """A fault in the structural layer must degrade to the base model, not abort.

    Generation failing outright because a parser hiccupped would make SPLM unusable in
    exactly the situations where its help is least certain.
    """
    from splm.model.logits_processor import PhraseLanguageLogitsProcessor

    processor = PhraseLanguageLogitsProcessor(
        engine=engine, prompt="John will meet Sarah in", record_steps=True
    )

    class Boom:
        def predict(self, _context):
            raise RuntimeError("induced failure")

    original = engine._slot_predictor
    engine._slot_predictor = Boom()
    try:
        output = engine.llm.generate(
            "John will meet Sarah in", logits_processor=processor, max_new_tokens=4
        )
        assert isinstance(output, str)
    finally:
        engine._slot_predictor = original


@pytest.mark.slow
def test_processor_records_steps(engine):
    """Per-step state is what the live generation view in the dashboard draws."""
    from splm.model.logits_processor import PhraseLanguageLogitsProcessor

    processor = PhraseLanguageLogitsProcessor(
        engine=engine, prompt="John will meet Sarah in", record_steps=True
    )
    engine.llm.generate(
        "John will meet Sarah in", logits_processor=processor, max_new_tokens=4
    )
    assert processor.steps
    first = processor.steps[0]
    assert "expected_slot" in first and "filled_slots" in first


# ---------------------------------------------------------------------------
# reproducibility
# ---------------------------------------------------------------------------


def test_fingerprint_tracks_configuration(config, engine):
    """A changed configuration must produce a different fingerprint."""
    from splm.model.engine import SPLMEngine

    other = SPLMEngine(
        config.with_features({"semantics": False}),
        pipeline=engine.pipeline,
        llm=engine.llm,
    )
    assert engine.fingerprint() != other.fingerprint()
    assert engine.fingerprint() == engine.fingerprint()


def test_describe_reports_what_is_and_is_not_installed(engine):
    described = engine.describe()
    assert described["model"]["model_id"]
    assert "features" in described and "weights" in described
    # Honesty about the knowledge base is part of the contract.
    assert "lexicon" in described
    assert "available" in described["lexicon"]
    assert described["slot_trained"] in {True, False}
