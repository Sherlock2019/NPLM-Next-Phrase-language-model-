#!/usr/bin/env python3
"""Run the SPLM benchmark and print the comparison (spec sections 38, 56).

    python scripts/benchmark.py
    python scripts/benchmark.py --suite slots --languages en
    python scripts/benchmark.py --ablation-ladder

Results are written to ``results/`` as JSON and CSV. Nothing is estimated,
extrapolated or filled in: an item that fails to run is recorded as skipped and
excluded from every metric, and a metric without enough samples reports
"insufficient data" rather than a number dressed up as a finding.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from splm.config import Config  # noqa: E402
from splm.logging_utils import setup_logging  # noqa: E402

VERDICT_LABELS = {
    "splm_improved": "MLM IMPROVED",
    "no_meaningful_difference": "NO MEANINGFUL DIFFERENCE",
    "base_better": "BASE MODEL BETTER",
    "insufficient_data": "INSUFFICIENT DATA",
}


def print_report(report) -> None:
    line = "=" * 74
    print(line)
    print(f"MLM BENCHMARK  {report.run_id}")
    print(line)
    print(f"model      : {report.model.get('model_id')}")
    print(f"device     : {report.model.get('device')}  dtype {report.model.get('dtype')}")
    print(f"dataset    : {report.dataset}")
    print(f"languages  : {', '.join(report.languages)}")
    print(f"samples    : {report.samples}   skipped: {report.skipped}")
    print(f"fingerprint: {report.fingerprint}")

    if report.slot_accuracy:
        print()
        print("EXPECTED SEMANTIC SLOT ACCURACY  (MLM-only capability)")
        print("-" * 74)
        accuracy = report.slot_accuracy
        print(
            f"  top-1  {accuracy['percent']:5.1f}%  "
            f"({accuracy['successes']}/{accuracy['total']}, "
            f"95% CI {accuracy['ci_low'] * 100:.1f}-{accuracy['ci_high'] * 100:.1f}%)"
        )
        if report.slot_accuracy_top3:
            top3 = report.slot_accuracy_top3
            print(f"  top-3  {top3['percent']:5.1f}%  ({top3['successes']}/{top3['total']})")
        print(f"  note   {accuracy.get('note', '')}")

        if report.slot_by_category:
            print()
            print("  by slot")
            for category, stats in report.slot_by_category.items():
                print(
                    f"    {category:<14} {stats['percent']:5.1f}%  "
                    f"({stats['successes']}/{stats['total']})"
                )

        errors = (report.slot_confusion or {}).get("common_errors") or []
        if errors:
            print()
            print("  most common confusions")
            for error in errors[:5]:
                print(f"    {error['true']} -> {error['predicted']}   x{error['count']}")

    if report.comparisons:
        print()
        print("BASE MODEL vs MLM")
        print("-" * 74)
        for comparison in report.comparisons:
            base, splm = comparison["base"], comparison["splm"]
            print(f"  {comparison['metric']}")
            print(
                f"    base {base['percent']:5.1f}%   splm {splm['percent']:5.1f}%   "
                f"{comparison['difference_pp']:+.1f} pp"
            )
            p = comparison["p_value"]
            print(
                f"    n={splm['total']}  "
                f"discordant {comparison['base_only_correct']}/{comparison['splm_only_correct']}  "
                f"p={'n/a' if p is None else f'{p:.3f}'}"
            )
            print(f"    -> {VERDICT_LABELS.get(comparison['verdict'], comparison['verdict'])}")

    if report.rank_metrics:
        print()
        print("RANK OF THE CORRECT ANSWER")
        print("-" * 74)
        for arm in ("base", "splm"):
            stats = report.rank_metrics.get(arm, {})
            print(
                f"  {arm:<5} mean rank {stats.get('mean_rank')}   MRR {stats.get('mrr')}   "
                f"top-1 {stats.get('top_1', {}).get('percent')}%   "
                f"not found {stats.get('not_found')}"
            )

    if report.win_loss:
        print()
        print(f"PER-ITEM OUTCOME  (criterion: {report.win_loss['criterion']})")
        print("-" * 74)
        print(
            f"  MLM better {report.win_loss['wins']}   "
            f"tie {report.win_loss['ties']}   "
            f"base better {report.win_loss['losses']}"
        )

    if report.continuous:
        print()
        print("CONTINUOUS MEASURES")
        print("-" * 74)
        for entry in report.continuous:
            direction = "lower is better" if entry["lower_is_better"] else "higher is better"
            print(f"  {entry['metric']}  ({direction})")
            print(
                f"    base {entry['base_mean']:.3f}{entry['unit']}   "
                f"splm {entry['splm_mean']:.3f}{entry['unit']}   "
                f"diff {entry['difference']:+.3f}   n={entry['samples']}"
            )

    multilingual = report.multilingual or {}
    if multilingual.get("mean_agreement"):
        print()
        print("CROSS-LANGUAGE STRUCTURAL CONSISTENCY")
        print("-" * 74)
        for pair, value in multilingual["mean_agreement"].items():
            print(f"  {pair}  {value * 100:5.1f}%")
        print(f"  {multilingual.get('metric_note', '')}")

    print()
    print("HEADLINE")
    print("-" * 74)
    for statement in report.headline:
        print(f"  {statement}")

    print()
    print("CAVEATS")
    print("-" * 74)
    for caveat in report.caveats:
        print(f"  - {caveat}")
    print()
    print(f"written to results/{report.run_id}.json")


def run_ablation_ladder(config: Config, limit: int | None) -> int:
    """Run the same suite under each ablation preset (spec section 39)."""
    from splm.evaluation.benchmark import Benchmark
    from splm.model.engine import SPLMEngine

    ladder = [
        ("LLM only", "base_only"),
        ("+ grammar", "grammar_only"),
        ("+ syntax", "syntax_only"),
        ("+ Phrase DNA", "phrase_only"),
        ("+ Phrase DNA + grammar", "phrase_grammar"),
        ("everything", "everything"),
    ]

    shared = SPLMEngine(config)
    shared.warmup()

    print("=" * 74)
    print("ABLATION LADDER")
    print("=" * 74)
    print(f"{'configuration':<26}{'next-word':>12}{'slot acc':>11}{'focus':>9}{'latency':>10}")
    print("-" * 74)

    for label, preset in ladder:
        variant = config.ablation(preset)
        engine = SPLMEngine(
            variant, pipeline=shared.pipeline, llm=shared.llm, lexicon=shared.lexicon
        )
        engine.warmup()
        report = Benchmark(variant, engine=engine).run(limit=limit, save=False)

        next_word = next(
            (c for c in report.comparisons if c["metric"].startswith("next-word")), None
        )
        focus = next(
            (c for c in report.continuous if c["metric"].startswith("semantic focus")), None
        )
        latency = next(
            (c for c in report.continuous if c["metric"].startswith("latency")), None
        )

        print(
            f"{label:<26}"
            f"{(next_word['splm']['percent'] if next_word else 0):>11.1f}%"
            f"{(report.slot_accuracy['percent'] if report.slot_accuracy else 0):>10.1f}%"
            f"{(focus['splm_mean'] * 100 if focus else 0):>8.1f}%"
            f"{(latency['splm_mean'] if latency else 0):>9.1f}ms"
        )

    print()
    print(
        "  Slot accuracy is unaffected by scoring ablations by construction: the slot\n"
        "  predictor runs before candidate scoring. It is shown so that is visible\n"
        "  rather than mistaken for a result."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="all", choices=["slots", "next_word", "multilingual", "all"])
    parser.add_argument("--languages", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--ablation-ladder", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    setup_logging(level=args.log_level)
    config = Config.load()

    if args.ablation_ladder:
        return run_ablation_ladder(config, args.limit)

    from splm.evaluation.benchmark import Benchmark

    report = Benchmark(config).run(
        languages=args.languages,
        limit=args.limit,
        suite=args.suite,
        save=not args.no_save,
    )
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
