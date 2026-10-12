"""Milestone 1: sentence -> Universal Phrase DNA (spec sections 19, 40).

The acceptance list in spec section 40 is tested sentence by sentence, then the
structural requirements that the representation must not violate: recursion
instead of flattening (section 11), and no dependence on word order (section 31).
"""

from __future__ import annotations

import pytest

from conftest import roles, texts
from splm.phrase.schema import PredicateType

# ---------------------------------------------------------------------------
# spec section 40 - the Milestone 1 acceptance list
# ---------------------------------------------------------------------------


def test_simple_action(frame_for):
    """John works. -> WHO = John, ACTION = work"""
    frame = frame_for("John works.")
    assert frame.predicate is not None
    assert frame.predicate.type is PredicateType.ACTION
    assert frame.predicate.lemma == "work"
    assert texts(frame, "subject") == ["John"]
    assert roles(frame, "subject") == ["AGENT"]


def test_state_predicate(frame_for):
    """John is tired. -> WHO = John, STATE = tired

    The copula is not the predicate: the property is.
    """
    frame = frame_for("John is tired.")
    assert frame.predicate is not None
    assert frame.predicate.type is PredicateType.STATE
    assert frame.predicate.lemma == "tired"
    assert frame.predicate.sense == "property"
    assert texts(frame, "subject") == ["John"]


def test_possession_relationship(frame_for):
    """John owns a car. -> WHO = John, RELATIONSHIP = own, WHAT = car

    Spec section 10 types this as RELATIONSHIP; the language pack decides, so this
    test pins the configured behaviour rather than a hard-coded rule.
    """
    frame = frame_for("John owns a car.")
    assert frame.predicate is not None
    assert frame.predicate.type is PredicateType.RELATIONSHIP
    assert frame.predicate.lemma == "own"
    assert texts(frame, "subject") == ["John"]
    assert texts(frame, "objects") == ["car"]


def test_participant_not_patient(frame_for):
    """John met Sarah. -> Sarah is a PARTICIPANT, not a PATIENT.

    This is the predicate-specific role requirement of spec section 18: meeting
    someone does not affect them the way deploying something affects it.
    """
    frame = frame_for("John met Sarah.")
    assert texts(frame, "participants") == ["Sarah"]
    assert not frame.slot("objects")
    assert frame.tense is not None and frame.tense.value == "past"


def test_location(frame_for):
    frame = frame_for("John met Sarah in Paris.")
    assert texts(frame, "location") == ["Paris"]
    assert roles(frame, "location") == ["LOCATION"]


def test_location_and_time(frame_for):
    frame = frame_for("John met Sarah in Paris yesterday.")
    assert texts(frame, "location") == ["Paris"]
    assert texts(frame, "time") == ["yesterday"]


def test_manner_of_transport(frame_for):
    """"by train" is HOW, not USING WHAT, and records the transport annotation."""
    frame = frame_for("John met Sarah in Paris yesterday by train.")
    assert texts(frame, "manner") == ["train"]
    assert not frame.slot("instrument")
    element = frame.slot("manner")[0]
    assert element.annotations.get("transport") == "train"


def test_purpose_is_a_nested_frame(frame_for):
    """A purpose clause becomes a nested frame, not a flat string."""
    frame = frame_for("John met Sarah in Paris yesterday to discuss the contract.")
    goals = frame.slot("goal")
    assert len(goals) == 1
    assert goals[0].semantic_role == "PURPOSE"

    nested = goals[0].frame
    assert nested is not None, "the goal must carry its own frame"
    assert nested.predicate is not None
    assert nested.predicate.lemma == "discuss"
    assert texts(nested, "objects") == ["contract"]


# ---------------------------------------------------------------------------
# spec section 3 - the worked example
# ---------------------------------------------------------------------------


def test_full_spec_example(frame_for):
    """The section 3 sentence must produce every slot the spec lists."""
    frame = frame_for(
        "John will meet Sarah in Paris tomorrow by train to discuss the contract."
    )
    assert frame.predicate is not None
    assert frame.predicate.type is PredicateType.ACTION
    assert frame.predicate.lemma == "meet"

    assert texts(frame, "subject") == ["John"]
    assert texts(frame, "participants") == ["Sarah"]
    assert texts(frame, "location") == ["Paris"]
    assert texts(frame, "time") == ["tomorrow"]
    assert texts(frame, "manner") == ["train"]

    assert frame.tense is not None and frame.tense.value == "future"
    assert frame.negation is False

    goal = frame.slot("goal")[0].frame
    assert goal is not None and goal.predicate is not None
    assert goal.predicate.lemma == "discuss"


