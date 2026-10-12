"""Multilingual behaviour (spec sections 4, 30-31, 45-47, 52).

Two claims are under test, and they are different:

1. **Language identification** works on short text in all three languages.
2. **The frame is language-independent**: English, French and Vietnamese renderings of
   the same meaning produce the same *structure*.

Claim 2 is asserted on structure only. Content lemmas are language-specific, and
comparing them would need a cross-lingual concept inventory the POC does not have -
so the tests check predicate type and sense, grammatical meaning, roles and entities,
and say nothing about word identity.
"""

from __future__ import annotations

import pytest

from conftest import texts
from splm.language.detector import LanguageDetector, ScriptHeuristicDetector

EQUIVALENT = {
    "en": "John will meet Sarah in Paris tomorrow.",
    "fr": "John rencontrera Sarah à Paris demain.",
    "vi": "Ngày mai John sẽ gặp Sarah ở Paris.",
}

LOCATED = {
    "en": "John is in Paris.",
    "fr": "John est à Paris.",
    "vi": "John đang ở Paris.",
}


# ---------------------------------------------------------------------------
# language identification (spec section 12)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("John will meet Sarah in Paris tomorrow.", "en"),
        ("John rencontrera Sarah à Paris demain.", "fr"),
        ("Ngày mai John sẽ gặp Sarah ở Paris.", "vi"),
        ("The engineer deployed the application yesterday.", "en"),
        ("Je voudrais un café s'il vous plaît.", "fr"),
        ("Tôi muốn một ly cà phê.", "vi"),
    ],
)
def test_language_detection(text, expected):
    detector = LanguageDetector(["en", "fr", "vi"], prefer_statistical=False)
    result = detector.detect(text)
    assert result.language == expected, f"{text!r} -> {result.language} ({result.scores})"


def test_vietnamese_is_not_confused_with_french():
    """Both use Latin script with diacritics; the tone stacking is the giveaway."""
    detector = ScriptHeuristicDetector(["en", "fr", "vi"])
    assert detector.detect("Ngày mai John sẽ gặp Sarah ở Paris.").language == "vi"
    assert detector.detect("John rencontrera Sarah à Paris demain.").language == "fr"


def test_detection_reports_low_confidence_on_no_evidence():
    """An ambiguous string must not be assigned a language confidently."""
    detector = ScriptHeuristicDetector(["en", "fr", "vi"])
    result = detector.detect("Paris 2026")
    assert result.confidence < 0.6


def test_language_and_locale_are_separate():
    """Spec section 12: a locale must never decide the language."""
    detector = LanguageDetector(["en", "fr", "vi"], prefer_statistical=False)
    result = detector.detect("John will meet Sarah in Paris tomorrow.", locale="fr-FR")
    assert result.language == "en", "the text is English regardless of the locale tag"
    assert result.locale == "fr-FR"
    parsed = result.parsed_locale
    assert parsed is not None and parsed.region == "FR"


def test_locale_parsing_keeps_dimensions_apart():
    from splm.language.locale import Locale

    locale = Locale.parse("zh-Hant-TW")
    assert locale is not None
    assert (locale.language, locale.script, locale.region) == ("zh", "Hant", "TW")

    # French in Canada is unremarkable; French in Japan is unusual but not wrong.
    assert Locale.parse("fr-CA").is_plausible()
    assert not Locale.parse("fr-JP").is_plausible()


# ---------------------------------------------------------------------------
# the frame is language-independent
# ---------------------------------------------------------------------------


def test_equivalence_fixtures_are_present(sentences):
    """Fail loudly when an equivalence sentence is missing from the fixtures.

    Without this the cross-language tests below would *skip* rather than fail, so a
    regenerated fixture that dropped a sentence would quietly disable the most
    important assertions in the suite - which is exactly what happened once.
    """
    missing: list[str] = []
    for group in (EQUIVALENT, LOCATED):
        for language, text in group.items():
            if text.strip() not in sentences.get(language, {}):
                missing.append(f"{language}: {text}")
    assert not missing, (
        "missing from tests/fixtures; run python scripts/make_fixtures.py:\n  "
        + "\n  ".join(missing)
    )


@pytest.fixture(scope="module")
def equivalent_frames(frame_for):
    frames = {}
    for language, text in EQUIVALENT.items():
        frames[language] = frame_for(text, language)
    return frames


def test_all_three_languages_produce_a_frame(equivalent_frames):
    assert set(equivalent_frames) == {"en", "fr", "vi"}
    for language, frame in equivalent_frames.items():
        assert frame.predicate is not None, f"{language} produced no predicate"


def test_same_predicate_type_across_languages(equivalent_frames):
    types = {
        language: frame.predicate.type.value
        for language, frame in equivalent_frames.items()
    }
    assert len(set(types.values())) == 1, f"predicate types diverged: {types}"


def test_same_tense_across_languages(equivalent_frames):
    """English uses an auxiliary, French an inflection, Vietnamese a particle.

    Three completely different surface mechanisms must yield the same abstract tense -
    which is the whole point of normalising grammatical meaning onto the frame.
    """
    tenses = {
        language: (frame.tense.value if frame.tense else None)
        for language, frame in equivalent_frames.items()
    }
    assert set(tenses.values()) == {"future"}, f"tense diverged: {tenses}"


