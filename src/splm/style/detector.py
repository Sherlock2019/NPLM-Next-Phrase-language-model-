"""Style / register detection (spec section 28).

Style governs *how* a meaning is expressed, never what it means. Nothing here may
change a frame slot; the detector only reports which register the text is in, and
the style score nudges candidate wording.

When two styles score close together the detector says so rather than picking one:
a wrong style guess would push candidate scoring in a confidently wrong direction.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from splm.language.packs import LanguagePack, LanguagePackRegistry, get_registry

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_SENTENCE = re.compile(r"[.!?]+")
_CONTRACTION = re.compile(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", re.IGNORECASE)


class StyleDetection(BaseModel):
    """Which register the text appears to be in."""

    style: str | None = None
    confidence: float = 0.0
    scores: dict[str, float] = Field(default_factory=dict)
    #: True when the top two styles are too close to separate.
    uncertain: bool = False
    evidence: list[str] = Field(default_factory=list)

    @property
    def is_confident(self) -> bool:
        return self.style is not None and not self.uncertain


class StyleDetector:
    """Scores text against each style defined in the language pack."""

    name = "marker"

    def __init__(self, registry: LanguagePackRegistry | None = None) -> None:
        self._registry = registry or get_registry()

    def detect(self, text: str, language: str = "en") -> StyleDetection:
        pack = self._registry.get(language)
        styles = pack.style_names
        if not styles or not text.strip():
            return StyleDetection()

        words = [w.lower() for w in _WORD.findall(text)]
        if not words:
            return StyleDetection()

        measurements = self._measure(text, words)
        weights = (pack.styles.get("detection", {}) or {}).get("weights", {}) or {}

        scores: dict[str, float] = {}
        evidence_by_style: dict[str, list[str]] = {}

        for style in styles:
            score, evidence = self._score_style(
                pack, style, words, measurements, weights
            )
            scores[style] = round(score, 4)
            evidence_by_style[style] = evidence

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best, best_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0

        min_margin = float(
            (pack.styles.get("detection", {}) or {}).get("min_margin", 0.08)
        )
        margin = best_score - runner_up
        uncertain = margin < min_margin

        if best_score <= 0.0:
            # No markers at all: report the pack's default without claiming confidence.
            return StyleDetection(
                style=pack.default_style,
                confidence=0.0,
                scores=scores,
                uncertain=True,
                evidence=["no register markers found; using the language pack default"],
            )

        return StyleDetection(
            style=best,
            confidence=round(min(0.99, best_score), 4),
            scores=scores,
            uncertain=uncertain,
            evidence=evidence_by_style.get(best, []),
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _measure(text: str, words: list[str]) -> dict[str, float]:
        sentences = [s for s in _SENTENCE.split(text) if s.strip()]
        sentence_count = max(len(sentences), 1)
        return {
            "word_count": float(len(words)),
            "mean_sentence_length": len(words) / sentence_count,
            "contraction_rate": len(_CONTRACTION.findall(text)) / max(len(words), 1),
        }

    def _score_style(
        self,
        pack: LanguagePack,
        style: str,
        words: list[str],
        measurements: dict[str, float],
        weights: dict[str, Any],
    ) -> tuple[float, list[str]]:
        spec = pack.style_spec(style)
        markers = spec.get("markers", {}) or {}
        evidence: list[str] = []
        score = 0.0

        lexemes = {str(w).lower() for w in markers.get("lexemes", [])}
        hits = [w for w in words if w in lexemes]
        if hits:
            # Normalised by length so a long text does not automatically win.
            rate = len(hits) / len(words)
            score += float(weights.get("lexeme_hits", 1.0)) * min(rate * 6, 1.0)
            evidence.append(
                f"register words present: {', '.join(sorted(set(hits))[:4])}"
            )

        contraction_policy = markers.get("contractions")
        rate = measurements["contraction_rate"]
        if contraction_policy and rate > 0:
            weight = float(weights.get("contraction_rate", 0.6))
            if contraction_policy == "encouraged":
                score += weight * min(rate * 10, 1.0)
                evidence.append("contractions used, which fits an informal register")
            elif contraction_policy == "forbidden":
                score -= weight * min(rate * 10, 1.0)

        expected_length = (markers.get("sentence_length", {}) or {}).get("mean")
        if expected_length:
            observed = measurements["mean_sentence_length"]
            # Closeness in [0,1]: 1 when identical, decaying with relative difference.
            closeness = 1.0 / (1.0 + abs(observed - float(expected_length)) / 8.0)
            score += float(weights.get("mean_sentence_length", 0.5)) * closeness

        avoids = {str(w).lower() for w in spec.get("avoids", [])}
        violations = [w for w in words if w in avoids]
        if violations:
            score -= 0.5
            evidence.append(
                f"words atypical of this register: {', '.join(sorted(set(violations))[:3])}"
            )

        return max(score, 0.0), evidence
