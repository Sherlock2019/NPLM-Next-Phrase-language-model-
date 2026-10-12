"""Rendering Universal Phrase Frames for humans and for machines.

The CLI output format is the one in spec section 36; the tree form is section 32's
semantic graph view. Slot labels come from the universal language pack, so nothing
here hard-codes a question word.
"""

from __future__ import annotations

import json
from typing import Any

from splm.language.packs import UniversalPack, get_registry
from splm.phrase.schema import ELEMENT_SLOTS, FrameElement, UniversalPhraseFrame

INDENT = "  "


def to_json(frame: UniversalPhraseFrame, *, indent: int = 2, compact: bool = False) -> str:
    """Serialise a frame to JSON.

    ``compact=True`` drops empty slots and internal bookkeeping, which is what
    tests and logs want; the full form round-trips back into the Pydantic model.
    """
    payload = frame.to_compact_dict() if compact else frame.model_dump(mode="json", exclude_none=True)
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def to_text(
    frame: UniversalPhraseFrame,
    *,
    universal: UniversalPack | None = None,
    show_confidence: bool = False,
) -> str:
    """Render a frame in the question-labelled form of spec section 36."""
    universal = universal or get_registry().universal()
    lines: list[str] = []
    _render_frame(frame, universal, lines, depth=0, show_confidence=show_confidence)
    return "\n".join(lines)


def _render_frame(
    frame: UniversalPhraseFrame,
    universal: UniversalPack,
    lines: list[str],
    *,
    depth: int,
    show_confidence: bool,
) -> None:
    pad = INDENT * depth

    if frame.predicate is not None:
        label = (
            universal.predicate_types.get(frame.predicate.type.value, {}).get(
                "frame_label", frame.predicate.type.value
            )
        )
        sense = f"  ({frame.predicate.sense})" if frame.predicate.sense else ""
        lines.append(f"{pad}{label}:")
        lines.append(f"{pad}{INDENT}{frame.predicate.lemma}{sense}")

    order = universal.slot_order or list(ELEMENT_SLOTS)
    for slot in order:
        if slot == "predicate":
            continue
        elements = frame.slot(slot)
        if not elements:
            continue
        lines.append(f"{pad}{universal.question_for_slot(slot)}:")
        for element in elements:
            lines.append(f"{pad}{INDENT}{_element_line(element, show_confidence)}")
            if element.frame is not None:
                _render_frame(
                    element.frame,
                    universal,
                    lines,
                    depth=depth + 2,
                    show_confidence=show_confidence,
                )

    grammar = _grammar_line(frame)
    if grammar:
        lines.append(f"{pad}GRAMMAR:")
        lines.append(f"{pad}{INDENT}{grammar}")

    if frame.unresolved_slots:
        questions = ", ".join(universal.question_for_slot(s) for s in frame.unresolved_slots)
        lines.append(f"{pad}NOT STATED:")
        lines.append(f"{pad}{INDENT}{questions}")

    for child in frame.children:
        lines.append(f"{pad}AND ALSO:")
        _render_frame(child, universal, lines, depth=depth + 1, show_confidence=show_confidence)


def _element_line(element: FrameElement, show_confidence: bool) -> str:
    text = element.text or "(empty)"
    parts = [text]
    if element.semantic_role:
        parts.append(f"[{element.semantic_role}]")
    if show_confidence:
        parts.append(f"{element.confidence:.2f}")
        if element.alternatives:
            alternatives = " ".join(
                f"{alt.role}={alt.probability:.2f}" for alt in element.alternatives
            )
            parts.append(f"(also {alternatives})")
    for key, value in element.annotations.items():
        parts.append(f"{{{key}={value}}}")
    return " ".join(parts)


def _grammar_line(frame: UniversalPhraseFrame) -> str:
    bits: list[str] = []
    for key in ("tense", "aspect", "modality", "voice"):
        value = getattr(frame, key)
        if value is None:
            continue
        bits.append(f"{key}={getattr(value, 'value', value)}")
    if frame.negation:
        bits.append("negated")
    if frame.certainty is not None:
        bits.append(f"certainty={frame.certainty:.2f}")
    if frame.intent and frame.intent != "statement":
        bits.append(f"intent={frame.intent}")
    return "  ".join(bits)


def to_tree(frame: UniversalPhraseFrame, *, universal: UniversalPack | None = None) -> str:
    """Render the frame as the semantic graph of spec section 32.

    Shows relationships radiating from the predicate rather than a word sequence -
    the point being that the representation is a graph, not a sentence template.
    """
    universal = universal or get_registry().universal()
    lines: list[str] = []
    _render_tree(frame, universal, lines, prefix="", is_last=True, root=True)
    return "\n".join(lines)


def _render_tree(
    frame: UniversalPhraseFrame,
    universal: UniversalPack,
    lines: list[str],
    *,
    prefix: str,
    is_last: bool,
    root: bool,
) -> None:
    head = (
        f"{frame.predicate.type.value}({frame.predicate.lemma})"
        if frame.predicate
        else "FRAME(?)"
    )
    if root:
        lines.append(head)
        child_prefix = ""
    else:
        connector = "`-- " if is_last else "|-- "
        lines.append(f"{prefix}{connector}{head}")
        child_prefix = prefix + ("    " if is_last else "|   ")

    entries: list[tuple[str, FrameElement]] = [
        (slot, element)
        for slot in (universal.slot_order or list(ELEMENT_SLOTS))
        if slot != "predicate"
        for element in frame.slot(slot)
    ]
    branches: list[Any] = [*entries, *frame.children]

    for position, branch in enumerate(branches):
        last = position == len(branches) - 1
        connector = "`-- " if last else "|-- "
        if isinstance(branch, tuple):
            slot, element = branch
            lines.append(
                f"{child_prefix}{connector}{element.semantic_role} = {element.text or '?'}"
            )
            if element.frame is not None:
                _render_tree(
                    element.frame,
                    universal,
                    lines,
                    prefix=child_prefix + ("    " if last else "|   "),
                    is_last=True,
                    root=False,
                )
        else:
            _render_tree(
                branch, universal, lines, prefix=child_prefix, is_last=last, root=False
            )


def to_rows(frame: UniversalPhraseFrame) -> list[dict[str, Any]]:
    """Flatten a frame into table rows, for the debugging UI and CSV export."""
    rows: list[dict[str, Any]] = []

    def walk(current: UniversalPhraseFrame, path: str) -> None:
        for slot, element in current.elements():
            rows.append(
                {
                    "path": path or "root",
                    "slot": slot,
                    "role": element.semantic_role,
                    "text": element.text,
                    "head_lemma": element.head_lemma,
                    "confidence": round(element.confidence, 4),
                    "entity_type": element.entity_type,
                    "deprel": element.deprel,
                    "alternatives": ", ".join(
                        f"{a.role}:{a.probability:.2f}" for a in element.alternatives
                    ),
                    "annotations": json.dumps(element.annotations) if element.annotations else "",
                }
            )
            if element.frame is not None:
                walk(element.frame, f"{path}/{slot}" if path else slot)
        for index, child in enumerate(current.children):
            walk(child, f"{path}/coord{index}" if path else f"coord{index}")

    walk(frame, "")
    return rows
