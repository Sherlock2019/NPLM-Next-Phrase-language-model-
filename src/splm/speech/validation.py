"""Semantic transcript validation: choose among Whisper's n-best with Phrase DNA.

For each hypothesis the transcript is sorted into Phrase DNA, and scored on

* acoustic   - Whisper's own length-normalised log-probability;
* predicate  - whether a predicate (action/status) was found at all;
* completeness - share of DNA categories filled;
* unresolved - categories the predicate expects but the text leaves empty;
* consensus  - how many hypotheses agree on its critical items (named entities
               and numbers). A name or a number that only one hypothesis hears is
               the classic ASR error that changes meaning.

A hypothesis may replace Whisper's top-1 only when its acoustic score is within
``max_acoustic_gap`` of it: validation re-ranks near-ties, it never overrides
clearly heard audio. Whether this lowers WER is an empirical question answered by
``scripts/speech_benchmark.py``, not assumed here.
"""

from __future__ import annotations

from typing import Callable, Sequence

from pydantic import BaseModel, Field

from splm.speech.asr import Hypothesis
from splm.speech.dna import DnaSort
from splm.speech.metrics import extract_numbers, normalize

_ENTITY_TYPES = {"PERSON", "LOCATION", "ORG", "FACILITY", "GPE", "PRODUCT", "EVENT", "DATE", "TIME"}

DEFAULT_WEIGHTS = {"acoustic": 1.0, "predicate": 0.6, "completeness": 0.4, "unresolved": 0.3, "consensus": 0.8}


class CriticalItem(BaseModel):
    text: str
    kind: str  # entity | number
    agreement: float = Field(description="Share of hypotheses containing it")


class ScoredHypothesis(BaseModel):
    text: str
    rank: int
    acoustic: float
    has_predicate: bool
    completeness: float
    unresolved: int
    consensus: float
    total: float
    eligible: bool
    critical: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    chosen: str
    chosen_rank: int
    changed: bool
    scored: list[ScoredHypothesis] = Field(default_factory=list)
    critical_items: list[CriticalItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0


def critical_items(sort: DnaSort, text: str, language: str | None) -> list[tuple[str, str]]:
    """Named entities from the DNA plus every number in the text."""
    items: list[tuple[str, str]] = []
    for category in sort.categories:
        for item in category.items:
            if item.entity_type and item.entity_type.upper() in _ENTITY_TYPES:
                items.append((normalize(item.text), "entity"))
    items.extend((number, "number") for number in extract_numbers(text, language))
    seen: set[tuple[str, str]] = set()
    return [x for x in items if x[0] and not (x in seen or seen.add(x))]


def core_gaps(sort: DnaSort) -> int:
    """Missing core meaning: no action/status, no subject (except commands), no object
    the predicate expects. WHERE/WHEN/HOW gaps are not errors - a sentence is complete
    without them - so they are not penalised. A hypothesis with no predicate at all
    counts every core gap, so it can never win by having nothing to be missing."""
    gaps = 0
    if not sort.texts("action"):
        gaps += 1
        gaps += 0 if sort.texts("who") else 1
        return gaps + (0 if sort.texts("on_what") else 1)
    who, on_what = sort.category("who"), sort.category("on_what")
    if who is not None and who.missing and sort.intent != "command":
        gaps += 1
    if on_what is not None and on_what.missing:
        gaps += 1
    return gaps


def validate(
    hypotheses: Sequence[Hypothesis],
    analyse: Callable[[str], DnaSort],
    *,
    language: str | None = None,
    weights: dict[str, float] | None = None,
    max_acoustic_gap: float = 1.5,
) -> tuple[ValidationResult, dict[str, DnaSort]]:
    """Re-rank ``hypotheses``; returns the result and each hypothesis's DNA sort."""
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    if not hypotheses:
        return ValidationResult(chosen="", chosen_rank=0, changed=False,
                                warnings=["no ASR hypotheses"]), {}

    sorts = {h.text: analyse(h.text) for h in hypotheses}
    criticals = {h.text: critical_items(sorts[h.text], h.text, language) for h in hypotheses}

    # Agreement of each critical item across hypotheses (by surface, number by value).
    counts: dict[tuple[str, str], int] = {}
    for h in hypotheses:
        normalised = f" {normalize(h.text)} "
        numbers = extract_numbers(h.text, language)
        for key in {item for items in criticals.values() for item in items}:
            text, kind = key
            present = text in numbers if kind == "number" else f" {text} " in normalised
            if present:
                counts[key] = counts.get(key, 0) + 1
    total = len(hypotheses)
    agreement = {key: count / total for key, count in counts.items()}

    top_score = hypotheses[0].score
    scored: list[ScoredHypothesis] = []
    for h in hypotheses:
        sort = sorts[h.text]
        items = criticals[h.text]
        consensus = sum(agreement.get(i, 0.0) for i in items) / len(items) if items else 1.0
        has_predicate = bool(sort.texts("action"))
        unresolved = core_gaps(sort)
        value = (
            weights["acoustic"] * h.score
            + weights["predicate"] * float(has_predicate)
            + weights["completeness"] * sort.completeness
            - weights["unresolved"] * unresolved
            + weights["consensus"] * consensus
        )
        scored.append(ScoredHypothesis(
            text=h.text, rank=h.rank, acoustic=h.score, has_predicate=has_predicate,
            completeness=sort.completeness, unresolved=unresolved,
            consensus=round(consensus, 4), total=round(value, 4),
            eligible=(top_score - h.score) <= max_acoustic_gap,
            critical=[text for text, _ in items],
        ))

    best = max((s for s in scored if s.eligible), key=lambda s: s.total)
    top_items = criticals[hypotheses[0].text]
    warnings = [
        f"uncertain {kind} '{text}': heard in {counts.get((text, kind), 0)}/{total} hypotheses"
        for text, kind in top_items
        if agreement.get((text, kind), 0.0) < 0.5
    ]
    items = [
        CriticalItem(text=text, kind=kind, agreement=round(agreement.get((text, kind), 0.0), 4))
        for text, kind in sorted({i for v in criticals.values() for i in v})
    ]
    return ValidationResult(
        chosen=best.text,
        chosen_rank=best.rank,
        changed=best.rank != hypotheses[0].rank,
        scored=scored,
        critical_items=items,
        warnings=warnings,
    ), sorts
