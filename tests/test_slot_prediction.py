"""Expected Slot Predictor (spec sections 20, 42).

This is the component with no base-model counterpart, so its contract is worth
stating precisely:

* a dangling marker dominates, because something must follow it;
* a slot already stated is unlikely to be stated again;
* ambiguity is reported as ambiguity, not resolved by rounding;
* probabilities form a distribution, with OTHER absorbing "no new slot".
"""

from __future__ import annotations

import pytest

from splm.phrase.slot_predictor import (
    OTHER,
    HeuristicSlotPredictor,
    SlotContext,
    SlotFeatureExtractor,
)


@pytest.fixture(scope="module")
def predictor(registry):
    return HeuristicSlotPredictor(registry)


def _predict(predictor, builder, sentence_for, text, language="en"):
    sentence = sentence_for(text, language)
    frame = builder.build(sentence)
    return predictor.predict(
        SlotContext(text=text, language=language, frame=frame, sentence=sentence)
    )


# ---------------------------------------------------------------------------
# distribution shape
# ---------------------------------------------------------------------------


def test_distribution_is_normalised(predictor, builder, sentence_for):
    prediction = _predict(predictor, builder, sentence_for, "John will meet Sarah in")
    total = sum(prediction.distribution.values())
    assert total == pytest.approx(1.0, abs=0.01)
    assert all(0.0 <= p <= 1.0 for p in prediction.distribution.values())


def test_other_absorbs_no_new_slot(predictor, builder, sentence_for):
    prediction = _predict(predictor, builder, sentence_for, "John will meet Sarah in")
    assert OTHER in prediction.distribution


def test_ranked_and_top_k_agree(predictor, builder, sentence_for):
    prediction = _predict(predictor, builder, sentence_for, "John will meet Sarah in")
    ranked = prediction.ranked()
    assert [slot for slot, _ in ranked[:3]] == prediction.top_k(3)
    assert prediction.top_slot == ranked[0][0]
    assert prediction.confidence == pytest.approx(ranked[0][1])


# ---------------------------------------------------------------------------
# the dangling marker (the spec's worked example)
# ---------------------------------------------------------------------------


def test_trailing_preposition_predicts_where(predictor, builder, sentence_for):
    """"John will meet Sarah in" must expect a LOCATION."""
    prediction = _predict(predictor, builder, sentence_for, "John will meet Sarah in")
    assert prediction.top_slot == "location"
    assert prediction.confidence > 0.5
    assert prediction.dangling_marker == "in"
    assert prediction.confidence_label in {"high", "medium"}


def test_trailing_instrument_marker_predicts_instrument(predictor, builder, sentence_for):
    prediction = _predict(
        predictor,
        builder,
        sentence_for,
        "The engineer deployed the application to AWS yesterday using",
    )
    assert prediction.top_slot == "instrument"
    assert prediction.confidence > 0.5


def test_trailing_because_predicts_cause(predictor, builder, sentence_for):
    prediction = _predict(predictor, builder, sentence_for, "She traveled to Paris because")
    assert prediction.top_slot == "cause"


def test_completed_sentence_has_no_dangling_marker(predictor, builder, sentence_for):
    prediction = _predict(predictor, builder, sentence_for, "John met Sarah in Paris.")
    assert prediction.dangling_marker is None


def test_marker_is_not_counted_as_a_filled_slot(predictor, builder, sentence_for):
    """A stranded "in" must not make WHERE look answered.

    If it did, the predictor would penalise exactly the slot the marker points at -
    which is how this originally failed, predicting WHEN for "... Sarah in".
    """
    prediction = _predict(predictor, builder, sentence_for, "John will meet Sarah in")
    assert "location" not in prediction.filled_slots
    assert prediction.top_slot == "location"


# ---------------------------------------------------------------------------
# what is already said
# ---------------------------------------------------------------------------


def test_filled_slots_are_reported(predictor, builder, sentence_for):
    prediction = _predict(predictor, builder, sentence_for, "John will meet Sarah in")
    assert "subject" in prediction.filled_slots
    assert "participants" in prediction.filled_slots


def test_stated_slot_is_less_likely_to_repeat(predictor, builder, sentence_for):
    """Once WHERE is answered, a further WHERE is possible but less expected."""
    before = _predict(predictor, builder, sentence_for, "John met Sarah.")
    after = _predict(predictor, builder, sentence_for, "John met Sarah in Paris.")
    assert after.distribution.get("location", 0.0) < before.distribution.get("location", 1.0)


# ---------------------------------------------------------------------------
# honesty about uncertainty
# ---------------------------------------------------------------------------


