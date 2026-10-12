"""Morphology engine (spec section 16).

Normalises whatever features a parser produced into one fixed inventory:
PERSON, NUMBER, GENDER, TENSE, ASPECT, MOOD, VOICE, CASE, POLARITY, POLITENESS,
DEFINITENESS. Universal Dependencies feature names are handled here; a language
pack may override or extend the mapping without touching this code.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from splm.language.packs import LanguagePack, LanguagePackRegistry, get_registry
from splm.linguistic.parser import ParsedSentence, Token

logger = logging.getLogger(__name__)

#: UD feature name -> SPLM category. Language packs may add to this.
UNIVERSAL_FEATURE_MAP: dict[str, str] = {
    "Person": "person",
    "Number": "number",
    "Gender": "gender",
    "Tense": "tense",
    "Aspect": "aspect",
    "Mood": "mood",
    "Voice": "voice",
    "Case": "case",
    "Polarity": "polarity",
    "Polite": "politeness",
    "Definite": "definiteness",
    "Degree": "degree",
    "VerbForm": "verb_form",
    "PronType": "pronoun_type",
    "Poss": "possessive",
    "NumType": "number_type",
    "Animacy": "animacy",
    "Evident": "evidentiality",
    "Reflex": "reflexive",
}

#: UD feature value -> SPLM value, per category.
UNIVERSAL_VALUE_MAP: dict[str, dict[str, Any]] = {
    "number": {"Sing": "singular", "Plur": "plural", "Dual": "dual"},
    "person": {"0": 0, "1": 1, "2": 2, "3": 3},
    "gender": {"Masc": "masculine", "Fem": "feminine", "Neut": "neuter", "Com": "common"},
    "tense": {"Past": "past", "Pres": "present", "Fut": "future", "Imp": "past", "Pqp": "past"},
    "aspect": {
        "Imp": "progressive",
        "Prog": "progressive",
        "Perf": "perfect",
        "Hab": "habitual",
        "Iter": "habitual",
    },
    "mood": {
        "Ind": "indicative",
        "Imp": "imperative",
        "Sub": "subjunctive",
        "Cnd": "conditional",
        "Opt": "optative",
        "Pot": "possible",
    },
    "voice": {"Act": "active", "Pass": "passive", "Mid": "middle", "Cau": "causative"},
    "case": {
        "Nom": "nominative",
        "Acc": "accusative",
        "Gen": "genitive",
        "Dat": "dative",
        "Loc": "locative",
        "Ins": "instrumental",
        "Abl": "ablative",
    },
    "polarity": {"Neg": "negative", "Pos": "positive"},
    "definiteness": {"Def": "definite", "Ind": "indefinite", "Spec": "specific"},
    "degree": {"Pos": "positive", "Cmp": "comparative", "Sup": "superlative", "Abs": "absolute"},
    "verb_form": {
        "Fin": "finite",
        "Inf": "infinitive",
        "Part": "participle",
        "Ger": "gerund",
        "Sup": "supine",
        "Conv": "converb",
    },
    "possessive": {"Yes": True},
    "reflexive": {"Yes": True},
    "politeness": {"Form": "formal", "Infm": "informal", "Elev": "elevated", "Humb": "humble"},
}

#: POS tags that can head a nominal constituent.
NOMINAL_POS = frozenset({"NOUN", "PROPN", "PRON", "NUM"})
#: POS tags that can head a predicate.
PREDICATE_POS = frozenset({"VERB", "AUX", "ADJ", "NOUN", "PROPN", "ADV"})


class Morphology(BaseModel):
    """Normalised morphological analysis of one word."""

    form: str
    lemma: str
    pos: str

    person: int | None = None
    number: str | None = None
    gender: str | None = None
    tense: str | None = None
    aspect: str | None = None
    mood: str | None = None
    voice: str | None = None
    case: str | None = None
    polarity: str | None = None
    politeness: str | None = None
    definiteness: str | None = None
    degree: str | None = None
    verb_form: str | None = None
    pronoun_type: str | None = None
    possessive: bool | None = None
    reflexive: bool | None = None
    animacy: str | None = None

    extras: dict[str, Any] = Field(
        default_factory=dict, description="Recognised features with no dedicated field"
    )
    unmapped: dict[str, str] = Field(
        default_factory=dict, description="Raw features this engine did not understand"
    )

    @property
    def is_nominal(self) -> bool:
        return self.pos in NOMINAL_POS

    @property
    def is_negative(self) -> bool:
        return self.polarity == "negative"

    def filled(self) -> dict[str, Any]:
        """Only the categories that were actually determined."""
        skip = {"form", "lemma", "pos", "extras", "unmapped"}
        return {
            key: value
            for key, value in self.model_dump().items()
            if key not in skip and value is not None
        }

    def agrees_with(self, other: "Morphology", *, categories: tuple[str, ...] = ("person", "number", "gender")) -> bool | None:
        """Whether two words agree on the given categories.

        Returns ``None`` when neither word specifies any of them - absence of
        marking is not disagreement, and English marks very little.
        """
        comparable = [
            (getattr(self, cat), getattr(other, cat))
            for cat in categories
            if getattr(self, cat) is not None and getattr(other, cat) is not None
        ]
        if not comparable:
            return None
        return all(mine == theirs for mine, theirs in comparable)


class AgreementCheck(BaseModel):
    """Outcome of a grammatical agreement test."""

    ok: bool
    checked: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    # None-valued categories mean "the language did not mark this here".
    undetermined: bool = False


class MorphologyEngine:
    """Turns parser features into :class:`Morphology`, and checks agreement."""

    def __init__(self, registry: LanguagePackRegistry | None = None) -> None:
        self._registry = registry or get_registry()

    def _pack(self, language: str) -> LanguagePack:
        return self._registry.get(language)

    # -- analysis ----------------------------------------------------------

    def analyze(self, token: Token, language: str) -> Morphology:
        """Normalise one word's features."""
        pack = self._pack(language)
        feature_map = {**UNIVERSAL_FEATURE_MAP, **pack.feature_map}
        value_maps = self._merged_value_maps(pack)

        fields: dict[str, Any] = {}
        extras: dict[str, Any] = {}
        unmapped: dict[str, str] = {}

        for raw_key, raw_value in token.feats.items():
            category = feature_map.get(raw_key)
            if category is None:
                unmapped[raw_key] = raw_value
                continue
            value = value_maps.get(category, {}).get(raw_value, raw_value)
            if category in Morphology.model_fields:
                fields[category] = value
            else:
                extras[category] = value

        analysis = Morphology(
            form=token.text,
            lemma=token.lemma or token.text,
            pos=token.upos,
            extras=extras,
            unmapped=unmapped,
            **fields,
        )
        return self._apply_language_defaults(analysis, token, pack)

    def analyze_sentence(self, sentence: ParsedSentence) -> dict[int, Morphology]:
        """Analyse every word, keyed by word index."""
        return {
            token.index: self.analyze(token, sentence.language) for token in sentence.tokens
        }

    def _merged_value_maps(self, pack: LanguagePack) -> dict[str, dict[str, Any]]:
        merged = {category: dict(table) for category, table in UNIVERSAL_VALUE_MAP.items()}
        for category, table in pack.value_map.items():
            merged.setdefault(category, {}).update(table)
        return merged

    def _apply_language_defaults(
        self, analysis: Morphology, token: Token, pack: LanguagePack
    ) -> Morphology:
        """Fill gaps the parser left, using language-pack knowledge.

        Only *absent* values are filled; a parser's explicit feature always wins.
        """
        updates: dict[str, Any] = {}

        if token.upos == "PRON":
            for key, value in pack.pronoun_features(token.text).items():
                if key == "animate":
                    if analysis.animacy is None:
                        updates["animacy"] = "animate" if value else "inanimate"
                elif key in Morphology.model_fields and getattr(analysis, key) is None:
                    updates[key] = value

        # Proper nouns and common nouns default to 3rd person; this is what makes
        # subject-verb agreement checkable in a language that marks almost nothing.
        if token.upos in {"NOUN", "PROPN"} and analysis.person is None:
            defaults = pack.morphology.get("defaults", {}) or {}
            if "person" in defaults:
                updates["person"] = defaults["person"]

        if not updates:
            return analysis
        return analysis.model_copy(update=updates)

    # -- agreement ---------------------------------------------------------

    def check_subject_verb(
        self, subject: Morphology | None, verb: Morphology | None
    ) -> AgreementCheck:
        """Check subject-verb agreement, reporting honestly when unmarked."""
        if subject is None or verb is None:
            return AgreementCheck(ok=True, undetermined=True)

        checked: list[str] = []
        violations: list[str] = []

        # Only finite present-tense verbs carry agreement marking in the POC
        # languages; elsewhere there is nothing to violate.
        for category in ("person", "number"):
            mine, theirs = getattr(subject, category), getattr(verb, category)
            if mine is None or theirs is None:
                continue
            checked.append(category)
            if mine != theirs:
                violations.append(f"{category}: subject={mine} verb={theirs}")

        return AgreementCheck(
            ok=not violations,
            checked=checked,
            violations=violations,
            undetermined=not checked,
        )

    # -- generation --------------------------------------------------------

    def inflect(self, lemma: str, form: str, language: str) -> str | None:
        """Produce an inflected form, e.g. ``inflect("go", "3sg", "en") == "goes"``.

        Consults the language pack's irregular table first, then its rules. Returns
        ``None`` when the language pack cannot say - callers must treat that as
        "unknown", never as "invalid".
        """
        pack = self._pack(language)
        irregular = pack.verb_form(lemma, form)
        if irregular:
            return irregular

        rules = (pack.morphology.get("inflection_rules", {}) or {}).get(
            {"3sg": "third_person_singular", "plural": "plural_noun", "past": "past_tense"}.get(
                form, form
            )
        )
        if not rules:
            return None
        return self._apply_inflection_rules(lemma, rules)

    @staticmethod
    def _apply_inflection_rules(lemma: str, rules: list[dict[str, Any]]) -> str | None:
        vowels = set("aeiou")
        for rule in rules:
            if rule.get("default"):
                return lemma + str(rule.get("add", ""))

            suffixes = rule.get("suffix_in") or []
            match = next((s for s in suffixes if lemma.endswith(str(s))), None)
            if match is None:
                continue
            if rule.get("preceded_by_consonant"):
                position = len(lemma) - len(str(match)) - 1
                if position < 0 or lemma[position] in vowels:
                    continue
            if "replace" in rule:
                return lemma[: len(lemma) - len(str(match))] + str(rule["replace"])
            return lemma + str(rule.get("add", ""))
        return None

    def plural_of(self, lemma: str, language: str) -> str | None:
        pack = self._pack(language)
        irregular = (pack.morphology.get("irregular_plurals", {}) or {}).get(lemma.lower())
        if irregular:
            return str(irregular)
        return self.inflect(lemma, "plural", language)
