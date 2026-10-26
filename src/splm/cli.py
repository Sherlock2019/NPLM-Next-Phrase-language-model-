"""SPLM command line interface (spec section 36).

    splm parse   "John will meet Sarah in Paris tomorrow."
    splm predict "John will meet Sarah in"
    splm slots   "John will meet Sarah in"
    splm detect  "John rencontrera Sarah a Paris demain."
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from splm import __version__
from splm.config import Config
from splm.logging_utils import setup_logging


# ---------------------------------------------------------------------------
# output helpers
# ---------------------------------------------------------------------------

def _print(text: str = "") -> None:
    sys.stdout.write(text + "\n")


def _heading(text: str) -> None:
    _print()
    _print(text.upper())


def _percent_table(distribution: dict[str, float], *, limit: int | None = None) -> None:
    ranked = sorted(distribution.items(), key=lambda kv: kv[1], reverse=True)
    if limit:
        ranked = ranked[:limit]
    width = max((len(str(key)) for key, _ in ranked), default=0)
    for key, value in ranked:
        _print(f"  {str(key).ljust(width)}   {value * 100:5.1f}%")


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_parse(args: argparse.Namespace, config: Config) -> int:
    """Text -> Universal Phrase DNA. This is Milestone 1."""
    from splm.pipeline import SPLMPipeline
    from splm.phrase.serializer import to_json, to_text, to_tree

    pipeline = SPLMPipeline(config)
    analysis = pipeline.analyze(args.text, language=args.language, locale=args.locale)

    for warning in analysis.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if not analysis.frames:
        print("error: no frame produced; is a parser model installed?", file=sys.stderr)
        return 1

    if args.json:
        payload = [
            (f.to_compact_dict() if args.compact else json.loads(to_json(f)))
            for f in analysis.frames
        ]
        _print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2, ensure_ascii=False))
        return 0

    _heading("language")
    _print(
        f"  {analysis.detection.language}"
        f"  (confidence {analysis.detection.confidence:.2f},"
        f" via {analysis.detection.backend})"
    )
    if analysis.style:
        confidence = (
            f" (confidence {analysis.style_confidence:.2f})"
            if analysis.style_confidence is not None
            else ""
        )
        _heading("style")
        _print(f"  {analysis.style}{confidence}")

    universal = pipeline.registry.universal()
    for index, frame in enumerate(analysis.frames):
        _heading("phrase frame" if len(analysis.frames) == 1 else f"phrase frame {index + 1}")
        _print()
        _print(to_text(frame, universal=universal, show_confidence=args.confidence))
        if args.tree:
            _heading("semantic graph")
            _print()
            _print(to_tree(frame, universal=universal))

    if args.timings:
        _heading("timings (ms)")
        for stage, value in analysis.timings_ms.items():
            _print(f"  {stage:<8} {value:7.1f}")
    return 0


def cmd_detect(args: argparse.Namespace, config: Config) -> int:
    from splm.language.detector import LanguageDetector

    detector = LanguageDetector(config.supported_languages)
    result = detector.detect(args.text, locale=args.locale)
    if args.json:
        _print(result.model_dump_json(indent=2))
        return 0

    _heading("language")
    _print(f"  {result.language}   confidence {result.confidence:.2f}   backend {result.backend}")
    if result.script:
        _print(f"  script  {result.script}")
    _print(f"  locale  {result.locale or '(none)'}")
    if result.scores:
        _heading("candidate scores")
        _percent_table({k: min(v, 1.0) for k, v in result.scores.items()})
    return 0


def cmd_slots(args: argparse.Namespace, config: Config) -> int:
    """Show the expected next semantic slot for an incomplete sentence."""
    from splm.phrase.slot_predictor import build_slot_predictor
    from splm.pipeline import SPLMPipeline

    pipeline = SPLMPipeline(config)
    analysis = pipeline.analyze(args.text, language=args.language)
    predictor = build_slot_predictor(config, registry=pipeline.registry)
    prediction = predictor.predict_from_analysis(analysis)

    if args.json:
        _print(prediction.model_dump_json(indent=2))
        return 0

    _heading("current phrase frame")
    if analysis.frame is not None:
        from splm.phrase.serializer import to_text

        _print()
        _print(to_text(analysis.frame, universal=pipeline.registry.universal()))

    _heading("expected phrase slot")
    _percent_table(prediction.distribution, limit=args.top)
    if prediction.evidence:
        _heading("evidence")
        for item in prediction.evidence:
            _print(f"  {item}")
    return 0


def cmd_predict(args: argparse.Namespace, config: Config) -> int:
    """Base-model candidates versus SPLM-reranked candidates, side by side."""
    from splm.model.engine import SPLMEngine

    engine = SPLMEngine(config)
    result = engine.predict(args.text, language=args.language, top_k=args.top_k)

    if args.json:
        _print(result.model_dump_json(indent=2))
        return 0

    _heading("expected phrase slot")
    _percent_table(result.expected_slots.distribution, limit=4)

    _heading("base model")
    _percent_table({c.token: c.base_probability for c in result.top_base(args.top)})

    _heading("splm")
    _percent_table({c.token: c.splm_probability for c in result.top_splm(args.top)})

    if args.detail:
        _heading("score breakdown")
        _print(result.score_table(limit=args.top))

    _heading("timings (ms)")
    for stage, value in result.timings_ms.items():
        _print(f"  {stage:<10} {value:7.1f}")
    return 0


def cmd_generate(args: argparse.Namespace, config: Config) -> int:
    from splm.model.engine import SPLMEngine

    engine = SPLMEngine(config)
    base, splm = engine.generate_comparison(
        args.text, language=args.language, max_new_tokens=args.max_new_tokens
    )
    _heading("base model")
    _print(f"  {base}")
    _heading("splm")
    _print(f"  {splm}")
    return 0


def cmd_languages(args: argparse.Namespace, config: Config) -> int:
    from splm.language.packs import get_registry
    from splm.linguistic.factory import build_parser

    registry = get_registry(config.language_packs_dir)
    _heading("language packs")
    for code in registry.available():
        pack = registry.get(code)
        name = pack.grammar.get("name", code)
        parts = [
            part
            for part, present in (
                ("grammar", pack.grammar),
                ("syntax", pack.syntax),
                ("morphology", pack.morphology),
                ("styles", pack.styles),
                ("idioms", pack.idioms),
            )
            if present
        ]
        mark = "*" if code in config.supported_languages else " "
        _print(f" {mark} {code:<4} {name:<12} {', '.join(parts) or '(empty)'}")
    _print()
    _print("  * = listed in config/app.yaml as supported")

    _heading("parser models")
    try:
        parser = build_parser(config)
        available = getattr(parser, "available_languages", lambda: [])()
        _print(f"  {', '.join(available) if available else '(none downloaded)'}")
    except Exception as exc:
        _print(f"  unavailable: {exc}")
    return 0


def cmd_config(args: argparse.Namespace, config: Config) -> int:
    if args.key:
        value = config.get(args.key)
        _print(json.dumps(value, indent=2, ensure_ascii=False, default=str))
        return 0 if value is not None else 1
    _print(json.dumps(config.as_dict(), indent=2, ensure_ascii=False, default=str))
    return 0


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="splm",
        description="Meaning Language Model - explicit structure over a Transformer.",
    )
    parser.add_argument("--version", action="version", version=f"splm {__version__}")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING, ERROR")
    parser.add_argument(
        "--profile", default=None, help="model profile from config/model.yaml (tiny, small, ...)"
    )
    parser.add_argument(
        "--ablation",
        default=None,
        help="ablation preset from config/scoring.yaml (base_only, phrase_only, ...)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_text_command(name: str, help_text: str, handler: Any) -> argparse.ArgumentParser:
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("text", help="input text")
        sub.add_argument("--language", default=None, help="skip detection and use this language")
        sub.add_argument("--json", action="store_true", help="machine-readable output")
        sub.set_defaults(handler=handler)
        return sub

    parse_cmd = add_text_command("parse", "text -> Universal Phrase DNA", cmd_parse)
    parse_cmd.add_argument("--locale", default=None, help="locale tag, e.g. en-GB")
    parse_cmd.add_argument("--tree", action="store_true", help="also draw the semantic graph")
    parse_cmd.add_argument(
        "--confidence", action="store_true", help="show role confidences and runner-up roles"
    )
    parse_cmd.add_argument("--compact", action="store_true", help="smaller JSON")
    parse_cmd.add_argument("--timings", action="store_true", help="report stage timings")

    detect_cmd = add_text_command("detect", "identify the language", cmd_detect)
    detect_cmd.add_argument("--locale", default=None)

    slots_cmd = add_text_command("slots", "predict the next semantic slot", cmd_slots)
    slots_cmd.add_argument("--top", type=int, default=6)

    predict_cmd = add_text_command("predict", "base model vs MLM next-token", cmd_predict)
    predict_cmd.add_argument("--top", type=int, default=8, help="rows to display")
    predict_cmd.add_argument("--top-k", type=int, default=None, help="candidates to re-score")
    predict_cmd.add_argument("--detail", action="store_true", help="per-feature score table")

    generate_cmd = add_text_command("generate", "continue text with and without MLM", cmd_generate)
    generate_cmd.add_argument("--max-new-tokens", type=int, default=None)

    languages_cmd = subparsers.add_parser("languages", help="list packs and parser models")
    languages_cmd.set_defaults(handler=cmd_languages)

    config_cmd = subparsers.add_parser("config", help="show resolved configuration")
    config_cmd.add_argument("key", nargs="?", help="dotted key, e.g. model.model.model_id")
    config_cmd.set_defaults(handler=cmd_config)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    setup_logging(level=args.log_level)
    config = Config.load()
    if args.profile:
        config = config.with_profile(args.profile)
    if args.ablation:
        config = config.ablation(args.ablation)

    try:
        return int(args.handler(args, config) or 0)
    except KeyboardInterrupt:  # pragma: no cover
        return 130
    except Exception as exc:
        if args.log_level and args.log_level.upper() == "DEBUG":
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