def test_genuine_ambiguity_is_labelled(predictor, builder, sentence_for):
    """"John is going to" could continue as a destination or a purpose.

    The predictor must not pick one confidently. Spec section 42 names exactly this
    case as one where several roles are live.
    """
    prediction = _predict(predictor, builder, sentence_for, "John is going to")
    top_two = [slot for slot, _ in prediction.ranked()[:2]]

    # Both live readings must be present: a place ("to Paris") and the be-going-to
    # future, where a verb follows ("to leave").
    assert set(top_two) == {"destination", "predicate"}, prediction.ranked()[:4]

    # The alternative must retain real mass rather than be rounded away.
    runner_up = prediction.distribution[top_two[1]]
    assert runner_up > 0.15, f"alternative reading nearly discarded: {prediction.ranked()[:3]}"
    assert prediction.normalized_entropy > 0.3


def test_entropy_tracks_confidence(predictor, builder, sentence_for):
    """A decisive prediction must have lower entropy than an ambiguous one."""
    decisive = _predict(
        predictor,
        builder,
        sentence_for,
        "The engineer deployed the application to AWS yesterday using",
    )
    ambiguous = _predict(predictor, builder, sentence_for, "John is going to")
    assert decisive.normalized_entropy < ambiguous.normalized_entropy
    assert decisive.confidence > ambiguous.confidence


def test_hits_at_k_is_lenient_about_close_calls(predictor, builder, sentence_for):
    """Top-k accuracy exists so reasonable ambiguity is not scored as total failure."""
    prediction = _predict(predictor, builder, sentence_for, "John is going to")
    runner_up = prediction.ranked()[1][0]
    assert not prediction.hits_at_k(runner_up, 1)
    assert prediction.hits_at_k(runner_up, 2)


def test_evidence_is_structured_not_prose(predictor, builder, sentence_for):
    """Explanations come from computed state, never from a generative model."""
    prediction = _predict(predictor, builder, sentence_for, "John will meet Sarah in")
    assert prediction.evidence
    assert any("in" in item for item in prediction.evidence)


# ---------------------------------------------------------------------------
# features shared with the trainable predictor
# ---------------------------------------------------------------------------


def test_feature_vector_is_stable_and_ordered(registry, builder, sentence_for):
    """The trainable predictor consumes these, so their shape must not drift."""
    extractor = SlotFeatureExtractor(registry)
    sentence = sentence_for("John will meet Sarah in")
    frame = builder.build(sentence)
    features = extractor.extract(
        SlotContext(
            text="John will meet Sarah in", language="en", frame=frame, sentence=sentence
        )
    )

    assert features.dangling_marker == "in"
    assert features.has_predicate and features.has_subject
    assert features.marker_cue.get("location", 0.0) > features.marker_cue.get("time", 0.0)

    vector = features.slot_vector("location")
    assert len(vector) == len(features.FEATURE_ORDER)
    assert all(isinstance(value, float) for value in vector)
    assert len(features.scalars()) == 5


def test_untrained_neural_predictor_falls_back_honestly(registry, builder, sentence_for):
    """Selecting the neural backend without a checkpoint must degrade, not break."""
    from splm.phrase.slot_predictor import NeuralSlotPredictor

    predictor = NeuralSlotPredictor(registry, checkpoint=None)
    assert not predictor.is_trained

    sentence = sentence_for("John will meet Sarah in")
    frame = builder.build(sentence)
    prediction = predictor.predict(
        SlotContext(
            text="John will meet Sarah in", language="en", frame=frame, sentence=sentence
        )
    )
    assert prediction.top_slot == "location"
    assert "heuristic" in prediction.backend
    assert any("untrained" in item for item in prediction.evidence)


# ---------------------------------------------------------------------------
# other languages
# ---------------------------------------------------------------------------


def test_french_trailing_preposition(predictor, builder, sentence_for):
    """French `a` is ambiguous in the lexicon but not always in context.

    Out of context `a` marks place, time, destination or recipient about equally. After
    "Jean rencontrera Sarah", a place is genuinely the most likely continuation and a
    time is the live alternative, so the prediction is expected to favour location
    while keeping real mass on time. Demanding artificial uncertainty here would be
    wrong about French, not cautious.
    """
    prediction = _predict(
        predictor, builder, sentence_for, "Jean rencontrera Sarah à", "fr"
    )
    assert prediction.dangling_marker == "à"
    assert prediction.top_slot == "location"
    # The other readings of `a` must survive with real mass rather than be rounded
    # away - their exact ordering is not the claim being made.
    assert prediction.distribution.get("time", 0.0) > 0.05
    assert prediction.distribution.get("destination", 0.0) > 0.05


def test_vietnamese_trailing_preposition(predictor, builder, sentence_for):
    prediction = _predict(
        predictor, builder, sentence_for, "Ngày mai John sẽ gặp Sarah ở", "vi"
    )
    assert prediction.dangling_marker == "ở"
    assert prediction.top_slot == "location"
