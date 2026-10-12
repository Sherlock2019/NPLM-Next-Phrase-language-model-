#!/usr/bin/env python3
"""Build the lexicon from public Wiktionary dumps, one language at a time.

    python scripts/build_lexicon.py                   # every supported language
    python scripts/build_lexicon.py --languages vi     # one language
    python scripts/build_lexicon.py --force            # re-download and rebuild

Each dump is downloaded once into data/raw/wiktionary and its source, version, licence
and date are written to data/MANIFEST.json. The running app does the same thing by
itself for a language it meets when ``app.lexicon.auto_download`` is on; this script is
the way to do it ahead of time, or with that switch off. Restart the API after a
rebuild so it reloads the words.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from splm.config import Config  # noqa: E402
from splm.linguistic.lexicon_builder import LexiconBuilder  # noqa: E402
from splm.logging_utils import setup_logging  # noqa: E402


def _progress(state: str, info: dict[str, Any]) -> None:
    if state == "downloading":
        line = f"  downloaded {info['bytes_done'] >> 20} of {info['bytes_total'] >> 20} MB"
    else:
        line = f"  {info['entries']:,} entries read"
    print(line, end="\r", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", nargs="*", default=None)
    parser.add_argument("--force", action="store_true", help="re-download the dump")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    setup_logging(level=args.log_level)
    config = Config.load()
    builder = LexiconBuilder(config)

    failures = 0
    for language in args.languages or config.supported_languages:
        if not builder.supports(language):
            print(f"{language}: no dictionary source configured", file=sys.stderr)
            failures += 1
            continue
        print(f"=== {language}: {builder.url_for(language)}")
        try:
            count = builder.build(language, force=args.force, progress=_progress)
        except Exception as exc:
            print(f"\n  failed: {exc}", file=sys.stderr)
            failures += 1
            continue
        print(f"\n  {count:,} entries in {config.database_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
