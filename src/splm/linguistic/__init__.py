"""Parsing, lexicon, morphology, grammar, syntax and semantic roles."""

from __future__ import annotations

from splm.linguistic.factory import build_parser
from splm.linguistic.parser import (
    LinguisticParser,
    ParsedDocument,
    ParsedSentence,
    ParserUnavailable,
    Token,
)

__all__ = [
    "build_parser",
    "LinguisticParser",
    "ParsedDocument",
    "ParsedSentence",
    "ParserUnavailable",
    "Token",
]
