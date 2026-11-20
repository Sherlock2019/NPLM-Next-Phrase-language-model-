"""Speech metrics: WER, CER, critical entity and number preservation, memory.

Text is normalised the same way for reference and hypothesis (case, punctuation,
whitespace) and nothing else - no number-word conversion, so "5" versus "five"
counts as an error. That is deliberate: number preservation is one of the things
being measured, and a normaliser that hid it would flatter every system equally.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Sequence

_PUNCT = re.compile(r"[^\w\s']", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, NFC, punctuation stripped, whitespace collapsed."""
    text = unicodedata.normalize("NFC", text or "").lower()
    text = _PUNCT.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


def edit_distance(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    """Levenshtein distance over arbitrary sequences (words or characters)."""
    if not reference:
        return len(hypothesis)
    previous = list(range(len(hypothesis) + 1))
    for i, ref_item in enumerate(reference, start=1):
        current = [i] + [0] * len(hypothesis)
        for j, hyp_item in enumerate(hypothesis, start=1):
            current[j] = min(
                previous[j] + 1,                               # deletion
                current[j - 1] + 1,                            # insertion
                previous[j - 1] + (ref_item != hyp_item),      # substitution
            )
        previous = current
    return previous[-1]


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate. 0 for a perfect match; can exceed 1 with many insertions."""
    ref, hyp = normalize(reference).split(), normalize(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate over normalised text, spaces excluded.

    Spaces are dropped because Vietnamese writes one syllable per word and French
    elides; word boundaries are already scored by WER.
    """
    ref = normalize(reference).replace(" ", "")
    hyp = normalize(hypothesis).replace(" ", "")
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(list(ref), list(hyp)) / len(ref)


# -- critical content -------------------------------------------------------

_DIGITS = re.compile(r"\d+(?:[.,:]\d+)*")

#: Spoken numbers per language. Small on purpose: these are the ones voice
#: commands actually carry (quantities, times, dates); extend in one place.
NUMBER_WORDS: dict[str, dict[str, str]] = {
    "en": {w: str(i) for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
    | {"thirty": "30", "forty": "40", "fifty": "50", "hundred": "100", "thousand": "1000"},
    "fr": {w: str(i) for i, w in enumerate(
        "zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize "
        "quatorze quinze seize".split())}
    | {"une": "1", "vingt": "20", "trente": "30", "quarante": "40", "cinquante": "50",
       "cent": "100", "mille": "1000"},
    "vi": {"không": "0", "một": "1", "hai": "2", "ba": "3", "bốn": "4", "năm": "5",
           "sáu": "6", "bảy": "7", "tám": "8", "chín": "9", "mười": "10",
           "trăm": "100", "nghìn": "1000", "ngàn": "1000"},
}


def extract_numbers(text: str, language: str | None = None) -> list[str]:
    """Numbers in ``text`` as digit strings, from digits and from number words.

    Vietnamese "năm" also means "year"; it is counted as a number only when it is
    followed by nothing alphabetic that would make it a noun is undecidable without
    a parser, so it is counted - a known source of false positives, kept visible.
    """
    found = [match.group(0).replace(",", ".") for match in _DIGITS.finditer(text or "")]
    words = NUMBER_WORDS.get(language or "", {})
    if words:
        for token in normalize(text).split():
            if token in words:
                found.append(words[token])
    return found


def preserved(expected: Iterable[str], hypothesis: str, *, numbers: bool = False,
              language: str | None = None) -> tuple[int, int]:
    """How many expected items survive into ``hypothesis``: (kept, total).

    Entities are matched as normalised substrings; numbers by value, so "five" in
    the hypothesis does preserve an expected "5".
    """
    items = [item for item in expected if str(item).strip()]
    if not items:
        return 0, 0
    if numbers:
        available = extract_numbers(hypothesis, language)
        kept = 0
        for item in items:
            value = str(item).replace(",", ".")
            if value in available:
                available.remove(value)
                kept += 1
        return kept, len(items)
    normalised = f" {normalize(hypothesis)} "
    kept = sum(1 for item in items if f" {normalize(str(item))} " in normalised)
    return kept, len(items)


# -- memory ----------------------------------------------------------------

def memory_snapshot() -> dict[str, float | None]:
    """Resident and peak memory of this process, plus CUDA peak when present (MB)."""
    rss = peak = None
    try:
        import resource

        # ru_maxrss is kilobytes on Linux.
        peak = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except (ImportError, OSError):
        pass
    try:
        import psutil

        rss = round(psutil.Process().memory_info().rss / (1024 * 1024), 1)
    except Exception:  # noqa: BLE001 - psutil is optional
        pass
    cuda_peak = None
    try:
        import torch

        if torch.cuda.is_available():
            cuda_peak = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1)
    except Exception:  # noqa: BLE001
        pass
    return {"rss_mb": rss, "peak_rss_mb": peak, "cuda_peak_mb": cuda_peak}
