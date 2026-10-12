#!/usr/bin/env python3
"""Freeze parser output into a CoNLL-U fixture for the test suite.

    python scripts/make_fixtures.py

Tests need dependency trees but should not need a 500 MB parser model, nor should
they change behaviour when a model is upgraded. So the trees are captured once,
here, and committed. They are *silver* data - a parser's output, not human
annotation - which is fine for testing the frame builder's logic, and is recorded
as such in the file header.

Re-run this after deliberately changing parser version or configuration, and
review the diff: a change in these trees is a change in the tests' premises.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from splm.config import Config  # noqa: E402
from splm.logging_utils import setup_logging  # noqa: E402

SENTENCES: dict[str, list[str]] = {
    "en": [
        # spec section 40 - the Milestone 1 acceptance list
        "John works.",
        "John is tired.",
        "John owns a car.",
        "John met Sarah.",
        "John met Sarah in Paris.",
        "John met Sarah in Paris yesterday.",
        "John met Sarah in Paris yesterday by train.",
        "John met Sarah in Paris yesterday to discuss the contract.",
        # The English side of the cross-language equivalence sets. Must stay in step
        # with EQUIVALENT/LOCATED in tests/test_multilingual.py.
        "John will meet Sarah in Paris tomorrow.",
        # spec sections 3, 11, 19 - structures that must not be flattened
        "John will meet Sarah in Paris tomorrow by train to discuss the contract.",
        "The engineer deployed the application to AWS yesterday using Terraform.",
        "If John knew that Sarah might leave, he would call her.",
        "There is a problem with the deployment.",
        "The application was deployed by the engineer.",
        "John did not meet Sarah in Paris.",
        "John is in Paris.",
        "Sarah has requested today's sales report.",
        "John gave Sarah the document.",
        "John met Sarah and Mary in Paris.",
        "John met Sarah in Paris and left early.",
        "I saw the man with the telescope.",
        # incomplete prefixes - slot prediction fixtures
        "John will meet Sarah in",
        "The engineer deployed the application to AWS yesterday using",
        "John is going to",
        "She traveled to Paris because",
        "John works at",
    ],
    "fr": [
        "John rencontrera Sarah à Paris demain.",
        "John est à Paris.",
        "John rencontrera Sarah à Paris demain en train pour négocier le contrat.",
        "Jean rencontrera Sarah à",
    ],
    "vi": [
        "Ngày mai John sẽ gặp Sarah ở Paris.",
        "John đang ở Paris.",
        "Ngày mai John sẽ gặp Sarah ở Paris, đi bằng tàu để đàm phán hợp đồng.",
        "Ngày mai John sẽ gặp Sarah ở",
    ],
}

HEADER = """\
# SPLM test fixture - SILVER data, not gold annotation.
#
# Produced by scripts/make_fixtures.py from the configured parser. Committed so
# that tests of the frame builder run without a parser model and do not change
# when a model is upgraded. Regenerate deliberately and review the diff.
#
# parser: {parser}
# language: {language}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "tests" / "fixtures", help="output directory"
    )
    parser.add_argument("--languages", nargs="*", default=None)
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    setup_logging(level=args.log_level)
    config = Config.load()

    from splm.linguistic.factory import build_parser

    backend = build_parser(config)
    args.out.mkdir(parents=True, exist_ok=True)

    languages = args.languages or list(SENTENCES)
    written = 0

    for language in languages:
        sentences = SENTENCES.get(language, [])
        if not sentences:
            continue
        if not getattr(backend, "supports", lambda _: True)(language):
            print(
                f"skipping {language}: no parser model "
                f"(python scripts/download_resources.py --languages {language})",
                file=sys.stderr,
            )
            continue

        blocks: list[str] = []
        for text in sentences:
            document = backend.parse(text, language)
            if not document.sentences:
                print(f"warning: no parse for {text!r}", file=sys.stderr)
                continue
            # Keep the original string as the sentence id so tests can look it up
            # even when the parser re-tokenised or split it.
            for sentence in document.sentences:
                blocks.append(f"# input = {text}\n{sentence.to_conllu()}")

        target = args.out / f"{language}.conllu"
        target.write_text(
            HEADER.format(parser=getattr(backend, "name", "unknown"), language=language)
            + "\n"
            + "\n".join(blocks),
            encoding="utf-8",
        )
        print(f"wrote {target} ({len(blocks)} sentences)")
        written += 1

    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
