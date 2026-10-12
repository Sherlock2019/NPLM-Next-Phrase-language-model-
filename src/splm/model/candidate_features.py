"""Candidate feature extraction (spec sections 21-22).

For every token the Transformer proposes, work out how well it fits the lexicon,
grammar, morphology, syntax, semantic role, expected phrase slot, style and
context. Each feature is a number in ``[0, 1]`` *plus* a flag saying whether any
evidence was actually available.

That flag is the difference between a research tool and a demo. A feature with no
evidence returns the neutral value and is marked uninformative, so it cannot move a
ranking, and metrics aggregated over features can report their own coverage instead
of quietly counting silence as agreement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from splm.language.packs import LanguagePack, LanguagePackRegistry, UniversalPack, get_registry
from splm.model.base_llm import Candidate
from splm.model.word_tracker import LexicalStatus, WordCandidateTracker
from splm.phrase.schema import ELEMENT_SLOTS, UniversalPhraseFrame
from splm.phrase.slot_predictor import OTHER, SlotPrediction

logger = logging.getLogger(__name__)

#: The feature names, in the fixed order a trained scorer consumes them.
#: Reordering this breaks every saved checkpoint, so it is asserted in tests.
FEATURE_ORDER: tuple[str, ...] = (
    "llm",
    "phrase_slot",
    "grammar",
    "syntax",
    "morphology",
    "semantic",
    "lexicon",
    "style",
    "context",
)

#: Which ablation switch governs which feature (spec section 39).
FEATURE_SWITCHES: dict[str, str] = {
    "lexicon": "lexicon",
    "morphology": "morphology",
    "grammar": "grammar",
    "syntax": "syntax",
    "semantic": "semantics",
    "phrase_slot": "phrase_structure",
    "context": "context_graph",
    "style": "style",
}

NOMINAL_OPENERS = frozenset({"DET", "PRON", "PROPN", "NOUN", "NUM", "ADJ"})


@dataclass
class ScoringContext:
    """Everything the feature extractor may consult about the current step."""

    text: str
    language: str
    frame: UniversalPhraseFrame | None = None
    slots: SlotPrediction | None = None
    style: str | None = None
    context_graph: Any | None = None
    tracker: WordCandidateTracker | None = None
    #: Part of speech of the final word of the prompt, when known.
    trailing_pos: str | None = None
    trailing_word: str | None = None


class PosEstimate(BaseModel):
    """A guess at a candidate word's part of speech, with its basis."""

    pos: str | None = None
    confidence: float = 0.0
    basis: str | None = None

    @property
    def informative(self) -> bool:
        return self.pos is not None


class CandidateFeatures(BaseModel):
    """One candidate's features, provenance and reasons."""

    token: str
    token_id: int
    word: str = Field(default="", description="Candidate text, boundary marker stripped")

    base_logit: float = 0.0
    base_probability: float = 0.0
    base_rank: int = 0

    # Normalised features in [0, 1]; `llm` is the base model's own contribution.
    llm: float = 0.0
    phrase_slot: float = 0.5
    grammar: float = 0.5
    syntax: float = 0.5
    morphology: float = 0.5
    semantic: float = 0.5
    lexicon: float = 0.5
    style: float = 0.5
    context: float = 0.5

    informative: dict[str, bool] = Field(
        default_factory=dict,
        description="Per feature: was there evidence, or is this the neutral default?",
    )
    reasons: list[str] = Field(
        default_factory=list, description="Human-readable basis for the scores actually computed"
    )
    slot_compatibility: dict[str, float] = Field(
        default_factory=dict, description="Compatibility with each candidate slot"
    )
    best_slot: str | None = Field(
        default=None, description="Slot this candidate fits best, if any evidence existed"
    )
    pos_estimate: PosEstimate = Field(default_factory=PosEstimate)
    lexical_status: str = LexicalStatus.UNKNOWN.value
    is_word_start: bool = False

    def vector(self, order: tuple[str, ...] = FEATURE_ORDER) -> list[float]:
        return [float(getattr(self, name)) for name in order]

    def informative_count(self) -> int:
        return sum(1 for value in self.informative.values() if value)

    @property
    def has_structural_evidence(self) -> bool:
        """Whether any non-LLM feature had something to say about this candidate."""
        return any(
            self.informative.get(name, False)
            for name in FEATURE_ORDER
            if name != "llm"
        )


