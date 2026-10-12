"""Benchmark metrics and the statistics needed to read them honestly.

Spec sections 44-45 of the UI brief are requirements, not style notes:

* a difference is reported as an improvement only when the evidence supports it;
* every comparison carries a sample count and a confidence interval;
* "SPLM is better" is never said - "SPLM scored higher on this dataset" is.

So :class:`Comparison` computes a verdict from the interval, not from the point
estimate, and it has four outcomes including *insufficient data*.
"""

from __future__ import annotations

import math
from typing import Literal, Sequence

from pydantic import BaseModel, Field

Verdict = Literal[
    "splm_improved", "no_meaningful_difference", "base_better", "insufficient_data"
]

#: Below this many samples, no verdict is offered at all.
MIN_SAMPLES = 20
#: A difference smaller than this in either direction is called no difference.
NEGLIGIBLE = 0.01


def wilson_interval(
    successes: int, total: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Preferred over the normal approximation because benchmark suites are small and
    accuracies sit near 0 or 1, where the normal interval misbehaves badly.
    """
    if total <= 0:
        return (0.0, 0.0)
    z = 1.959964 if confidence >= 0.95 else 1.644854
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = proportion + z**2 / (2 * total)
    spread = z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2))
    return (
        max(0.0, (centre - spread) / denominator),
        min(1.0, (centre + spread) / denominator),
    )


def mcnemar_p_value(base_only: int, splm_only: int) -> float | None:
    """Two-sided exact McNemar p-value for paired correct/incorrect outcomes.

    The right test here: each item is answered by both systems, so only the items
    where they disagree carry information. Returns ``None`` when nothing disagrees.
    """
    n = base_only + splm_only
    if n == 0:
        return None

    # Exact binomial test against p = 0.5 on the discordant pairs.
    k = min(base_only, splm_only)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


class Proportion(BaseModel):
    """A measured proportion with its interval."""

    successes: int
    total: int

    @property
    def value(self) -> float:
        return self.successes / self.total if self.total else 0.0

    @property
    def percent(self) -> float:
        return round(self.value * 100, 2)

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.successes, self.total)

    def summary(self) -> dict[str, float | int]:
        low, high = self.interval
        return {
            "successes": self.successes,
            "total": self.total,
            "value": round(self.value, 4),
            "percent": self.percent,
            "ci_low": round(low, 4),
            "ci_high": round(high, 4),
        }


class Comparison(BaseModel):
    """A base-versus-SPLM comparison on one metric."""

    metric: str
    base: Proportion
    splm: Proportion
    higher_is_better: bool = True
    #: Items each system got right that the other did not; needed for McNemar.
    base_only_correct: int = 0
    splm_only_correct: int = 0
    unit: str = "proportion"
    note: str = ""

    @property
    def difference(self) -> float:
        delta = self.splm.value - self.base.value
        return delta if self.higher_is_better else -delta

    @property
    def difference_percentage_points(self) -> float:
        return round((self.splm.value - self.base.value) * 100, 2)

    @property
    def relative_difference(self) -> float | None:
        if self.base.value == 0:
            return None
        return round((self.splm.value - self.base.value) / self.base.value, 4)

    @property
    def p_value(self) -> float | None:
        return mcnemar_p_value(self.base_only_correct, self.splm_only_correct)

    @property
    def intervals_overlap(self) -> bool:
        base_low, base_high = self.base.interval
        splm_low, splm_high = self.splm.interval
        return not (splm_low > base_high or base_low > splm_high)

    @property
    def verdict(self) -> Verdict:
        """Four-way outcome, decided by evidence rather than by the point estimate."""
        if min(self.base.total, self.splm.total) < MIN_SAMPLES:
            return "insufficient_data"
        if abs(self.difference) < NEGLIGIBLE:
            return "no_meaningful_difference"

        p = self.p_value
        # With paired data, require the disagreements to be lopsided enough to matter.
        if p is not None and p > 0.05:
            return "no_meaningful_difference"
        # Without a usable paired test, fall back to interval separation.
        if p is None and self.intervals_overlap:
            return "no_meaningful_difference"

        return "splm_improved" if self.difference > 0 else "base_better"

    def statement(self) -> str:
        """A factual sentence, phrased as the UI brief requires."""
        delta = self.difference_percentage_points
        verdict = self.verdict
        if verdict == "insufficient_data":
            return (
                f"{self.metric}: {self.base.total} samples is too few for a verdict "
                f"(observed {delta:+.2f} pp)."
            )
        if verdict == "no_meaningful_difference":
            return (
                f"{self.metric}: no meaningful difference on this dataset "
                f"({delta:+.2f} pp over {self.splm.total} samples)."
            )
        if verdict == "base_better":
            return (
                f"{self.metric}: the base model scored higher on this dataset "
                f"({delta:+.2f} pp over {self.splm.total} samples)."
            )
        return (
            f"{self.metric}: SPLM scored higher on this dataset by "
            f"{abs(delta):.2f} percentage points over {self.splm.total} samples."
        )

    def summary(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "base": self.base.summary(),
            "splm": self.splm.summary(),
            "difference_pp": self.difference_percentage_points,
            "relative_difference": self.relative_difference,
            "p_value": self.p_value,
            "base_only_correct": self.base_only_correct,
            "splm_only_correct": self.splm_only_correct,
            "intervals_overlap": self.intervals_overlap,
            "verdict": self.verdict,
            "statement": self.statement(),
            "note": self.note,
        }


class Continuous(BaseModel):
    """A continuous measurement, e.g. latency or target rank."""

    metric: str
    base_values: list[float] = Field(default_factory=list)
    splm_values: list[float] = Field(default_factory=list)
    lower_is_better: bool = True
    unit: str = ""

    @staticmethod
    def _mean(values: Sequence[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _stdev(values: Sequence[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))

    @property
    def base_mean(self) -> float:
        return round(self._mean(self.base_values), 4)

    @property
    def splm_mean(self) -> float:
        return round(self._mean(self.splm_values), 4)

    @property
    def difference(self) -> float:
        return round(self.splm_mean - self.base_mean, 4)

    @property
    def improved(self) -> bool | None:
        if not self.base_values or not self.splm_values:
            return None
        return (
            self.difference < 0 if self.lower_is_better else self.difference > 0
        )

    def summary(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "unit": self.unit,
            "base_mean": self.base_mean,
            "splm_mean": self.splm_mean,
            "base_stdev": round(self._stdev(self.base_values), 4),
            "splm_stdev": round(self._stdev(self.splm_values), 4),
            "difference": self.difference,
            "samples": min(len(self.base_values), len(self.splm_values)),
            "lower_is_better": self.lower_is_better,
            "improved": self.improved,
        }


class RankMetrics(BaseModel):
    """Where the correct answer landed (metrics brief section 10)."""

    ranks: list[int] = Field(default_factory=list)
    not_found: int = 0

    def add(self, rank: int | None) -> None:
        if rank is None:
            self.not_found += 1
        else:
            self.ranks.append(rank)

    @property
    def total(self) -> int:
        return len(self.ranks) + self.not_found

    @property
    def mean_rank(self) -> float | None:
        """Mean rank over items where the target was found.

        Items where it was absent are excluded and counted separately - assigning them
        an arbitrary rank would silently invent data.
        """
        return round(sum(self.ranks) / len(self.ranks), 3) if self.ranks else None

    @property
    def mrr(self) -> float:
        """Mean reciprocal rank over *all* items; absent targets contribute 0."""
        if self.total == 0:
            return 0.0
        return round(sum(1 / rank for rank in self.ranks) / self.total, 4)

    def hits_at(self, k: int) -> Proportion:
        return Proportion(
            successes=sum(1 for rank in self.ranks if rank <= k), total=self.total
        )

    def summary(self) -> dict[str, object]:
        return {
            "samples": self.total,
            "found": len(self.ranks),
            "not_found": self.not_found,
            "mean_rank": self.mean_rank,
            "mrr": self.mrr,
            "top_1": self.hits_at(1).summary(),
            "top_5": self.hits_at(5).summary(),
            "top_10": self.hits_at(10).summary(),
        }


class ConfusionMatrix(BaseModel):
    """True slot versus predicted slot (metrics brief section 24)."""

    counts: dict[str, dict[str, int]] = Field(default_factory=dict)

    def add(self, true_slot: str, predicted: str) -> None:
        self.counts.setdefault(true_slot, {})
        self.counts[true_slot][predicted] = self.counts[true_slot].get(predicted, 0) + 1

    @property
    def labels(self) -> list[str]:
        found = set(self.counts)
        for row in self.counts.values():
            found.update(row)
        return sorted(found)

    def accuracy(self) -> Proportion:
        correct = sum(row.get(label, 0) for label, row in self.counts.items())
        total = sum(sum(row.values()) for row in self.counts.values())
        return Proportion(successes=correct, total=total)

    def per_slot(self) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for label, row in self.counts.items():
            total = sum(row.values())
            correct = row.get(label, 0)
            confusions = sorted(
                ((other, count) for other, count in row.items() if other != label),
                key=lambda kv: kv[1],
                reverse=True,
            )
            result[label] = {
                **Proportion(successes=correct, total=total).summary(),
                "top_confusions": [
                    {"predicted": other, "count": count} for other, count in confusions[:3]
                ],
            }
        return result

    def common_errors(self, limit: int = 8) -> list[dict[str, object]]:
        errors = [
            {"true": label, "predicted": other, "count": count}
            for label, row in self.counts.items()
            for other, count in row.items()
            if other != label
        ]
        return sorted(errors, key=lambda e: e["count"], reverse=True)[:limit]  # type: ignore[arg-type]


class WinLossTally(BaseModel):
    """Per-item win / tie / loss, by a stated criterion (metrics brief section 39)."""

    criterion: str = "rank of the correct answer"
    wins: int = 0
    ties: int = 0
    losses: int = 0

    def add(self, verdict: str) -> None:
        if verdict == "win":
            self.wins += 1
        elif verdict == "loss":
            self.losses += 1
        elif verdict == "tie":
            self.ties += 1

    @property
    def total(self) -> int:
        return self.wins + self.ties + self.losses

    def summary(self) -> dict[str, object]:
        total = self.total or 1
        return {
            "criterion": self.criterion,
            "wins": self.wins,
            "ties": self.ties,
            "losses": self.losses,
            "total": self.total,
            "win_rate": round(self.wins / total, 4),
            "tie_rate": round(self.ties / total, 4),
            "loss_rate": round(self.losses / total, 4),
        }
