"""The SPLM prediction engine (spec sections 29, 43, 55).

Runs the full cycle for one prediction step:

    text -> language -> parse -> Phrase DNA -> expected slot
         -> base-model candidates -> feature extraction -> re-scoring
         -> adjusted logits -> next token

and returns everything needed to *explain and measure* the step, not just its
answer. Base and SPLM figures always come from the same forward pass, so any
difference between the two columns is the structural layer and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from splm.config import Config, get_config
from splm.model.advantage import (
    CandidateRelevance,
    MassByCategory,
    SearchSpace,
    SemanticFocus,
    TargetOutcome,
    compute_mass_by_category,
    compute_relevance,
    compute_search_space,
    compute_semantic_focus,
    compute_target_outcome,
    frame_completion,
)
from splm.model.base_llm import BaseLanguageModel
from splm.model.candidate_features import ScoringContext
from splm.model.candidate_scorer import CandidateScore, PhraseCandidateScorer
from splm.linguistic.lexicon_builder import lexicon_status
from splm.model.word_tracker import WordCandidateTracker, build_trie_from_lexicon
from splm.phrase.schema import UniversalPhraseFrame
from splm.phrase.slot_predictor import SlotContext, SlotPrediction, build_slot_predictor

logger = logging.getLogger(__name__)


class PredictionResult(BaseModel):
    """One prediction step, fully instrumented."""

    text: str
    language: str
    style: str | None = None

    frame: UniversalPhraseFrame | None = None
    frame_completion: float = 0.0
    expected_slots: SlotPrediction = Field(default_factory=SlotPrediction)
    candidates: list[CandidateScore] = Field(default_factory=list)

    search_space: SearchSpace | None = None
    semantic_focus: SemanticFocus | None = None
    relevance: CandidateRelevance | None = None
    mass_by_category: MassByCategory | None = None
    target: TargetOutcome | None = None

    timings_ms: dict[str, float] = Field(default_factory=dict)
    warm: bool = Field(
        default=True,
        description=(
            "False when this call also loaded the parser or the model. Cold timings "
            "include one-off loading and must not be reported as per-prediction latency."
        ),
    )
    warnings: list[str] = Field(default_factory=list)
    fingerprint: str = ""
    semantics_coverage: str = "seed"

    # -- views -------------------------------------------------------------

    def top_base(self, n: int = 10) -> list[CandidateScore]:
        return sorted(self.candidates, key=lambda c: c.base_rank)[:n]

    def top_splm(self, n: int = 10) -> list[CandidateScore]:
        return sorted(self.candidates, key=lambda c: c.splm_rank)[:n]

    @property
    def base_choice(self) -> CandidateScore | None:
        return self.top_base(1)[0] if self.candidates else None

    @property
    def splm_choice(self) -> CandidateScore | None:
        return self.top_splm(1)[0] if self.candidates else None

    @property
    def changed_selection(self) -> bool:
        base, splm = self.base_choice, self.splm_choice
        return bool(base and splm and base.token_id != splm.token_id)

    def rank_changes(self, limit: int = 10) -> list[CandidateScore]:
        """Candidates whose rank moved most, largest movement first."""
        moved = [c for c in self.candidates if c.rank_change != 0]
        return sorted(moved, key=lambda c: abs(c.rank_change), reverse=True)[:limit]

    @property
    def total_latency_ms(self) -> float:
        return round(sum(self.timings_ms.values()), 2)

    @property
    def splm_overhead_ms(self) -> float:
        """Everything except the base model's own forward pass."""
        return round(
            sum(value for key, value in self.timings_ms.items() if key != "llm_inference"), 2
        )

    # -- text rendering ----------------------------------------------------

    def comparison_table(self, limit: int = 10) -> str:
        """Base versus SPLM, side by side (spec section 36)."""
        base = self.top_base(limit)
        splm = self.top_splm(limit)
        lines = [
            f"{'BASE MODEL':<28}   {'MLM':<28}",
            f"{'-' * 28}   {'-' * 28}",
        ]
        for left, right in zip(base, splm):
            arrow = ""
            if right.rank_change > 0:
                arrow = f" ^{right.rank_change}"
            elif right.rank_change < 0:
                arrow = f" v{abs(right.rank_change)}"
            lines.append(
                f"{left.word or left.token:<16}{left.base_probability * 100:6.1f}%   "
                f"{right.word or right.token:<16}{right.splm_probability * 100:6.1f}%{arrow}"
            )
        return "\n".join(lines)

    def score_table(self, limit: int = 8) -> str:
        """Per-feature score table (spec section 37)."""
        header = (
            f"{'TOKEN':<14}{'LLM':>7}{'PHRASE':>8}{'GRAM':>7}{'SYNTAX':>8}"
            f"{'MORPH':>7}{'SEM':>7}{'LEX':>7}{'STYLE':>7}{'CTX':>7}{'DELTA':>8}"
        )
        lines = [header, "-" * len(header)]
        for score in self.top_splm(limit):
            features = score.features
            if features is None:
                continue
            lines.append(
                f"{(score.word or score.token)[:13]:<14}"
                f"{features.llm:>7.2f}{features.phrase_slot:>8.2f}{features.grammar:>7.2f}"
                f"{features.syntax:>8.2f}{features.morphology:>7.2f}{features.semantic:>7.2f}"
                f"{features.lexicon:>7.2f}{features.style:>7.2f}{features.context:>7.2f}"
                f"{score.delta_logit:>+8.2f}"
            )
        return "\n".join(lines)


