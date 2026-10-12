"""Base-model-only evaluation (spec section 38).

The control arm. It runs the same items through the Transformer with no structural
layer at all, which serves two purposes: it is the comparison every SPLM number is
measured against, and it is a check on the harness itself - if the base arm here
disagrees with the base column produced during an SPLM run, the comparison is not
apples to apples and the discrepancy is a bug.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

from pydantic import BaseModel, Field

from splm.config import Config
from splm.evaluation.datasets import TestCase
from splm.evaluation.metrics import Proportion, RankMetrics

logger = logging.getLogger(__name__)


class BaselineResult(BaseModel):
    """What the base model alone achieved."""

    model_id: str
    samples: int = 0
    top_1: dict[str, Any] = Field(default_factory=dict)
    ranks: dict[str, Any] = Field(default_factory=dict)
    mean_latency_ms: float = 0.0
    perplexity: float | None = None
    perplexity_note: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)


class Baseline:
    """Runs items through the Transformer with SPLM switched off entirely."""

    def __init__(self, config: Config | None = None, *, llm: Any | None = None) -> None:
        from splm.config import get_config

        self.config = config or get_config()
        self._llm = llm

    @property
    def llm(self) -> Any:
        if self._llm is None:
            from splm.model.base_llm import BaseLanguageModel

            self._llm = BaseLanguageModel.from_config(self.config)
        return self._llm

    def run(self, cases: list[TestCase], *, top_k: int | None = None) -> BaselineResult:
        llm = self.llm
        llm.load()
        # Warm the kernels so the first item does not carry the loading cost.
        llm.get_top_candidates("Warmup", k=8)

        result = BaselineResult(model_id=llm.model_id)
        ranks = RankMetrics()
        correct = total = 0
        latencies: list[float] = []

        for case in cases:
            if case.kind != "next_word" or not case.target:
                continue

            started = time.perf_counter()
            candidates = llm.get_top_candidates(case.prompt, k=top_k or llm.top_k_candidates)
            latencies.append((time.perf_counter() - started) * 1000)

            top = candidates[0] if candidates else None
            hit = bool(top and case.is_correct_word(top.stripped))
            total += 1
            correct += int(hit)

            target_rank = next(
                (c.rank for c in candidates if case.is_correct_word(c.stripped)), None
            )
            ranks.add(target_rank)

            result.items.append(
                {
                    "id": case.id,
                    "prompt": case.prompt,
                    "target": case.target,
                    "top": top.stripped if top else None,
                    "correct": hit,
                    "target_rank": target_rank,
                }
            )

        result.samples = total
        result.top_1 = Proportion(successes=correct, total=total).summary()
        result.ranks = ranks.summary()
        result.mean_latency_ms = (
            round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        )
        return result

    def perplexity(self, texts: list[str]) -> tuple[float | None, str]:
        """Token-level perplexity of the base model over ``texts``.

        Reported for the base model only, and deliberately not for SPLM: SPLM
        re-scores just the top-K candidates, so its adjusted scores are not a
        normalised distribution over the vocabulary. Calling the result a perplexity
        would be a category error, so this returns the base figure plus that caveat.
        """
        llm = self.llm
        total_log_probability = 0.0
        total_tokens = 0

        for text in texts:
            try:
                log_probability, count = llm.sequence_log_probability(text)
            except Exception as exc:
                logger.debug("perplexity failed for %r: %s", text[:40], exc)
                continue
            total_log_probability += log_probability
            total_tokens += count

        if total_tokens == 0:
            return None, "no scorable text"

        value = math.exp(-total_log_probability / total_tokens)
        note = (
            "Base model only. SPLM re-scores the top-K candidates rather than the whole "
            "vocabulary, so its adjusted scores are not a normalised distribution and a "
            "comparable perplexity cannot be computed without full-vocabulary rescoring."
        )
        return round(value, 4), note
