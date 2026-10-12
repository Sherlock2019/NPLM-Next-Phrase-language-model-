"""Semantic role assignment (spec sections 17-18).

The properties that matter are not "this sentence gets this role" - those are covered
in test_phrase_builder - but the *rules of evidence*:

* roles are distributions, not decisions;
* roles are predicate-specific, with no fixed ARG0/ARG1 mapping;
* predicate-specific knowledge overrides a generic prior rather than competing
  with it;
* a subtyped relation with its own meaning is not overridden by generic per-verb
  knowledge;
* a cue that says nothing about a role must not veto it.
"""

from __future__ import annotations

import pytest

from splm.linguistic.semantic_roles import SemanticRoleEngine


def _assignments(engine, sentence, predicate_type="ACTION"):
    root = sentence.root
    assert root is not None
    return {a.token_index: a for a in engine.assign_all(sentence, root, predicate_type)}


def _by_head(engine, sentence, lemma, predicate_type="ACTION"):
    """Find an assignment by its head lemma.

    Not by its text: the role engine's ``text`` is the raw constituent span including
    the marker that signalled the role ("by train"), which is what you want when
    debugging evidence. The frame builder is what strips markers for presentation.
    """
    assignments = _assignments(engine, sentence, predicate_type)
    for assignment in assignments.values():
        if assignment.head_lemma == lemma.lower():
            return assignment
    pytest.fail(
        f"no assignment headed by {lemma!r}; "
        f"got {[(a.head_lemma, a.text) for a in assignments.values()]}"
    )


# ---------------------------------------------------------------------------
# distributions, not decisions
# ---------------------------------------------------------------------------


def test_roles_are_distributions(sentence_for, role_engine: SemanticRoleEngine):
    """Every assignment carries ranked alternatives that sum sensibly."""
    sentence = sentence_for("John met Sarah in Paris yesterday by train.")
    assignments = _assignments(role_engine, sentence)
    assert assignments

    for assignment in assignments.values():
        assert assignment.hypotheses, f"{assignment.text!r} has no hypotheses"
        probabilities = [h.probability for h in assignment.hypotheses]
        assert probabilities == sorted(probabilities, reverse=True)
        assert all(0.0 <= p <= 1.0 for p in probabilities)
        # Only the top few are kept, so they need not sum to 1 - but nothing may
        # exceed it either.
        assert sum(probabilities) <= 1.0001


def test_every_hypothesis_records_its_evidence(sentence_for, role_engine):
    sentence = sentence_for("John met Sarah in Paris.")
    assignment = _by_head(role_engine, sentence, "Paris")
    assert assignment.best is not None
    assert assignment.best.evidence, "the winning role must say what supported it"
    assert any("prior_source" in item for item in assignment.best.evidence)


def test_ambiguity_is_visible_in_the_margin(sentence_for, role_engine):
    """A genuinely ambiguous constituent must not report a large margin."""
    sentence = sentence_for("John met Sarah in Paris yesterday by train.")
    train = _by_head(role_engine, sentence, "train")
    paris = _by_head(role_engine, sentence, "Paris")
    # "in Paris" is near-unambiguous; "by train" has a live instrument reading.
    assert paris.margin > train.margin


# ---------------------------------------------------------------------------
# predicate-specific roles (spec section 18)
# ---------------------------------------------------------------------------


def test_same_relation_different_predicate_different_role(sentence_for, role_engine):
    """The object of `meet` and the object of `deploy` are not the same role.

    This is the requirement that ARG0/ARG1 must not be assumed constant: both are
    plain `obj` relations, and they must still come out differently.
    """
    meeting = sentence_for("John met Sarah.")
    deploying = sentence_for("The engineer deployed the application to AWS yesterday using Terraform.")

    sarah = _by_head(role_engine, meeting, "Sarah")
    application = _by_head(role_engine, deploying, "application")

    assert sarah.deprel.startswith("obj")
    assert application.deprel.startswith("obj")
    assert sarah.role == "PARTICIPANT"
    assert application.role == "PATIENT"


def test_predicate_knowledge_overrides_the_generic_prior(sentence_for, role_engine):
    """A per-verb profile replaces the relation prior instead of multiplying into it.

    The generic prior for an object is PATIENT. For `meet` the pack says PARTICIPANT.
    PARTICIPANT must win outright, and it must win because of the profile - which the
    recorded evidence has to show.
    """
    sentence = sentence_for("John met Sarah.")
    sarah = _by_head(role_engine, sentence, "Sarah")

    assert sarah.role == "PARTICIPANT"
    assert sarah.confidence > 0.5
    assert any("predicate_profile" in item for item in sarah.best.evidence)