class CandidateFeatureExtractor:
    """Computes :class:`CandidateFeatures` for candidates of one prediction step."""

    def __init__(
        self,
        registry: LanguagePackRegistry | None = None,
        *,
        config: Any | None = None,
        lexicon: Any | None = None,
        neutral: float = 0.5,
    ) -> None:
        self._registry = registry or get_registry()
        self._config = config
        self.lexicon = lexicon
        self.neutral = neutral

    @property
    def universal(self) -> UniversalPack:
        return self._registry.universal()

    def _pack(self, language: str) -> LanguagePack:
        return self._registry.get(language)

    # -- entry point -------------------------------------------------------

    def extract(
        self, candidate: Candidate, context: ScoringContext, *, max_logit: float = 0.0
    ) -> CandidateFeatures:
        pack = self._pack(context.language)
        word = candidate.stripped

        features = CandidateFeatures(
            token=candidate.token,
            token_id=candidate.token_id,
            word=word,
            base_logit=candidate.logit,
            base_probability=candidate.probability,
            base_rank=candidate.rank,
            # Squash the raw logit into [0,1] relative to the step's best candidate so
            # the weighted sum stays scale-free across models.
            llm=self._normalized_llm(candidate, max_logit),
            is_word_start=candidate.is_word_start,
        )
        features.informative["llm"] = True

        features.pos_estimate = self._estimate_pos(word, pack, candidate)

        self._score_lexicon(features, context, pack)
        self._score_slot_compatibility(features, context, pack)
        self._score_phrase_slot(features, context)
        self._score_syntax(features, context, pack)
        self._score_grammar(features, context, pack)
        self._score_morphology(features, context, pack)
        self._score_style(features, context, pack)
        self._score_context(features, context)

        return features

    def extract_all(
        self, candidates: list[Candidate], context: ScoringContext
    ) -> list[CandidateFeatures]:
        max_logit = max((c.logit for c in candidates), default=0.0)
        return [self.extract(c, context, max_logit=max_logit) for c in candidates]

    # -- individual features ----------------------------------------------

    @staticmethod
    def _normalized_llm(candidate: Candidate, max_logit: float) -> float:
        """Map a logit to [0,1] relative to the strongest candidate this step."""
        # 6 logits below the best candidate is already negligible probability.
        span = 6.0
        delta = candidate.logit - max_logit
        return max(0.0, min(1.0, 1.0 + delta / span))

    def _estimate_pos(
        self, word: str, pack: LanguagePack, candidate: Candidate
    ) -> PosEstimate:
        """Guess a candidate word's part of speech from language-pack knowledge.

        No tagger is run - a single out-of-context word cannot be tagged reliably, and
        running one per candidate would dominate latency. Instead the pack's own word
        lists are consulted, and when they say nothing the estimate is left empty
        rather than guessed.
        """
        # Whitespace, punctuation and control tokens are not words. Without this the
        # byte-level BPE symbol for a newline reaches the capitalisation heuristic
        # below and is mistaken for a proper noun.
        if not word or not candidate.is_word_like:
            return PosEstimate()
        lowered = word.lower()

        closed_class = pack.function_word_pos(lowered)
        if closed_class is not None:
            return PosEstimate(
                pos=closed_class, confidence=0.95, basis="closed-class word list"
            )

        if lowered in pack.pronouns:
            return PosEstimate(pos="PRON", confidence=0.9, basis="pronoun table")
        if pack.adposition_cue(lowered):
            return PosEstimate(pos="ADP", confidence=0.85, basis="adposition table")
        if pack.subordinator_cue(lowered):
            return PosEstimate(pos="SCONJ", confidence=0.7, basis="subordinator table")
        if lowered in pack.temporal_adverbs or lowered in pack.locative_adverbs:
            return PosEstimate(pos="ADV", confidence=0.85, basis="adverb list")
        if lowered in pack.manner_adverbs:
            return PosEstimate(pos="ADV", confidence=0.8, basis="manner adverb list")
        if pack.verb_form(lowered, "base") or lowered in (
            pack.grammar.get("auxiliaries", {}) or {}
        ):
            return PosEstimate(pos="VERB", confidence=0.7, basis="verb table")

        classes = pack.classes_of_word(lowered)
        if classes:
            proper = bool(classes & {"city", "country", "region", "software"})
            return PosEstimate(
                pos="PROPN" if proper and word[:1].isupper() else "NOUN",
                confidence=0.75,
                basis=f"semantic class {sorted(classes)[0]}",
            )

        suffixes = pack.syntax.get("manner_adverb_suffixes", []) or []
        if any(lowered.endswith(str(suffix)) for suffix in suffixes) and len(lowered) > 4:
            return PosEstimate(pos="ADV", confidence=0.5, basis="adverb suffix")

        # A capitalised word mid-sentence is usually a name. Weak, and marked so.
        if word[:1].isupper() and candidate.is_word_start:
            weight = float(
                pack.semantics_scoring.get("capitalised_suggests_proper_noun", 0.35)
            )
            return PosEstimate(pos="PROPN", confidence=weight, basis="capitalisation")

        return PosEstimate()

    def _score_lexicon(
        self, features: CandidateFeatures, context: ScoringContext, pack: LanguagePack
    ) -> None:
        tracker = context.tracker or WordCandidateTracker(language=context.language)
        verdict = tracker.judge(features.token)
        features.lexical_status = verdict.status.value
        features.lexicon = tracker.score(verdict, neutral=self.neutral)
        features.informative["lexicon"] = verdict.is_informative
        if verdict.is_informative and verdict.evidence:
            features.reasons.append(verdict.evidence[0])

    def _score_slot_compatibility(
        self, features: CandidateFeatures, context: ScoringContext, pack: LanguagePack
    ) -> None:
        """How well the candidate could fill each slot, with per-slot evidence.

        This powers both the semantic feature and every "semantic focus" style
        metric, so it records which slots had evidence at all.
        """
        word = features.word
        if not word:
            features.informative["semantic"] = False
            features.semantic = self.neutral
            return

        weights = pack.semantics_scoring.get("evidence_weights", {}) or {}
        classes = pack.classes_of_word(word.lower())
        pos = features.pos_estimate.pos

        compatibility: dict[str, float] = {}
        informative = False
        best_reason: str | None = None

        candidate_slots = [s for s in (self.universal.predictable_slots or ELEMENT_SLOTS)]
        for slot in candidate_slots:
            requirements = pack.slot_requirements(slot)
            if not requirements:
                continue

            score: float | None = None
            reason: str | None = None

            wanted_classes = set(requirements.get("classes", []) or [])
            if wanted_classes and classes & wanted_classes:
                score = float(weights.get("gazetteer_hit", 1.0))
                reason = (
                    f"{word!r} is listed as {sorted(classes & wanted_classes)[0]}, "
                    f"which fits {slot.upper()}"
                )
            elif classes and wanted_classes:
                # It is a strong member of some other slot's class, so it is a poorer
                # fit here - but only mildly: words belong to many categories.
                score = 1.0 - float(weights.get("gazetteer_miss_other_slot", 0.8))
                reason = (
                    f"{word!r} is listed as {sorted(classes)[0]}, which does not fit "
                    f"{slot.upper()}"
                )

            if pos is not None:
                allowed = set(requirements.get("pos_allow", []) or [])
                openers = set(requirements.get("pos_open", []) or [])
                if pos in allowed:
                    pos_score = float(weights.get("pos_head_match", 0.6))
                elif pos in openers:
                    pos_score = float(weights.get("pos_open_match", 0.45))
                else:
                    pos_score = 1.0 - float(weights.get("pos_mismatch", 0.5))
                # Combine with any gazetteer evidence, taking the stronger signal.
                score = pos_score if score is None else max(score, pos_score)
                if reason is None:
                    reason = (
                        f"{word!r} looks like a {pos} "
                        f"({features.pos_estimate.basis}), "
                        + ("which can fill " if pos in allowed or pos in openers else "a weaker fit for ")
                        + slot.upper()
                    )

            if score is None:
                continue

            compatibility[slot] = round(max(0.0, min(1.0, score)), 4)
            informative = True
            if slot == (context.slots.top_slot if context.slots else None):
                best_reason = reason

        features.slot_compatibility = compatibility
        features.informative["semantic"] = informative

        if not informative:
            features.semantic = self.neutral
            return

        features.best_slot = max(compatibility, key=lambda slot: compatibility[slot])

        expected = context.slots.top_slot if context.slots else None
        if expected and expected != OTHER and expected in compatibility:
            features.semantic = compatibility[expected]
            if best_reason:
                features.reasons.append(best_reason)
        else:
            features.semantic = compatibility.get(features.best_slot, self.neutral)

    def _score_phrase_slot(
        self, features: CandidateFeatures, context: ScoringContext
    ) -> None:
        """Expected-slot fit: compatibility weighted by the slot distribution.

        Not simply "does it fit the top slot" - the slot predictor's uncertainty is
        carried through, so an ambiguous prediction cannot over-promote one reading.
        """
        if context.slots is None or not features.slot_compatibility:
            features.phrase_slot = self.neutral
            features.informative["phrase_slot"] = False
            return

        total_mass = 0.0
        weighted = 0.0
        for slot, probability in context.slots.distribution.items():
            if slot == OTHER:
                continue
            compatibility = features.slot_compatibility.get(slot)
            if compatibility is None:
                continue
            weighted += probability * compatibility
            total_mass += probability

        if total_mass <= 0:
            features.phrase_slot = self.neutral
            features.informative["phrase_slot"] = False
            return

        features.phrase_slot = round(weighted / total_mass, 4)
        features.informative["phrase_slot"] = True

        top = context.slots.top_slot
        if top != OTHER and features.slot_compatibility.get(top, 0.0) >= 0.7:
            features.reasons.append(
                f"fits the expected {top.upper()} slot "
                f"({context.slots.confidence * 100:.0f}% expected)"
            )

    def _score_syntax(
        self, features: CandidateFeatures, context: ScoringContext, pack: LanguagePack
    ) -> None:
        """Whether the candidate can continue the current syntactic structure.

        The clearest case: after a dangling preposition a nominal must follow. An
        adjective there ("in beautiful") is not impossible - it can premodify a noun -
        so it scores lower, never zero. SPLM implements no hard rules here, which is
        why the UI must say "less compatible", not "invalid".
        """
        pos = features.pos_estimate.pos
        marker = context.frame.dangling_marker if context.frame else None

        if marker is None or pos is None:
            features.syntax = self.neutral
            features.informative["syntax"] = False
            return

        if pos in {"NOUN", "PROPN", "PRON", "NUM"}:
            features.syntax = 0.95
            features.reasons.append(f'a {pos} can directly complete "{marker} ..."')
        elif pos == "DET":
            features.syntax = 0.9
            features.reasons.append(f'a determiner can open the complement of "{marker}"')
        elif pos == "ADJ":
            features.syntax = 0.6
            features.reasons.append(
                f'an adjective after "{marker}" needs a following noun to complete the phrase'
            )
        elif pos == "ADV":
            features.syntax = 0.45
        elif pos in {"ADP", "SCONJ"}:
            features.syntax = 0.2
            features.reasons.append(
                f'a second preposition directly after "{marker}" is a weaker continuation'
            )
        elif pos in {"VERB", "AUX"}:
            features.syntax = 0.3
        else:
            features.syntax = self.neutral
            features.informative["syntax"] = False
            return

        features.informative["syntax"] = True

    def _score_grammar(
        self, features: CandidateFeatures, context: ScoringContext, pack: LanguagePack
    ) -> None:
        """Whether the candidate is a grammatically valid continuation.

        Two checks are implementable from a single candidate word: article
        phonology ("a" versus "an" is decided by the *next* word, so it is checked in
        reverse - a candidate noun after "a" must not start with a vowel sound), and
        the openers each slot permits.
        """
        pos = features.pos_estimate.pos
        trailing = (context.trailing_word or "").lower()
        checks: list[float] = []

        agreement = pack.grammar.get("agreement", {}) or {}
        phonology = agreement.get("article_phonology", {}) or {}
        if trailing in {"a", "an"} and features.word:
            starts_vowel = features.word[:1].lower() in "aeiou"
            exceptions_an = {str(w).lower() for w in phonology.get("exceptions_an", [])}
            exceptions_a = {str(w).lower() for w in phonology.get("exceptions_a", [])}
            word = features.word.lower()

            if word in exceptions_an:
                wants_an = True
            elif word in exceptions_a:
                wants_an = False
            else:
                wants_an = starts_vowel

            correct = (trailing == "an") == wants_an
            checks.append(0.95 if correct else 0.1)
            features.reasons.append(
                f'"{trailing} {features.word}" is '
                + ("phonologically well formed" if correct else "the wrong article form")
            )

        if pos is not None and context.slots is not None:
            top = context.slots.top_slot
            openers = pack.constituent_openers(top)
            if openers:
                checks.append(0.9 if pos in openers else 0.35)

        if not checks:
            features.grammar = self.neutral
            features.informative["grammar"] = False
            return

        features.grammar = round(sum(checks) / len(checks), 4)
        features.informative["grammar"] = True

    def _score_morphology(
        self, features: CandidateFeatures, context: ScoringContext, pack: LanguagePack
    ) -> None:
        """Morphological fit with the surrounding words.

        English marks little, so this is honest about having little to say: it checks
        determiner-number agreement and subject-verb agreement when a verb is expected.
        """
        trailing = (context.trailing_word or "").lower()
        checks: list[float] = []

        agreement = pack.grammar.get("agreement", {}) or {}
        for rule in agreement.get("determiner_noun", []) or []:
            when = rule.get("when", {}) or {}
            determiners = {str(d).lower() for d in when.get("determiner", [])}
            if trailing not in determiners:
                continue
            requires = rule.get("requires", {}) or {}
            wanted_number = requires.get("number")
            if wanted_number and features.word:
                plural = pack.morphology.get("irregular_plurals", {}) or {}
                looks_plural = features.word.lower().endswith("s") or features.word.lower() in {
                    str(v).lower() for v in plural.values()
                }
                correct = (wanted_number == "plural") == looks_plural
                checks.append(0.9 if correct else 0.25)

        if (
            context.slots is not None
            and context.slots.top_slot == "predicate"
            and context.frame is not None
            and context.frame.slot("subject")
        ):
            subject = context.frame.slot("subject")[0]
            number = subject.features.get("number")
            person = subject.features.get("person")
            if number == "singular" and person == 3 and features.word:
                expected = pack.verb_form(features.word.lower(), "3sg")
                if expected:
                    checks.append(0.95 if features.word.lower() == expected else 0.3)

        if not checks:
            features.morphology = self.neutral
            features.informative["morphology"] = False
            return

        features.morphology = round(sum(checks) / len(checks), 4)
        features.informative["morphology"] = True

    def _score_style(
        self, features: CandidateFeatures, context: ScoringContext, pack: LanguagePack
    ) -> None:
        """Fit with the detected register. Never changes meaning, only expression."""
        if not context.style or not features.word:
            features.style = self.neutral
            features.informative["style"] = False
            return

        spec = pack.style_spec(context.style)
        if not spec:
            features.style = self.neutral
            features.informative["style"] = False
            return

        word = features.word.lower()
        prefers = {str(w).lower() for w in spec.get("prefers", [])}
        avoids = {str(w).lower() for w in spec.get("avoids", [])}
        markers = {str(w).lower() for w in (spec.get("markers", {}) or {}).get("lexemes", [])}

        if word in avoids:
            features.style = 0.15
            features.reasons.append(f"{word!r} is out of register for {context.style}")
        elif word in prefers or word in markers:
            features.style = 0.9
            features.reasons.append(f"{word!r} is typical of the {context.style} register")
        else:
            features.style = self.neutral
            features.informative["style"] = False
            return

        features.informative["style"] = True

    def _score_context(
        self, features: CandidateFeatures, context: ScoringContext
    ) -> None:
        """Consistency with what the discourse has already established."""
        graph = context.context_graph
        if graph is None or not features.word:
            features.context = self.neutral
            features.informative["context"] = False
            return

        try:
            verdict = graph.score_candidate(features.word, slot=context.slots.top_slot if context.slots else None)
        except Exception as exc:
            logger.debug("context graph could not score %r: %s", features.word, exc)
            features.context = self.neutral
            features.informative["context"] = False
            return

        if verdict is None:
            features.context = self.neutral
            features.informative["context"] = False
            return

        features.context = float(verdict.score)
        features.informative["context"] = True
        if verdict.reason:
            features.reasons.append(verdict.reason)
