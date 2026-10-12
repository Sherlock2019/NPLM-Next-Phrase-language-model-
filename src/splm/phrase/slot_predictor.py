"""Expected Slot Predictor (spec sections 20, 42).

Given what the sentence already says, predict what *kind* of meaning comes next:

    "John will meet Sarah in"  ->  { location: 0.83, time: 0.07, manner: 0.03, ... }

This is the component that lets SPLM ask "what information is missing?" before
asking "what token is likely?".

Two backends behind one interface:

``HeuristicSlotPredictor``
    Language-pack priors times evidence from a dangling marker and from which
    slots are already filled. No training data needed, fully inspectable.

``NeuralSlotPredictor``
    A small trained network over the same feature vector (the Phase 9 evolution).
    Because both consume :class:`SlotFeatures`, swapping them changes nothing
    upstream, and the heuristic's output is exactly what the neural version is
    trained to beat.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from splm.language.packs import LanguagePack, LanguagePackRegistry, UniversalPack, get_registry
from splm.linguistic.parser import ParsedSentence, Token
from splm.phrase.schema import ELEMENT_SLOTS, UniversalPhraseFrame

logger = logging.getLogger(__name__)

#: Absorbs probability for "no new slot": punctuation, a continuing constituent,
#: a discourse marker, the end of the sentence.
OTHER = "OTHER"

#: Marker part-of-speech tags that can dangle at the end of an unfinished clause.
MARKER_POS = frozenset({"ADP", "SCONJ", "PART"})


class SlotPrediction(BaseModel):
    """A distribution over the semantic slot that plausibly comes next."""

    distribution: dict[str, float] = Field(default_factory=dict)
    top_slot: str = OTHER
    confidence: float = 0.0
    entropy: float = 0.0
    normalized_entropy: float = Field(
        default=1.0, description="Entropy scaled to [0,1]; 1.0 means no information"
    )
    confidence_label: str = "ambiguous"
    filled_slots: list[str] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    dangling_marker: str | None = None
    evidence: list[str] = Field(default_factory=list)
    backend: str = "heuristic"

    def ranked(self) -> list[tuple[str, float]]:
        return sorted(self.distribution.items(), key=lambda kv: kv[1], reverse=True)

    def top_k(self, k: int) -> list[str]:
        return [slot for slot, _ in self.ranked()[:k]]

    def probability(self, slot: str) -> float:
        return self.distribution.get(slot, 0.0)

    def hits_at_k(self, true_slot: str, k: int) -> bool:
        """Top-k slot accuracy (spec section 6 of the metrics brief).

        Reasonable ambiguity - INSTRUMENT versus PARTICIPANT after "with" - should
        not be scored as total failure, so accuracy is reported at several k.
        """
        return true_slot in self.top_k(k)


@dataclass
class SlotContext:
    """Everything the predictor is allowed to look at."""

    text: str
    language: str
    frame: UniversalPhraseFrame | None = None
    sentence: ParsedSentence | None = None
    context_graph: Any | None = None
    style: str | None = None


@dataclass
class SlotFeatures:
    """The feature vector shared by both backends.

    Kept explicit and ordered so a trained model's inputs cannot silently drift
    from what the heuristic sees.
    """

    #: Per-slot features, each a mapping slot -> value.
    sequence_prior: dict[str, float] = field(default_factory=dict)
    marker_cue: dict[str, float] = field(default_factory=dict)
    expected_by_predicate: dict[str, float] = field(default_factory=dict)
    already_filled: dict[str, float] = field(default_factory=dict)

    #: Scalar context features.
    predicate_type: str | None = None
    has_predicate: bool = False
    has_subject: bool = False
    filled_count: int = 0
    token_count: int = 0
    dangling_marker: str | None = None
    ends_with_marker: bool = False
    #: True when the predicate's argument structure settled the marker's reading.
    marker_override: bool = False

    FEATURE_ORDER: tuple[str, ...] = (
        "sequence_prior",
        "marker_cue",
        "expected_by_predicate",
        "already_filled",
    )

    def slot_vector(self, slot: str) -> list[float]:
        """Per-slot features in a fixed order, for a trained scorer."""
        return [
            self.sequence_prior.get(slot, 0.0),
            self.marker_cue.get(slot, 0.0),
            self.expected_by_predicate.get(slot, 0.0),
            self.already_filled.get(slot, 0.0),
        ]

    def scalars(self) -> list[float]:
        return [
            1.0 if self.has_predicate else 0.0,
            1.0 if self.has_subject else 0.0,
            float(self.filled_count),
            float(self.token_count),
            1.0 if self.ends_with_marker else 0.0,
        ]


@runtime_checkable
class SlotPredictor(Protocol):
    def predict(self, context: SlotContext) -> SlotPrediction: ...


class SlotFeatureExtractor:
    """Builds :class:`SlotFeatures` from a :class:`SlotContext`.

    Shared by every backend, and reused by the training-data miner: a gold UD tree
    yields one (features, true next slot) pair per constituent, which is how the
    trainable predictor gets supervision without hand labelling.
    """

    def __init__(self, registry: LanguagePackRegistry | None = None) -> None:
        self._registry = registry or get_registry()

    @property
    def universal(self) -> UniversalPack:
        return self._registry.universal()

    def _pack(self, language: str) -> LanguagePack:
        return self._registry.get(language)

    def extract(self, context: SlotContext) -> SlotFeatures:
        pack = self._pack(context.language)
        frame = context.frame

        marker = self._dangling_marker(context, pack)
        features = SlotFeatures(
            sequence_prior=self._sequence_prior(frame, context, pack),
            marker_cue=self._marker_cue(marker, pack, frame),
            expected_by_predicate=self._expected_by_predicate(frame),
            marker_override=marker is not None
            and bool(self._marker_predicate_override(pack, marker, frame)),
            already_filled={
                slot: 1.0 for slot in ELEMENT_SLOTS if frame is not None and frame.slot(slot)
            },
            predicate_type=(
                frame.predicate.type.value if frame and frame.predicate else None
            ),
            has_predicate=bool(frame and frame.predicate),
            has_subject=bool(frame and frame.slot("subject")),
            filled_count=len(frame.filled_slots()) if frame else 0,
            token_count=len(context.sentence) if context.sentence else 0,
            dangling_marker=marker,
            ends_with_marker=marker is not None,
        )
        return features

    # -- individual features ----------------------------------------------

    def _dangling_marker(self, context: SlotContext, pack: LanguagePack) -> str | None:
        """The trailing adposition or subordinator of an unfinished clause.

        The frame builder already identifies this from the parse, so prefer its
        answer. The raw-text fallback covers the case where parsing failed and SPLM
        is running without structure.
        """
        if context.frame is not None and context.frame.dangling_marker:
            return context.frame.dangling_marker

        stripped = context.text.rstrip()
        if not stripped or stripped[-1] in ".!?;:,":
            return None

        last_word = stripped.split()[-1].lower().strip("\"'()[[]")
        if not last_word:
            return None

        known = (
            last_word in pack.syntax.get("adposition_cues", {})
            or last_word in pack.syntax.get("subordinator_cues", {})
            or last_word in pack.syntax.get("clause_head_cues", {})
        )
        if not known:
            return None

        # Confirm with the parse when it agrees, but do not require it.
        sentence = context.sentence
        if sentence is not None and sentence.tokens:
            final: Token = sentence.tokens[-1]
            if final.lower_lemma == last_word and final.upos not in MARKER_POS:
                if final.upos not in {"VERB", "AUX"}:
                    return None
        return last_word

    def _marker_cue(
        self,
        marker: str | None,
        pack: LanguagePack,
        frame: UniversalPhraseFrame | None = None,
    ) -> dict[str, float]:
        """Slot likelihoods implied by a dangling marker.

        A word can appear in several cue tables - English "to" is both a preposition and
        an infinitival marker - so the tables are merged by taking the strongest reading
        per role rather than averaging them away.

        The merge alone is not always enough. "gave the document to ___" wants a
        recipient, but the infinitival reading of "to" is the strongest entry in the
        tables, so it would win. The verb decides: after a transfer predicate, "to"
        introduces a recipient. That is stated declaratively in the language pack rather
        than inferred here.
        """
        if marker is None:
            return {}

        override = self._marker_predicate_override(pack, marker, frame)
        if override:
            return self._roles_to_slots(override)

        # A trailing copula or auxiliary is waiting for its complement, and a copular
        # complement is the predicate ("The day after Monday is ___" wants Tuesday,
        # which SPLM records as the predicate under an identity reading).
        if pack.auxiliary_spec(marker) or pack.function_word_pos(marker) == "AUX":
            cue = pack.syntax.get("trailing_auxiliary_cue") or {"predicate": 0.85}
            return self._roles_to_slots({k: float(v) for k, v in cue.items()})

        merged: dict[str, float] = {}
        for cue in (
            pack.adposition_cue(marker),
            pack.subordinator_cue(marker),
            self._clause_head_cue(marker, pack),
        ):
            for role, probability in cue.items():
                merged[role] = max(merged.get(role, 0.0), probability)

        return self._roles_to_slots(merged)

    @staticmethod
    def _marker_predicate_override(
        pack: LanguagePack, marker: str, frame: UniversalPhraseFrame | None
    ) -> dict[str, float]:
        """A marker reading that this predicate's own argument structure settles."""
        if frame is None or frame.predicate is None:
            return {}

        rules = pack.syntax.get("marker_predicate_overrides", []) or []
        classes = pack.syntax.get("predicate_classes", {}) or {}
        lemma = frame.predicate.lemma.lower()

        for rule in rules:
            markers = {str(m).lower() for m in (rule.get("markers") or [])}
            if marker.lower() not in markers:
                continue

            members: set[str] = set()
            for class_name in rule.get("predicate_classes") or []:
                members |= {str(m).lower() for m in (classes.get(class_name) or [])}
            members |= {str(m).lower() for m in (rule.get("predicate_lemmas") or [])}

            if lemma in members:
                return {k: float(v) for k, v in (rule.get("distribution") or {}).items()}
        return {}

    @staticmethod
    def _clause_head_cue(marker: str, pack: LanguagePack) -> dict[str, float]:
        spec = (pack.syntax.get("clause_head_cues", {}) or {}).get(marker, {})
        return {k: float(v) for k, v in (spec.get("distribution") or {}).items()}

    def _roles_to_slots(self, role_distribution: dict[str, float]) -> dict[str, float]:
        """Collapse a role distribution onto frame slots.

        A key may also name a slot directly. That is needed for ``predicate``, which is
        something a marker can genuinely predict - "is going to ___" may be followed by
        a verb - but which is not a semantic role and so has no role name.
        """
        slots: dict[str, float] = {}
        for key, probability in role_distribution.items():
            if key in ELEMENT_SLOTS or key == "predicate":
                slot: str | None = key
            else:
                slot = self.universal.slot_for_role(key)
                if slot is not None and slot not in ELEMENT_SLOTS:
                    slot = None
            if slot is None:
                continue
            slots[slot] = max(slots.get(slot, 0.0), probability)
        return slots

    def _sequence_prior(
        self, frame: UniversalPhraseFrame | None, context: SlotContext, pack: LanguagePack
    ) -> dict[str, float]:
        """Which slot usually comes next in this language, given the last one.

        Word order is a *realisation* fact, so it lives in the language pack and is
        used only here - never stored on the frame (spec section 31).
        """
        priors = pack.slot_sequence_priors
        if not priors:
            return {}

        if frame is None or frame.predicate is None:
            # A fragment with a subject but no predicate is waiting for the predicate,
            # not for another adjunct: "The engineer ___".
            if frame is not None and frame.slot("subject") and "after_subject" in priors:
                return priors["after_subject"]
            return priors.get("sentence_initial", {})

        last_slot = self._last_filled_slot(frame)
        for key in (f"after_{last_slot}" if last_slot else None, "after_predicate"):
            if key and key in priors:
                return priors[key]
        return priors.get("sentence_initial", {})

    @staticmethod
    def _last_filled_slot(frame: UniversalPhraseFrame) -> str | None:
        """The slot whose content appears latest in the surface string."""
        best_slot: str | None = None
        best_index = -1
        for slot, element in frame.elements():
            if not element.token_indices:
                continue
            index = max(element.token_indices)
            if index > best_index:
                best_index, best_slot = index, slot
        if frame.predicate is not None and frame.predicate.token_index is not None:
            if frame.predicate.token_index > best_index:
                return "predicate"
        return best_slot

    def _expected_by_predicate(
        self, frame: UniversalPhraseFrame | None
    ) -> dict[str, float]:
        """Slots this predicate type plausibly takes, from the universal pack."""
        if frame is None or frame.predicate is None:
            return {}
        table = (
            self.universal.phrase_schema.get("expected_slots_by_predicate_type", {}) or {}
        )
        expected = table.get(frame.predicate.type.value, [])
        if not expected:
            return {}
        # Earlier in the list means more salient for this predicate type.
        span = max(len(expected), 1)
        return {slot: 1.0 - (position / (2 * span)) for position, slot in enumerate(expected)}


