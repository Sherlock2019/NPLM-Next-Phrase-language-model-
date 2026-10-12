#!/usr/bin/env python3
"""Walk through the SPLM pipeline on a fixed set of sentences.

    python scripts/demo.py                  # Milestone 1: text -> Phrase DNA
    python scripts/demo.py --stage slots    # + expected next semantic slot
    python scripts/demo.py --stage predict  # + base vs SPLM candidate re-ranking
    python scripts/demo.py --stage all --json

Sentence sets come from the spec's own milestone lists, so this doubles as a
readable smoke test of whatever has been built so far.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from splm.config import Config  # noqa: E402
from splm.logging_utils import setup_logging  # noqa: E402

# Spec section 40: these must all produce a sensible frame before anything else
# is built on top.
MILESTONE_1 = [
    "John works.",
    "John is tired.",
    "John owns a car.",
    "John met Sarah.",
    "John met Sarah in Paris.",
    "John met Sarah in Paris yesterday.",
    "John met Sarah in Paris yesterday by train.",
    "John met Sarah in Paris yesterday to discuss the contract.",
]

# Spec sections 3, 11, 19: the harder structures.
STRUCTURE = [
    "John will meet Sarah in Paris tomorrow by train to discuss the contract.",
    "The engineer deployed the application to AWS yesterday using Terraform.",
    "If John knew that Sarah might leave, he would call her.",
    "There is a problem with the deployment.",
    "The application was deployed by the engineer.",
    "John did not meet Sarah in Paris.",
    "John is in Paris.",
]

# Incomplete prefixes - what the slot predictor and the re-ranker are for.
PREFIXES = [
    "John will meet Sarah in",
    "The engineer deployed the application to AWS yesterday using",
    "John is going to",
    "She traveled to Paris because",
]

MULTILINGUAL = [
    ("en", "John will meet Sarah in Paris tomorrow."),
    ("fr", "John rencontrera Sarah à Paris demain."),
    ("vi", "Ngày mai John sẽ gặp Sarah ở Paris."),
]


def show_frames(pipeline, sentences: list[str], *, as_json: bool, tree: bool) -> int:
    from splm.phrase.serializer import to_text, to_tree

    failures = 0
    universal = pipeline.registry.universal()

    for sentence in sentences:
        print("=" * 78)
        print(sentence)
        print("=" * 78)
        analysis = pipeline.analyze(sentence)
        if not analysis.frames:
            print("  !! no frame produced")
            for warning in analysis.warnings:
                print(f"  !! {warning}")
            failures += 1
            continue
        for frame in analysis.frames:
            if as_json:
                print(json.dumps(frame.to_compact_dict(), indent=2, ensure_ascii=False))
            else:
                print(to_text(frame, universal=universal))
                if tree:
                    print()
                    print(to_tree(frame, universal=universal))
        print()
    return failures


def show_slots(pipeline, config: Config, prefixes: list[str]) -> int:
    try:
        from splm.phrase.slot_predictor import build_slot_predictor
    except ImportError:
        print("slot predictor not built yet; skipping", file=sys.stderr)
        return 0

    predictor = build_slot_predictor(config, registry=pipeline.registry)
    for prefix in prefixes:
        print("=" * 78)
        print(f"{prefix!r}")
        print("=" * 78)
        analysis = pipeline.analyze(prefix)
        prediction = predictor.predict_from_analysis(analysis)
        for slot, probability in prediction.ranked()[:5]:
            bar = "#" * int(round(probability * 40))
            print(f"  {slot:<12} {probability * 100:5.1f}%  {bar}")
        for note in prediction.evidence:
            print(f"    - {note}")
        print()
    return 0


def show_predictions(config: Config, prefixes: list[str], top: int) -> int:
    try:
        from splm.model.engine import SPLMEngine
    except ImportError:
        print("prediction engine not built yet; skipping", file=sys.stderr)
        return 0

    engine = SPLMEngine(config)
    # Load everything first: a cold call's timings are dominated by model loading and
    # would misrepresent per-prediction latency.
    load = engine.warmup()
    print(
        f"warmup: parser {load['parser_load_ms']:.0f} ms, "
        f"model {load['model_load_ms']:.0f} ms\n"
    )

    for prefix in prefixes:
        print("=" * 78)
        print(f"{prefix!r}")
        print("=" * 78)
        result = engine.predict(prefix)

        slots = result.expected_slots
        print(
            f"expected slot: {slots.top_slot.upper()} {slots.confidence * 100:.1f}% "
            f"({slots.confidence_label} confidence, "
            f"normalised entropy {slots.normalized_entropy:.2f})"
        )
        print()
        print(result.comparison_table(limit=top))

        focus = result.semantic_focus
        if focus is not None and focus.is_reportable:
            print()
            print(
                f"semantic focus on {focus.slot.upper()}: "
                f"base {focus.base_mass * 100:.1f}% -> SPLM {focus.splm_mass * 100:.1f}% "
                f"({focus.delta_percentage_points:+.1f} pp, "
                f"{focus.evaluated}/{focus.total} candidates classified)"
            )
        if result.search_space is not None:
            print()
            print("search funnel")
            for stage in result.search_space.stages:
                print(f"  {stage.count:>8}  {stage.name:<26} [{stage.label}]")
        print()
        print(
            f"latency (warm): total {result.total_latency_ms:.1f} ms, "
            f"SPLM overhead {result.splm_overhead_ms:.1f} ms"
        )
        print()
    return 0


def show_multilingual(pipeline) -> int:
    frames: dict[str, object] = {}
    for language, sentence in MULTILINGUAL:
        analysis = pipeline.analyze(sentence, language=language)
        if not analysis.frames:
            print(f"  !! {language}: no frame ({'; '.join(analysis.warnings)})")
            continue
        frames[language] = analysis.frames[0]
        print(f"--- {language}: {sentence}")
        print(json.dumps(analysis.frames[0].structural_signature(), indent=2, ensure_ascii=False))

    codes = list(frames)
    if len(codes) > 1:
        print()
        print("cross-language structural agreement")
        for i, left in enumerate(codes):
            for right in codes[i + 1 :]:
                score = frames[left].agreement_with(frames[right])  # type: ignore[attr-defined]
                print(f"  {left} <-> {right}   {score * 100:5.1f}%")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        default="frames",
        choices=["frames", "slots", "predict", "multilingual", "all"],
    )
    parser.add_argument("--json", action="store_true", help="print frames as JSON")
    parser.add_argument("--tree", action="store_true", help="also draw the semantic graph")
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    setup_logging(level=args.log_level)
    config = Config.load()

    from splm.pipeline import SPLMPipeline

    pipeline = SPLMPipeline(config)
    failures = 0

    if args.stage in {"frames", "all"}:
        failures += show_frames(
            pipeline, MILESTONE_1 + STRUCTURE, as_json=args.json, tree=args.tree
        )
    if args.stage in {"slots", "all"}:
        failures += show_slots(pipeline, config, PREFIXES)
    if args.stage in {"predict", "all"}:
        failures += show_predictions(config, PREFIXES, args.top)
    if args.stage in {"multilingual", "all"}:
        failures += show_multilingual(pipeline)

    if failures:
        print(f"\n{failures} sentence(s) produced no frame", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