class SPLMEngine:
    """Orchestrates the structural layers and the base Transformer."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        pipeline: Any | None = None,
        llm: BaseLanguageModel | None = None,
        scorer: PhraseCandidateScorer | None = None,
        slot_predictor: Any | None = None,
        lexicon: Any | None = None,
    ) -> None:
        self.config = config or get_config()
        self._pipeline = pipeline
        self._llm = llm
        self._scorer = scorer
        self._slot_predictor = slot_predictor
        self.lexicon = lexicon
        self._tries: dict[str, Any] = {}

    # -- lazily built components ------------------------------------------

    @property
    def pipeline(self) -> Any:
        if self._pipeline is None:
            from splm.pipeline import SPLMPipeline

            self._pipeline = SPLMPipeline(self.config)
        return self._pipeline

    @property
    def llm(self) -> BaseLanguageModel:
        if self._llm is None:
            self._llm = BaseLanguageModel.from_config(self.config)
        return self._llm

    @property
    def scorer(self) -> PhraseCandidateScorer:
        if self._scorer is None:
            self._scorer = PhraseCandidateScorer.from_config(
                self.config, registry=self.pipeline.registry, lexicon=self.lexicon
            )
        return self._scorer

    @property
    def slot_predictor(self) -> Any:
        if self._slot_predictor is None:
            self._slot_predictor = build_slot_predictor(
                self.config, registry=self.pipeline.registry
            )
        return self._slot_predictor

    # -- warmup ------------------------------------------------------------

    @property
    def is_warm(self) -> bool:
        """Whether the parser and the model are both already loaded."""
        return self._warmed

    _warmed: bool = False

    def warmup(self, language: str | None = None) -> dict[str, float]:
        """Load the parser and the model up front.

        Latency figures are meaningless otherwise: a first call carries seconds of
        one-off loading that would otherwise be reported as per-prediction cost. The
        API calls this at startup and benchmarks call it before timing anything.
        """
        timings: dict[str, float] = {}
        language = language or self.config.default_language

        started = time.perf_counter()
        try:
            self.pipeline.analyze("Warmup sentence.", language=language)
        except Exception as exc:
            logger.warning("parser warmup failed: %s", exc)
        timings["parser_load_ms"] = round((time.perf_counter() - started) * 1000, 1)

        started = time.perf_counter()
        try:
            self.llm.load()
            self.llm.get_top_candidates("Warmup", k=8)
        except Exception as exc:
            logger.warning("model warmup failed: %s", exc)
        timings["model_load_ms"] = round((time.perf_counter() - started) * 1000, 1)

        self._warmed = True
        logger.info(
            "warmup complete: parser %.0f ms, model %.0f ms",
            timings["parser_load_ms"],
            timings["model_load_ms"],
        )
        return timings

    def _tracker(self, language: str, text: str) -> WordCandidateTracker:
        """A word tracker whose trie is built once per language."""
        if language not in self._tries:
            if self.lexicon is None:
                from splm.linguistic.lexicon import open_lexicon

                self.lexicon = open_lexicon(self.config)
            trie = build_trie_from_lexicon(self.lexicon, language)
            if not trie:
                # Not kept: the language's dictionary may still be loading, and it
                # should be picked up as soon as it is there.
                return WordCandidateTracker(trie, language=language).reset(text)
            self._tries[language] = trie
        return WordCandidateTracker(self._tries[language], language=language).reset(text)

    # -- reproducibility ---------------------------------------------------

    def fingerprint(self) -> str:
        """A short hash of everything that affects a result (spec section 39)."""
        payload = {
            "model": self.config.model,
            "weights": self.config.scoring_weights,
            "features": self.config.features,
            "scoring": self.config.get("scoring.scoring", {}),
            "slot_backend": self.config.get("app.slot_predictor.backend"),
            "scorer_backend": self.config.get("scoring.backend"),
            "parser": self.config.get("app.parser.backend"),
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:12]

    def describe(self) -> dict[str, Any]:
        """System and model information for the UI's info page (spec section 32)."""
        registry = self.pipeline.registry
        packs = {
            code: {
                "version": registry.get(code).grammar.get("version"),
                "semantics_coverage": registry.get(code).semantics_coverage,
            }
            for code in registry.available()
        }
        return {
            "model": self.llm.describe(),
            "fingerprint": self.fingerprint(),
            "weights": self.config.scoring_weights,
            "features": self.config.features,
            "scorer_backend": getattr(self.scorer.backend, "name", "unknown"),
            "scorer_trained": getattr(self.scorer.backend, "is_trained", False),
            "slot_backend": getattr(self.slot_predictor, "name", "unknown"),
            "slot_trained": getattr(self.slot_predictor, "is_trained", False),
            "language_packs": packs,
            "universal_pack_version": registry.universal().semantic_roles.get("version"),
            "lexicon": {
                **(self.lexicon.describe() if self.lexicon is not None else {"available": False}),
                "loading": lexicon_status(self.config),
            },
        }

    # -- prediction --------------------------------------------------------

    def predict(
        self,
        text: str,
        *,
        language: str | None = None,
        style: str | None = None,
        top_k: int | None = None,
        target: str | None = None,
        relevance_top_k: int = 10,
    ) -> PredictionResult:
        """Predict the next token, with the base model's view alongside SPLM's."""
        timings: dict[str, float] = {}
        was_warm = self._warmed

        started = time.perf_counter()
        analysis = self.pipeline.analyze(text, language=language, style=style)
        timings["language_analysis"] = round(
            analysis.timings_ms.get("detect", 0.0) + analysis.timings_ms.get("style", 0.0), 2
        )
        timings["phrase_parse"] = round(
            analysis.timings_ms.get("parse", 0.0) + analysis.timings_ms.get("frames", 0.0), 2
        )
        if not analysis.parsed:
            timings["phrase_parse"] = round((time.perf_counter() - started) * 1000, 2)

        started = time.perf_counter()
        slots = self.slot_predictor.predict(
            SlotContext(
                text=text,
                language=analysis.language,
                frame=analysis.frame,
                sentence=analysis.sentence,
                style=analysis.style,
            )
        )
        timings["slot_prediction"] = round((time.perf_counter() - started) * 1000, 2)

        k = int(top_k or self.llm.top_k_candidates)
        started = time.perf_counter()
        candidates = self.llm.get_top_candidates(text, k=k)
        timings["llm_inference"] = round((time.perf_counter() - started) * 1000, 2)

        started = time.perf_counter()
        context = ScoringContext(
            text=text,
            language=analysis.language,
            frame=analysis.frame,
            slots=slots,
            style=analysis.style,
            context_graph=getattr(self.pipeline, "context_graph", None),
            tracker=self._tracker(analysis.language, text),
            trailing_word=self._trailing_word(text),
            trailing_pos=self._trailing_pos(analysis),
        )
        scored = self.scorer.score_candidates(candidates, context)
        timings["candidate_scoring"] = round((time.perf_counter() - started) * 1000, 2)

        pack = self.pipeline.registry.get(analysis.language)
        result = PredictionResult(
            text=text,
            language=analysis.language,
            style=analysis.style,
            frame=analysis.frame,
            frame_completion=frame_completion(analysis.frame),
            expected_slots=slots,
            candidates=scored,
            search_space=compute_search_space(scored, slots, self.llm.vocab_size),
            semantic_focus=compute_semantic_focus(scored, slots),
            relevance=compute_relevance(scored, slots, top_k=relevance_top_k),
            mass_by_category=compute_mass_by_category(scored),
            target=compute_target_outcome(scored, target) if target else None,
            timings_ms=timings,
            warm=was_warm,
            warnings=list(analysis.warnings),
            fingerprint=self.fingerprint(),
            semantics_coverage=pack.semantics_coverage,
        )
        if not was_warm:
            self._warmed = True
            result.warnings.append(
                "cold call: these timings include one-off parser and model loading; "
                "call warmup() before measuring latency"
            )
        return result

    @staticmethod
    def _trailing_word(text: str) -> str | None:
        stripped = text.rstrip()
        if not stripped:
            return None
        words = stripped.split()
        return words[-1].lower().strip(".,;:!?\"'") if words else None

    @staticmethod
    def _trailing_pos(analysis: Any) -> str | None:
        sentence = analysis.sentence
        if sentence is None or not sentence.tokens:
            return None
        return sentence.tokens[-1].upos

    # -- generation --------------------------------------------------------

    def generate(
        self,
        text: str,
        *,
        language: str | None = None,
        max_new_tokens: int | None = None,
        use_splm: bool = True,
        **kwargs: Any,
    ) -> str:
        """Continue ``text``, optionally with SPLM re-scoring active."""
        from splm.model.logits_processor import PhraseLanguageLogitsProcessor

        options = dict(kwargs)
        if max_new_tokens is not None:
            options["max_new_tokens"] = max_new_tokens

        if not use_splm:
            return self.llm.generate(text, **options)

        processor = PhraseLanguageLogitsProcessor(engine=self, prompt=text, language=language)
        return self.llm.generate(text, logits_processor=processor, **options)

    def generate_comparison(
        self,
        text: str,
        *,
        language: str | None = None,
        max_new_tokens: int | None = None,
        **kwargs: Any,
    ) -> tuple[str, str]:
        """Generate twice from identical settings - once plain, once with SPLM.

        Same model, prompt, decoding configuration and hardware; the only difference
        is the re-scoring layer (spec section 38).
        """
        base = self.generate(
            text, max_new_tokens=max_new_tokens, use_splm=False, **kwargs
        )
        splm = self.generate(
            text, language=language, max_new_tokens=max_new_tokens, use_splm=True, **kwargs
        )
        return base, splm