class HeuristicSlotPredictor:
    """Rule- and prior-driven slot prediction. The baseline the neural one must beat."""

    name = "heuristic"

    def __init__(
        self,
        registry: LanguagePackRegistry | None = None,
        *,
        extractor: SlotFeatureExtractor | None = None,
        config: Any | None = None,
    ) -> None:
        self._registry = registry or get_registry()
        self.extractor = extractor or SlotFeatureExtractor(self._registry)
        self._config = config

    @property
    def universal(self) -> UniversalPack:
        return self._registry.universal()

    def predict(self, context: SlotContext) -> SlotPrediction:
        pack = self._registry.get(context.language)
        features = self.extractor.extract(context)
        candidates = self.universal.predictable_slots or list(ELEMENT_SLOTS)

        exponent = float(pack.syntax.get("dangling_marker_exponent", 2.0))
        marker_floor = float(pack.syntax.get("marker_slot_prior_floor", 0.10))
        repeat_penalty = float(pack.syntax.get("repeat_slot_penalty", 0.25))
        repeatable = set(pack.syntax.get("repeatable_slots", []) or [])

        scores: dict[str, float] = {}
        evidence: list[str] = []

        for slot in candidates:
            if slot == "predicate":
                # Predicting "a predicate comes next" is normally only meaningful when
                # there is not one yet - unless a dangling marker says a verb follows,
                # as in the be-going-to future, where a second predicate is exactly what
                # is expected.
                if features.has_predicate and "predicate" not in features.marker_cue:
                    continue

            prior = features.sequence_prior.get(slot, 0.01)

            # A slot the marker explicitly predicts must not be vetoed by a word-order
            # prior that simply never listed it. "is going to [leave]" needs a predicate
            # next, which no "what usually follows a predicate" table mentions.
            #
            # Only slots the prior *omits* get this floor. Applying it to slots that do
            # have a prior would flatten the ordering the prior exists to express, and
            # markers like "with" - which name several roles at once - would stop being
            # distinguishable by position at all.
            if slot in features.marker_cue and slot not in features.sequence_prior:
                prior = marker_floor

            score = prior

            if features.marker_cue:
                # A dangling marker is strong evidence, so its cue is sharpened
                # before being applied.
                cue = features.marker_cue.get(slot, 0.01)
                score *= cue**exponent

            expected = features.expected_by_predicate.get(slot)
            if expected is not None:
                score *= 0.5 + expected

            if features.already_filled.get(slot) and slot not in repeatable:
                score *= repeat_penalty

            scores[slot] = score

        total = sum(scores.values())
        if total <= 0:
            distribution = {OTHER: 1.0}
        else:
            # Remaining mass goes to OTHER: continuing the current constituent,
            # punctuation, or simply ending the sentence.
            other = self._other_mass(features)
            distribution = {
                slot: (score / total) * (1.0 - other) for slot, score in scores.items()
            }
            distribution[OTHER] = other

        distribution = {
            slot: round(value, 4) for slot, value in distribution.items() if value > 1e-4
        }

        if features.dangling_marker:
            evidence.append(
                f'the phrase ends with "{features.dangling_marker}", which in '
                f"{context.language} most often introduces "
                + ", ".join(
                    slot.upper()
                    for slot, _ in sorted(
                        features.marker_cue.items(), key=lambda kv: kv[1], reverse=True
                    )[:2]
                )
            )
        if features.predicate_type:
            evidence.append(
                f"the predicate is {features.predicate_type}, which typically takes "
                + ", ".join(
                    slot.upper()
                    for slot in list(features.expected_by_predicate)[:4]
                )
            )
        filled = [slot for slot in ELEMENT_SLOTS if features.already_filled.get(slot)]
        if filled:
            evidence.append("already stated: " + ", ".join(slot.upper() for slot in filled))

        return self._finalize(
            distribution,
            features=features,
            evidence=evidence,
            backend=self.name,
        )

    def _other_mass(self, features: SlotFeatures) -> float:
        """How much probability to reserve for "no new slot".

        Small when a marker is dangling (something must follow it), larger when the
        clause already looks complete.
        """
        if features.ends_with_marker:
            return 0.03
        if not features.has_predicate:
            return 0.15
        return min(0.45, 0.12 + 0.04 * features.filled_count)

    def _finalize(
        self,
        distribution: dict[str, float],
        *,
        features: SlotFeatures,
        evidence: list[str],
        backend: str,
    ) -> SlotPrediction:
        total = sum(distribution.values()) or 1.0
        normalized = {slot: value / total for slot, value in distribution.items()}
        ranked = sorted(normalized.items(), key=lambda kv: kv[1], reverse=True)
        top_slot, top_probability = ranked[0] if ranked else (OTHER, 0.0)

        entropy = -sum(p * math.log(p) for _, p in ranked if p > 0)
        max_entropy = math.log(len(ranked)) if len(ranked) > 1 else 1.0
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

        thresholds = self._thresholds()
        if top_probability >= thresholds["high"] and normalized_entropy <= thresholds["low_entropy"]:
            label = "high"
        elif top_probability >= thresholds["medium"]:
            label = "medium"
        else:
            label = "ambiguous"

        missing = [
            slot
            for slot in ELEMENT_SLOTS
            if not features.already_filled.get(slot)
            and slot in features.expected_by_predicate
        ]

        return SlotPrediction(
            distribution={slot: round(value, 4) for slot, value in normalized.items()},
            top_slot=top_slot,
            confidence=round(top_probability, 4),
            entropy=round(entropy, 4),
            normalized_entropy=round(normalized_entropy, 4),
            confidence_label=label,
            filled_slots=[slot for slot in ELEMENT_SLOTS if features.already_filled.get(slot)],
            missing_slots=missing,
            dangling_marker=features.dangling_marker,
            evidence=evidence,
            backend=backend,
        )

    def _thresholds(self) -> dict[str, float]:
        defaults = {"high": 0.6, "medium": 0.35, "low_entropy": 0.6}
        if self._config is None:
            return defaults
        configured = self._config.get("app.slot_predictor.confidence_thresholds") or {}
        return {**defaults, **{k: float(v) for k, v in configured.items()}}

    # -- convenience -------------------------------------------------------

    def predict_from_analysis(self, analysis: Any) -> SlotPrediction:
        """Predict directly from a :class:`splm.pipeline.Analysis`."""
        return self.predict(
            SlotContext(
                text=analysis.text,
                language=analysis.language,
                frame=analysis.frame,
                sentence=analysis.sentence,
                style=analysis.style,
            )
        )


