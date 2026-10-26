"""The benchmark runner (spec sections 38, 56).

Every metric is measured on identical input, with the same model, the same forward
pass and the same hardware; only the re-scoring layer differs. Nothing is
extrapolated and nothing is filled in - an item that cannot be run is recorded as
skipped.

Note which metrics are comparisons and which are not. Next-word accuracy, target
rank and latency have a base-model counterpart. **Expected-slot accuracy does not**:
a plain language model makes no slot prediction, so there is nothing to compare it
against. It is reported as an SPLM-only capability measurement rather than dressed up
as a win.
"""

from __future__ import annotations

import logging
import platform
import time
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from splm.config import Config
from splm.evaluation.datasets import (
    DIAGNOSTIC_NOTE,
    MULTILINGUAL_SETS,
    TestCase,
    diagnostic_suite,
)
from splm.evaluation.metrics import (
    Comparison,
    ConfusionMatrix,
    Continuous,
    Proportion,
    RankMetrics,
    WinLossTally,
)
from splm.evaluation.store import write_result

logger = logging.getLogger(__name__)

Suite = Literal["slots", "next_word", "multilingual", "all"]


class ItemResult(BaseModel):
    """One benchmark item's outcome, for the test browser (UI spec section 28)."""

    id: str
    language: str
    kind: str
    category: str
    prompt: str
    source: str = "diagnostic"

    expected_slot: str | None = None
    predicted_slot: str | None = None
    slot_confidence: float | None = None
    slot_top3: list[str] = Field(default_factory=list)
    slot_correct: bool | None = None
    slot_correct_top3: bool | None = None

    target: str | None = None
    base_top: str | None = None
    splm_top: str | None = None
    base_correct: bool | None = None
    splm_correct: bool | None = None
    target_base_rank: int | None = None
    target_splm_rank: int | None = None
    target_boost_logits: float | None = None
    verdict: str | None = None

    semantic_focus_base: float | None = None
    semantic_focus_splm: float | None = None
    latency_ms: float | None = None
    skipped_reason: str | None = None


class BenchmarkReport(BaseModel):
    """A complete run, with its caveats attached rather than in a footnote."""

    run_id: str
    timestamp: str
    dataset: str
    dataset_note: str
    languages: list[str] = Field(default_factory=list)
    samples: int = 0
    skipped: int = 0

    model: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str = ""
    features: dict[str, bool] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    semantics_coverage: dict[str, str] = Field(default_factory=dict)

    #: SPLM-only capability: no base-model equivalent exists.
    slot_accuracy: dict[str, Any] | None = None
    slot_accuracy_top3: dict[str, Any] | None = None
    slot_by_category: dict[str, Any] = Field(default_factory=dict)
    slot_confusion: dict[str, Any] = Field(default_factory=dict)

    #: Genuine base-versus-SPLM comparisons.
    comparisons: list[dict[str, Any]] = Field(default_factory=list)
    rank_metrics: dict[str, Any] = Field(default_factory=dict)
    win_loss: dict[str, Any] = Field(default_factory=dict)
    continuous: list[dict[str, Any]] = Field(default_factory=list)
    multilingual: dict[str, Any] = Field(default_factory=dict)

    headline: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    items: list[ItemResult] = Field(default_factory=list)


