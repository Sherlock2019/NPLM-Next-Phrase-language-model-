#!/usr/bin/env python
"""Benchmark the speech lab's three modes on identical inputs.

    python scripts/speech_benchmark.py                       # built-in set, synthetic speech
    python scripts/speech_benchmark.py --languages en --limit 10
    python scripts/speech_benchmark.py --manifest data/speech/manifest.jsonl   # real recordings

Manifest lines (JSONL):
    {"id": "u1", "audio": "clips/u1.wav", "language": "en",
     "reference": "Book a meeting with Sarah tomorrow at three.",
     "entities": ["Sarah"], "numbers": ["3"],
     "slots": {"action": ["book"], "on_what": ["a meeting"]}}   # slots optional

Writes results/speech/<run_id>.json and .csv; the dashboard's Speech Lab lists them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from splm.config import Config  # noqa: E402
from splm.evaluation.store import write_result  # noqa: E402
from splm.logging_utils import setup_logging  # noqa: E402
from splm.speech.benchmark import SpeechBenchmark, load_items  # noqa: E402
from splm.speech.pipeline import SpeechPipeline  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", default=None, help="JSONL of real recordings (default: built-in synthetic set)")
    parser.add_argument("--languages", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None, help="items per language")
    parser.add_argument("--no-speak", action="store_true", help="skip TTS (no time-to-first-audio)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    setup_logging(level=args.log_level)
    config = Config.load()
    items, source = load_items(args.manifest, args.languages, args.limit)
    if not items:
        print("no benchmark items selected", file=sys.stderr)
        return 1

    report = SpeechBenchmark(SpeechPipeline(config), config).run(items, source=source, speak=not args.no_speak)
    out_dir = config.results_dir / str(config.get("speech.benchmark.results_subdir", "speech"))
    path = write_result(out_dir, report)

    print(f"\n{report['samples']} items ({source}) -> {path}")
    for mode, stats in report["per_mode"].items():
        print(f"  {mode:<15} WER {stats['corpus_wer']}  slots {stats['slot_accuracy']['percent']}%  "
              f"entities {stats['entity_preservation']['percent']}%  numbers {stats['number_preservation']['percent']}%  "
              f"gen {stats['generation_ms']} ms  TTFA {stats['time_to_first_audio_ms']} ms  "
              f"E2E {stats['end_to_end_ms']} ms  RTF {stats['rtf_end_to_end']}")
    print("\n" + "\n".join(f"- {line}" for line in report["headline"]))
    for caveat in report["caveats"]:
        print(f"! {caveat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