def test_spec_section_19_example(frame_for):
    """"deployed ... to AWS yesterday using Terraform" - four distinct slots."""
    frame = frame_for("The engineer deployed the application to AWS yesterday using Terraform.")
    assert frame.predicate is not None
    assert frame.predicate.lemma == "deploy"
    assert texts(frame, "subject") == ["engineer"]
    assert texts(frame, "objects") == ["application"]
    assert texts(frame, "destination") == ["AWS"]
    assert texts(frame, "time") == ["yesterday"]
    # "using Terraform" must resolve to the tool, not to the participle.
    assert texts(frame, "instrument") == ["Terraform"]
    assert frame.tense is not None and frame.tense.value == "past"


# ---------------------------------------------------------------------------
# spec section 11 - nesting, not flattening
# ---------------------------------------------------------------------------


def test_conditional_nests_three_levels(frame_for):
    """If John knew that Sarah might leave, he would call her.

    CONDITION -> the knowing event -> the content of what is known. Flattening any
    of those layers would lose the meaning, so depth is asserted explicitly.
    """
    frame = frame_for("If John knew that Sarah might leave, he would call her.")

    assert frame.predicate is not None
    assert frame.predicate.lemma == "call"
    assert frame.modality == "conditional"

    conditions = frame.slot("condition")
    assert len(conditions) == 1
    assert conditions[0].semantic_role == "CONDITION"

    knowing = conditions[0].frame
    assert knowing is not None
    assert knowing.predicate is not None and knowing.predicate.lemma == "know"

    content = [e for _, e in knowing.elements() if e.frame is not None]
    assert content, "the content of `know` must itself be a frame"
    leaving = content[0].frame
    assert leaving is not None
    assert leaving.predicate is not None and leaving.predicate.lemma == "leave"
    assert leaving.modality == "possible"

    assert frame.depth >= 3


def test_coordinated_clauses_become_sibling_frames(frame_for):
    """Two events must not be squashed into one frame."""
    frame = frame_for("John met Sarah in Paris and left early.")
    assert frame.predicate is not None and frame.predicate.lemma == "meet"
    assert frame.children, "the second clause needs its own frame"
    assert frame.children[0].predicate is not None
    assert frame.children[0].predicate.lemma == "leave"


def test_coordinated_arguments_share_a_role(frame_for):
    """John met Sarah and Mary -> both are participants."""
    frame = frame_for("John met Sarah and Mary in Paris.")
    participants = texts(frame, "participants")
    assert "Sarah" in participants
    assert "Mary" in participants


# ---------------------------------------------------------------------------
# grammatical meaning
# ---------------------------------------------------------------------------


def test_negation_is_a_flag_not_a_slot(frame_for):
    """`not` must set the negation flag, never land in a semantic slot."""
    frame = frame_for("John did not meet Sarah in Paris.")
    assert frame.negation is True
    all_text = [element.text.lower() for _, element in frame.elements()]
    assert "not" not in all_text
    assert not frame.slot("manner")


def test_passive_keeps_semantic_roles_stable(frame_for):
    """The passive changes the syntax, not who did what.

    "The application was deployed by the engineer" must give the same AGENT and
    PATIENT as the active sentence - that is the whole point of a semantic layer.
    """
    frame = frame_for("The application was deployed by the engineer.")
    assert frame.voice is not None and frame.voice.value == "passive"
    assert texts(frame, "subject") == ["engineer"]
    assert roles(frame, "subject") == ["AGENT"]
    assert texts(frame, "objects") == ["application"]
    assert roles(frame, "objects") == ["PATIENT"]


def test_existence(frame_for):
    frame = frame_for("There is a problem with the deployment.")
    assert frame.predicate is not None
    assert frame.predicate.type is PredicateType.EXISTENCE