class Benchmark:
    """Runs a suite and produces a :class:`BenchmarkReport`."""

    def __init__(self, config: Config | None = None, *, engine: Any | None = None) -> None:
        from splm.config import get_config

        self.config = config or get_config()
        self._engine = engine

    @property
    def engine(self) -> Any:
        if self._engine is None:
            from splm.model.engine import SPLMEngine

            self._engine = SPLMEngine(self.config)
        return self._engine

    # -- running -----------------------------------------------------------

    def run(
        self,
        *,
        languages: list[str] | None = None,
        limit: int | None = None,
        suite: Suite = "all",
        cases: list[TestCase] | None = None,
        save: bool = True,
    ) -> BenchmarkReport:
        """Run the benchmark and (by default) persist the result."""
        engine = self.engine
        # Load everything before timing anything, or the first item absorbs the
        # model-loading cost and the latency figures become fiction.
        engine.warmup()

        kinds: list[str] | None = None
        if suite == "slots":
            kinds = ["slot"]
        elif suite == "next_word":
            kinds = ["next_word"]

        selected = cases if cases is not None else diagnostic_suite(languages, kinds)  # type: ignore[arg-type]
        if limit:
            selected = selected[:limit]

        report = self._new_report(selected, languages)

        slot_correct = slot_correct_top3 = slot_total = 0
        by_category: dict[str, list[bool]] = {}
        confusion = ConfusionMatrix()

        word_total = base_word_correct = splm_word_correct = 0
        base_only = splm_only = 0
        base_ranks, splm_ranks = RankMetrics(), RankMetrics()
        tally = WinLossTally()
        focus_base: list[float] = []
        focus_splm: list[float] = []
        # Base latency is the Transformer's own forward pass - exactly the work a plain
        # language model would do. SPLM latency is that plus the structural layers.
        base_latency: list[float] = []
        splm_latency: list[float] = []

        for case in selected:
            item = ItemResult(
                id=case.id,
                language=case.language,
                kind=case.kind,
                category=case.category,
                prompt=case.prompt,
                source=case.source,
                expected_slot=case.expected_slot,
                target=case.target,
            )

            try:
                result = engine.predict(
                    case.prompt, language=case.language, target=case.target
                )
            except Exception as exc:
                item.skipped_reason = str(exc)
                report.items.append(item)
                report.skipped += 1
                logger.warning("skipped %s: %s", case.id, exc)
                continue

            splm_latency.append(result.total_latency_ms)
            base_latency.append(result.timings_ms.get("llm_inference", 0.0))
            item.latency_ms = result.total_latency_ms

            slots = result.expected_slots
            item.predicted_slot = slots.top_slot
            item.slot_confidence = slots.confidence
            item.slot_top3 = slots.top_k(3)

            if case.expected_slot:
                slot_total += 1
                correct = slots.top_slot == case.expected_slot
                item.slot_correct = correct
                item.slot_correct_top3 = slots.hits_at_k(case.expected_slot, 3)
                slot_correct += int(correct)
                slot_correct_top3 += int(item.slot_correct_top3)
                by_category.setdefault(case.category, []).append(correct)
                confusion.add(case.expected_slot, slots.top_slot)

            focus = result.semantic_focus
            if focus is not None and focus.is_reportable:
                focus_base.append(focus.base_mass)
                focus_splm.append(focus.splm_mass)
                item.semantic_focus_base = focus.base_mass
                item.semantic_focus_splm = focus.splm_mass

            base_choice, splm_choice = result.base_choice, result.splm_choice
            item.base_top = base_choice.word if base_choice else None
            item.splm_top = splm_choice.word if splm_choice else None

            if case.kind == "next_word" and case.target:
                word_total += 1
                base_hit = bool(base_choice and case.is_correct_word(base_choice.word))
                splm_hit = bool(splm_choice and case.is_correct_word(splm_choice.word))
                item.base_correct, item.splm_correct = base_hit, splm_hit
                base_word_correct += int(base_hit)
                splm_word_correct += int(splm_hit)
                if base_hit and not splm_hit:
                    base_only += 1
                elif splm_hit and not base_hit:
                    splm_only += 1

                outcome = result.target
                if outcome is not None:
                    item.target_base_rank = outcome.base_rank
                    item.target_splm_rank = outcome.splm_rank
                    item.target_boost_logits = outcome.boost_logits
                    item.verdict = outcome.verdict
                    base_ranks.add(outcome.base_rank)
                    splm_ranks.add(outcome.splm_rank)
                    tally.add(outcome.verdict)

            report.items.append(item)
            report.samples += 1

        # -- SPLM-only capability -----------------------------------------
        if slot_total:
            report.slot_accuracy = {
                **Proportion(successes=slot_correct, total=slot_total).summary(),
                "note": (
                    "MLM-only capability. A plain language model makes no semantic-slot "
                    "prediction, so there is no base-model figure to compare against."
                ),
            }
            report.slot_accuracy_top3 = Proportion(
                successes=slot_correct_top3, total=slot_total
            ).summary()
            report.slot_by_category = {
                category: Proportion(
                    successes=sum(results), total=len(results)
                ).summary()
                for category, results in sorted(by_category.items())
            }
            report.slot_confusion = {
                "labels": confusion.labels,
                "counts": confusion.counts,
                "per_slot": confusion.per_slot(),
                "common_errors": confusion.common_errors(),
            }

        # -- comparisons ---------------------------------------------------
        if word_total:
            report.comparisons.append(
                Comparison(
                    metric="next-word accuracy (top-1)",
                    base=Proportion(successes=base_word_correct, total=word_total),
                    splm=Proportion(successes=splm_word_correct, total=word_total),
                    base_only_correct=base_only,
                    splm_only_correct=splm_only,
                ).summary()
            )
            report.rank_metrics = {
                "base": base_ranks.summary(),
                "splm": splm_ranks.summary(),
                "note": (
                    "Rank of the correct answer among the re-scored candidates. Items "
                    "where the target never appeared are counted separately, never "
                    "assigned a placeholder rank."
                ),
            }
            report.win_loss = tally.summary()

        if focus_base:
            report.continuous.append(
                Continuous(
                    metric="semantic focus (probability mass on the expected slot)",
                    base_values=focus_base,
                    splm_values=focus_splm,
                    lower_is_better=False,
                    unit="proportion",
                ).summary()
            )

        if splm_latency:
            report.continuous.append(
                Continuous(
                    metric="latency per prediction (warm)",
                    base_values=base_latency,
                    splm_values=splm_latency,
                    lower_is_better=True,
                    unit="ms",
                ).summary()
            )

        if suite in {"multilingual", "all"}:
            report.multilingual = self._run_multilingual()

        report.headline = self._headline(report)
        report.caveats = self._caveats(report)

        if save:
            write_result(self.config.results_dir, report.model_dump(mode="json"))
        return report

    # -- report assembly ---------------------------------------------------

    def _new_report(
        self, cases: list[TestCase], languages: list[str] | None
    ) -> BenchmarkReport:
        from splm.device import device_report

        engine = self.engine
        registry = engine.pipeline.registry
        sources = sorted({case.source for case in cases})

        return BenchmarkReport(
            run_id=f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            dataset=", ".join(sources) or "diagnostic",
            dataset_note=DIAGNOSTIC_NOTE if "diagnostic" in sources else "",
            languages=languages or sorted({case.language for case in cases}),
            model=engine.llm.describe(),
            fingerprint=engine.fingerprint(),
            features=self.config.features,
            weights=self.config.scoring_weights,
            environment={
                "python": platform.python_version(),
                "platform": platform.platform(),
                **device_report(),
            },
            semantics_coverage={
                code: registry.get(code).semantics_coverage for code in registry.available()
            },
        )

    def _run_multilingual(self) -> dict[str, Any]:
        """Cross-language structural agreement over equivalent sentences."""
        engine = self.engine
        sets: list[dict[str, Any]] = []

        for index, group in enumerate(MULTILINGUAL_SETS):
            frames: dict[str, Any] = {}
            tokens: dict[str, int] = {}
            missing: list[str] = []

            for language, text in group.items():
                analysis = engine.pipeline.analyze(text, language=language)
                if analysis.frame is None:
                    missing.append(language)
                    continue
                frames[language] = analysis.frame
                try:
                    tokens[language] = engine.llm.token_count(text)
                except Exception:
                    pass

            agreement: dict[str, float] = {}
            codes = sorted(frames)
            for position, left in enumerate(codes):
                for right in codes[position + 1 :]:
                    agreement[f"{left}-{right}"] = frames[left].agreement_with(frames[right])

            sets.append(
                {
                    "index": index,
                    "texts": group,
                    "token_counts": tokens,
                    "agreement": agreement,
                    "missing_parser": missing,
                    "signatures": {
                        code: frame.structural_signature() for code, frame in frames.items()
                    },
                }
            )

        pairs: dict[str, list[float]] = {}
        for entry in sets:
            for pair, value in entry["agreement"].items():
                pairs.setdefault(pair, []).append(value)

        return {
            "sets": sets,
            "mean_agreement": {
                pair: round(sum(values) / len(values), 4) for pair, values in pairs.items()
            },
            "metric_note": (
                "Structural agreement only: predicate type and sense, grammatical "
                "meaning, filled slots, roles, named entities, nesting depth. Content "
                "lemmas are excluded because they are language-specific."
            ),
        }

    @staticmethod
    def _headline(report: BenchmarkReport) -> list[str]:
        """Factual statements, including unfavourable ones."""
        lines: list[str] = []
        for comparison in report.comparisons:
            lines.append(str(comparison["statement"]))

        if report.slot_accuracy:
            lines.append(
                f"expected-slot accuracy: {report.slot_accuracy['percent']:.1f}% "
                f"({report.slot_accuracy['successes']}/{report.slot_accuracy['total']}), "
                "an MLM-only capability with no base-model counterpart"
            )

        for entry in report.continuous:
            if entry["metric"].startswith("semantic focus"):
                lines.append(
                    f"semantic focus: base {entry['base_mean'] * 100:.1f}% -> "
                    f"MLM {entry['splm_mean'] * 100:.1f}% "
                    f"({(entry['splm_mean'] - entry['base_mean']) * 100:+.1f} pp "
                    f"over {entry['samples']} predictions)"
                )
            elif entry["metric"].startswith("latency"):
                overhead = entry["splm_mean"] - entry["base_mean"]
                lines.append(
                    f"latency: base forward pass {entry['base_mean']:.1f} ms, "
                    f"MLM {entry['splm_mean']:.1f} ms "
                    f"({overhead:+.1f} ms of structural overhead per prediction)"
                )

        if report.win_loss:
            lines.append(
                f"per-item outcome by {report.win_loss['criterion']}: "
                f"{report.win_loss['wins']} wins, {report.win_loss['ties']} ties, "
                f"{report.win_loss['losses']} losses"
            )
        return lines

    @staticmethod
    def _caveats(report: BenchmarkReport) -> list[str]:
        caveats: list[str] = []
        if report.dataset_note:
            caveats.append(report.dataset_note)
        if report.samples < 20:
            caveats.append(
                f"only {report.samples} items ran; too few for any statistical verdict"
            )
        seeds = [code for code, level in report.semantics_coverage.items() if level == "seed"]
        if seeds:
            caveats.append(
                "slot-compatibility data is seed-level for "
                + ", ".join(sorted(seeds))
                + ", so semantic focus and relevance figures are indicative, not decisive"
            )
        if report.skipped:
            caveats.append(f"{report.skipped} items were skipped and excluded from all metrics")
        caveats.append(
            "latency is measured warm; model and parser loading is excluded because it "
            "is paid once per process, not per prediction"
        )
        return caveats