def test_named_entities_survive_translation(equivalent_frames):
    """Proper nouns are the one lexical content that is safe to compare."""
    for language, frame in equivalent_frames.items():
        all_text = " ".join(element.text for _, element in frame.elements())
        assert "Sarah" in all_text, f"{language} lost Sarah"
        assert "Paris" in all_text, f"{language} lost Paris: {all_text!r}"


def test_participant_role_is_consistent(equivalent_frames):
    """`meet` takes a co-participant in all three languages.

    Each pack states this for its own verb, which is what makes the universal layer
    universal: the same role arrives from three different lexicons.
    """
    for language, frame in equivalent_frames.items():
        participants = texts(frame, "participants")
        assert "Sarah" in participants, (
            f"{language} did not treat Sarah as a participant; "
            f"frame was {frame.to_compact_dict()}"
        )


def test_location_is_consistent(equivalent_frames):
    for language, frame in equivalent_frames.items():
        assert "Paris" in texts(frame, "location"), (
            f"{language} did not record Paris as a location"
        )


def test_structural_agreement_is_high(equivalent_frames):
    """Measured agreement, not asserted equality.

    The score is reported rather than demanded to be perfect: real parses of real
    languages differ, and a test that insisted on 100% would only be satisfied by
    over-fitting the packs. The threshold marks "the same meaning clearly arrived",
    and the exact figures are published by the benchmark.
    """
    scores = {}
    codes = sorted(equivalent_frames)
    for index, left in enumerate(codes):
        for right in codes[index + 1 :]:
            score = equivalent_frames[left].agreement_with(equivalent_frames[right])
            scores[f"{left}-{right}"] = score

    for pair, score in scores.items():
        assert score >= 0.7, f"{pair} agreement only {score:.2f} ({scores})"


def test_signature_excludes_language_specific_lemmas(equivalent_frames):
    """The comparison must not smuggle in content words.

    "meet", "rencontrer" and "gặp" are different strings for the same concept; a
    signature containing them would make cross-language agreement impossible by
    construction, and a signature that compared them anyway would be lying.
    """
    signature = equivalent_frames["en"].structural_signature()
    flattened = str(signature)
    assert "meet" not in flattened
    assert "predicate_type" in signature
    assert "roles" in signature


# ---------------------------------------------------------------------------
# the located reading (spec sections 46-47)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def located_frames(frame_for):
    return {language: frame_for(text, language) for language, text in LOCATED.items()}


def test_located_sense_is_shared(located_frames):
    """"John is in Paris" / "John est a Paris" / "John dang o Paris".

    English and French use a copula plus a preposition; Vietnamese uses a locative
    verb. All three must land on STATE with the *located* sense - spec section 46 and
    47's requirement, and the clearest test of whether the sense inventory is doing
    real work.
    """
    for language, frame in located_frames.items():
        assert frame.predicate is not None, f"{language} produced no predicate"
        assert frame.predicate.type.value == "STATE", (
            f"{language} typed it as {frame.predicate.type.value}"
        )
        assert frame.predicate.sense == "located", (
            f"{language} gave sense {frame.predicate.sense!r}"
        )


def test_located_frames_record_a_place(located_frames):
    for language, frame in located_frames.items():
        places = texts(frame, "location") + texts(frame, "objects")
        assert any("Paris" in place for place in places), (
            f"{language} lost the location: {frame.to_compact_dict()}"
        )


def test_located_subject_is_the_entity(located_frames):
    for language, frame in located_frames.items():
        assert "John" in texts(frame, "subject"), f"{language} lost the subject"


# ---------------------------------------------------------------------------
# adding a language must not require engine changes (spec section 4)
# ---------------------------------------------------------------------------


def test_every_supported_language_has_a_pack(config, registry):
    available = set(registry.available())
    for language in config.supported_languages:
        assert language in available, f"no language pack for {language}"


def test_packs_declare_the_same_interface(registry):
    """Each pack must fill in the same slots, so the engine needs no special cases."""
    for code in ("en", "fr", "vi"):
        pack = registry.get(code)
        assert pack.syntax.get("adposition_cues"), f"{code} has no adposition cues"
        assert pack.syntax.get("subordinator_cues"), f"{code} has no subordinator cues"
        assert pack.syntax.get("slot_sequence_priors"), f"{code} has no sequence priors"
        assert pack.grammar.get("predicate_types"), f"{code} has no predicate types"
        assert pack.style_names, f"{code} has no styles"
        assert pack.semantics.get("slot_requirements"), f"{code} has no slot requirements"


def test_vietnamese_declares_no_inflection(registry):
    """Vietnamese has no verb morphology, and the pack should say so rather than fake it."""
    pack = registry.get("vi")
    assert pack.morphology.get("verb_forms") == {}
    assert pack.grammar.get("auxiliaries"), "tense must come from particles instead"