def test_copular_locative_fills_the_where_slot(frame_for):
    """John is in Paris. -> STATE/located with WHERE = Paris (spec section 46).

    The complement is the syntactic head here, so it is easy to lose. The frame
    must still record a location.
    """
    frame = frame_for("John is in Paris.")
    assert frame.predicate is not None
    assert frame.predicate.type is PredicateType.STATE
    assert frame.predicate.sense == "located"
    assert texts(frame, "subject") == ["John"]
    assert texts(frame, "location") == ["Paris"]


def test_recipient_and_theme_are_distinguished(frame_for):
    frame = frame_for("John gave Sarah the document.")
    assert texts(frame, "recipients") == ["Sarah"]
    assert texts(frame, "objects") == ["document"]


def test_future_modality_and_certainty(frame_for):
    frame = frame_for("John will meet Sarah in Paris tomorrow by train to discuss the contract.")
    assert frame.tense is not None and frame.tense.value == "future"
    assert frame.modality == "intention"
    assert frame.certainty is not None and frame.certainty > 0.5


# ---------------------------------------------------------------------------
# structural invariants
# ---------------------------------------------------------------------------


def test_unresolved_slots_are_reported_not_invented(frame_for):
    """Missing information is listed as missing, never filled with a guess."""
    frame = frame_for("John met Sarah.")
    assert "location" in frame.unresolved_slots
    assert "time" in frame.unresolved_slots
    assert not frame.slot("location")
    assert not frame.slot("time")


def test_frame_records_no_word_order(frame_for):
    """Nothing in the frame may encode surface position (spec section 31).

    Token indices are provenance, not structure: the assertion is that the frame's
    own fields carry no ordering information beyond which slot something is in.
    """
    frame = frame_for("John met Sarah in Paris yesterday.")
    dumped = frame.model_dump()
    for slot in ("subject", "participants", "location", "time"):
        for element in dumped[slot]:
            assert "position" not in element
            assert "order" not in element
            assert "index" not in element


def test_role_alternatives_are_preserved(frame_for):
    """An ambiguous constituent keeps its runner-up roles for later re-ranking."""
    frame = frame_for("John met Sarah in Paris yesterday by train.")
    manner = frame.slot("manner")[0]
    assert manner.alternatives, "runner-up roles must be kept"
    assert all(0.0 <= alt.probability <= 1.0 for alt in manner.alternatives)
    assert manner.confidence >= manner.alternatives[0].probability


def test_serialisation_round_trips(frame_for):
    from splm.phrase.schema import UniversalPhraseFrame

    frame = frame_for("John will meet Sarah in Paris tomorrow by train to discuss the contract.")
    restored = UniversalPhraseFrame.model_validate(frame.model_dump())
    assert restored.predicate is not None
    assert restored.predicate.lemma == frame.predicate.lemma
    assert texts(restored, "location") == texts(frame, "location")
    assert restored.depth == frame.depth


@pytest.mark.parametrize(
    "text",
    [
        "John works.",
        "John is tired.",
        "John owns a car.",
        "John met Sarah.",
        "John met Sarah in Paris.",
        "John met Sarah in Paris yesterday.",
        "John met Sarah in Paris yesterday by train.",
        "John met Sarah in Paris yesterday to discuss the contract.",
    ],
)
def test_milestone_1_sentences_all_produce_a_predicate(frame_for, text):
    """Every acceptance sentence yields a frame with a typed predicate."""
    frame = frame_for(text)
    assert frame.predicate is not None, f"no predicate for {text!r}"
    assert frame.predicate.lemma
    assert isinstance(frame.predicate.type, PredicateType)
    assert frame.subject, f"no WHO for {text!r}"


# ---------------------------------------------------------------------------
# integration with the real parser
# ---------------------------------------------------------------------------


@pytest.mark.parser
def test_live_pipeline_matches_fixture(pipeline, frame_for):
    """The committed fixtures must still describe what the live parser produces."""
    text = "John will meet Sarah in Paris tomorrow by train to discuss the contract."
    live = pipeline.parse_frame(text)
    assert live is not None
    expected = frame_for(text)
    assert live.predicate is not None and expected.predicate is not None
    assert live.predicate.lemma == expected.predicate.lemma
    assert texts(live, "location") == texts(expected, "location")
    assert texts(live, "participants") == texts(expected, "participants")