def test_language_without_ner_still_gets_participant(sentence_for, role_engine):
    """The same must hold with no named-entity information at all.

    Vietnamese has no NER model here. Before predicate knowledge was made the prior,
    PARTICIPANT only won because an entity boost happened to suppress PATIENT, so this
    case silently produced the wrong role. It is now a regression test.
    """
    sentence = sentence_for("Ngày mai John sẽ gặp Sarah ở Paris.", "vi")
    assert all(token.entity_type is None for token in sentence.tokens), (
        "this test is meaningless if the Vietnamese pipeline gained NER; "
        "pick a language without it"
    )
    sarah = _by_head(role_engine, sentence, "Sarah")
    assert sarah.role == "PARTICIPANT"


def test_subtyped_relation_beats_generic_verb_knowledge(sentence_for, role_engine):
    """`obl:agent` is an agent whatever the verb's generic `obl` entry says.

    The pack tells us `deploy` takes a destination as its oblique. In a passive, the
    `obl:agent` is still the agent - the specific relation must not be overridden.
    """
    sentence = sentence_for("The application was deployed by the engineer.")
    engineer = _by_head(role_engine, sentence, "engineer")
    assert engineer.deprel == "obl:agent"
    assert engineer.role == "AGENT"


# ---------------------------------------------------------------------------
# cue behaviour
# ---------------------------------------------------------------------------


def test_adposition_disambiguates_an_oblique(sentence_for, role_engine):
    """`in Paris` and `by train` are both obliques and must not get the same role."""
    sentence = sentence_for("John met Sarah in Paris yesterday by train.")
    assert _by_head(role_engine, sentence, "Paris").role == "LOCATION"
    assert _by_head(role_engine, sentence, "train").role == "MANNER"


def test_lexical_override_annotates(sentence_for, role_engine):
    sentence = sentence_for("John met Sarah in Paris yesterday by train.")
    train = _by_head(role_engine, sentence, "train")
    assert train.annotations.get("transport") == "train"


def test_bare_temporal_adverb(sentence_for, role_engine):
    sentence = sentence_for("John met Sarah in Paris yesterday.")
    assert _by_head(role_engine, sentence, "yesterday").role == "TIME"


def test_negation_particle_gets_no_role(sentence_for, role_engine):
    sentence = sentence_for("John did not meet Sarah in Paris.")
    texts = [a.text.strip().lower() for a in _assignments(role_engine, sentence).values()]
    assert "not" not in texts


def test_tense_particle_gets_no_role(sentence_for, role_engine):
    """Vietnamese marks the future with a particle a parser tags as an adverb.

    Without special handling it becomes a MANNER element, which is both wrong and
    actively misleading - it fills the HOW slot with a tense marker.
    """
    sentence = sentence_for("Ngày mai John sẽ gặp Sarah ở Paris.", "vi")
    texts = [a.text.strip() for a in _assignments(role_engine, sentence).values()]
    assert "sẽ" not in texts


def test_markers_are_not_role_bearers(sentence_for, role_engine):
    """Adpositions and subordinators are evidence, never constituents."""
    sentence = sentence_for("John met Sarah in Paris yesterday to discuss the contract.")
    texts = [a.text.strip().lower() for a in _assignments(role_engine, sentence).values()]
    for marker in ("in", "to", "the"):
        assert marker not in texts


def test_coordinated_element_inherits_its_conjunct_role(sentence_for, role_engine):
    sentence = sentence_for("John met Sarah and Mary in Paris.")
    assignments = _assignments(role_engine, sentence)
    inherited = [
        a for a in assignments.values() if any("inherited_from" in e for e in (a.best.evidence if a.best else []))
    ]
    assert inherited, "the second conjunct must inherit a role"
    assert inherited[0].role == "PARTICIPANT"


def test_role_maps_to_a_frame_slot(role_engine, universal):
    """Every role in the inventory has somewhere to go on the frame."""
    from splm.phrase.schema import ELEMENT_SLOTS

    for role in universal.role_names:
        slot = universal.slot_for_role(role)
        assert slot is not None, f"role {role} has no slot"
        assert slot in ELEMENT_SLOTS, f"role {role} maps to unknown slot {slot}"


def test_entity_boost_does_not_veto_unlisted_roles(registry):
    """A boost table must leave roles it does not mention untouched.

    Entity boosts are multipliers, not distributions. Treating an absent role as
    near-zero turns every boost table into a veto, which is how a correct PATIENT
    reading was being suppressed.
    """
    universal = registry.universal()
    boost = universal.entity_role_boost("PERSON")
    assert boost, "the PERSON entity type should carry boosts"
    assert "PATIENT" not in boost, (
        "this test assumes PERSON does not mention PATIENT; if the pack changed, "
        "choose another role"
    )
    # The contract is asserted on the pack itself: boosts are relative adjustments,
    # so values sit around 1.0 rather than summing to 1.
    assert sum(boost.values()) > 1.5
