"""Universal Phrase DNA: schema, builder, slot prediction and serialisation."""

from __future__ import annotations

from splm.phrase.builder import PhraseFrameBuilder
from splm.phrase.schema import (
    ALL_SLOTS,
    ELEMENT_SLOTS,
    Aspect,
    FrameElement,
    Predicate,
    PredicateType,
    Tense,
    UniversalPhraseFrame,
    Voice,
)
from splm.phrase.serializer import to_json, to_rows, to_text, to_tree

__all__ = [
    "ALL_SLOTS",
    "ELEMENT_SLOTS",
    "Aspect",
    "FrameElement",
    "PhraseFrameBuilder",
    "Predicate",
    "PredicateType",
    "Tense",
    "UniversalPhraseFrame",
    "Voice",
    "to_json",
    "to_rows",
    "to_text",
    "to_tree",
]