class NeuralSlotPredictor(HeuristicSlotPredictor):
    """Trainable slot predictor (Phase 9).

    Learns "WHO + ACTION + `in` -> WHERE" from data rather than from the priors in
    ``syntax.yaml``, over exactly the features the heuristic uses. Training lives in
    :mod:`splm.training.slot_trainer`; this class only loads and applies a
    checkpoint, and falls back to the heuristic when none exists so the pipeline
    never breaks because a model has not been trained yet.
    """

    name = "neural"

    def __init__(
        self,
        registry: LanguagePackRegistry | None = None,
        *,
        checkpoint: Path | str | None = None,
        extractor: SlotFeatureExtractor | None = None,
        config: Any | None = None,
    ) -> None:
        super().__init__(registry, extractor=extractor, config=config)
        self.checkpoint = Path(checkpoint) if checkpoint else None
        self._model: Any | None = None
        self._slots: list[str] = []
        self._load()

    def _load(self) -> None:
        if self.checkpoint is None or not self.checkpoint.is_file():
            logger.info(
                "no slot-predictor checkpoint at %s; using heuristic predictions",
                self.checkpoint,
            )
            return
        try:
            import torch

            from splm.training.slot_model import SlotScorer

            payload = torch.load(self.checkpoint, map_location="cpu", weights_only=False)
            self._slots = list(payload["slots"])
            self._model = SlotScorer(
                slot_feature_dim=payload["slot_feature_dim"],
                scalar_dim=payload["scalar_dim"],
                hidden_sizes=payload.get("hidden_sizes", [32, 16]),
            )
            self._model.load_state_dict(payload["state_dict"])
            self._model.eval()
            logger.info("loaded slot predictor from %s", self.checkpoint)
        except Exception as exc:
            logger.warning("could not load slot predictor %s: %s", self.checkpoint, exc)
            self._model = None

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def predict(self, context: SlotContext) -> SlotPrediction:
        if self._model is None:
            prediction = super().predict(context)
            return prediction.model_copy(
                update={
                    "backend": "heuristic (no trained checkpoint)",
                    "evidence": [*prediction.evidence, "neural predictor requested but untrained"],
                }
            )

        import torch

        features = self.extractor.extract(context)
        slot_inputs = torch.tensor(
            [features.slot_vector(slot) for slot in self._slots], dtype=torch.float32
        )
        scalars = torch.tensor(features.scalars(), dtype=torch.float32)

        with torch.no_grad():
            logits = self._model(slot_inputs, scalars).squeeze(-1)
            probabilities = torch.softmax(logits, dim=-1).tolist()

        distribution = {
            slot: float(probability)
            for slot, probability in zip(self._slots, probabilities)
            if probability > 1e-4
        }
        return self._finalize(
            distribution,
            features=features,
            evidence=["distribution produced by the trained slot predictor"],
            backend=self.name,
        )


def build_slot_predictor(
    config: Any | None = None, *, registry: LanguagePackRegistry | None = None
) -> HeuristicSlotPredictor:
    """Construct the configured slot predictor."""
    from splm.config import get_config

    config = config or get_config()
    registry = registry or get_registry(config.language_packs_dir)
    backend = str(config.get("app.slot_predictor.backend", "heuristic") or "heuristic").lower()

    if backend == "neural":
        checkpoint = config.get("app.slot_predictor.checkpoint")
        return NeuralSlotPredictor(
            registry,
            checkpoint=config.root / checkpoint if checkpoint else None,
            config=config,
        )
    if backend != "heuristic":
        logger.warning("unknown slot predictor backend %r; using heuristic", backend)
    return HeuristicSlotPredictor(registry, config=config)
