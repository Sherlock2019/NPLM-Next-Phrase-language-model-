"""SPLM candidate scoring (spec sections 23-24).

    FINAL = base_logit + logit_scale * SUM_f  w_f * (feature_f - neutral)

Centring each feature on ``neutral`` is what makes the layer safe: a feature with
no evidence lands exactly on neutral and contributes exactly zero, so silence never
masquerades as support.

Two backends behind one interface:

``WeightedScorer``
    The configured weights from ``config/scoring.yaml``. Inspectable, and the
    contributions it reports are literally the terms of the sum above - which is
    what the UI's waterfall chart draws.

``NeuralScorer``
    The Phase 9 replacement: a small network over the same feature vector, trained
    separately from the base LLM. Same interface, same reported contributions
    (via gradients), so nothing downstream changes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from splm.model.candidate_features import (
    FEATURE_ORDER,
    FEATURE_SWITCHES,
    CandidateFeatures,
    CandidateFeatureExtractor,
    ScoringContext,
)

logger = logging.getLogger(__name__)


class FeatureContribution(BaseModel):
    """One term of the scoring sum, ready to draw as a waterfall bar."""

    feature: str
    value: float
    weight: float
    contribution: float = Field(description="Logits this feature added or removed")
    informative: bool = True
    enabled: bool = True


class CandidateScore(BaseModel):
    """A candidate's full scoring record."""

    token: str
    token_id: int
    word: str = ""

    base_logit: float
    base_probability: float
    base_rank: int

    splm_logit: float
    splm_probability: float = 0.0
    splm_rank: int = 0

    delta_logit: float = 0.0
    contributions: list[FeatureContribution] = Field(default_factory=list)
    features: CandidateFeatures | None = None
    reasons: list[str] = Field(default_factory=list)
    clipped: bool = False

    @property
    def rank_change(self) -> int:
        """Positions gained. Positive means SPLM promoted the candidate."""
        return self.base_rank - self.splm_rank

    @property
    def direction(self) -> str:
        """``up``, ``down`` or ``same`` (metrics brief section 9)."""
        if self.delta_logit > 0.01:
            return "up"
        if self.delta_logit < -0.01:
            return "down"
        return "same"

    def feature_value(self, name: str) -> float:
        return float(getattr(self.features, name, 0.0)) if self.features else 0.0


@runtime_checkable
class ScorerBackend(Protocol):
    name: str

    def delta(self, features: CandidateFeatures) -> tuple[float, list[FeatureContribution]]: ...


class WeightedScorer:
    """Configured linear scorer (spec section 23)."""

    name = "weighted"

    def __init__(
        self,
        weights: dict[str, float],
        *,
        features_enabled: dict[str, bool] | None = None,
        neutral: float = 0.5,
        logit_scale: float = 2.0,
        max_logit_delta: float = 6.0,
    ) -> None:
        self.weights = dict(weights)
        self.features_enabled = dict(features_enabled or {})
        self.neutral = neutral
        self.logit_scale = logit_scale
        self.max_logit_delta = max_logit_delta

    def is_enabled(self, feature: str) -> bool:
        switch = FEATURE_SWITCHES.get(feature)
        if switch is None:
            return True
        return bool(self.features_enabled.get(switch, True))

    def delta(self, features: CandidateFeatures) -> tuple[float, list[FeatureContribution]]:
        contributions: list[FeatureContribution] = []
        total = 0.0

        for name in FEATURE_ORDER:
            if name == "llm":
                # The base logit already carries the model's own opinion; adding it
                # again would double-count it.
                continue

            weight = float(self.weights.get(name, 0.0))
            value = float(getattr(features, name, self.neutral))
            informative = bool(features.informative.get(name, False))
            enabled = self.is_enabled(name)

            contribution = (
                weight * (value - self.neutral) * self.logit_scale
                if enabled and informative
                else 0.0
            )
            total += contribution

            contributions.append(
                FeatureContribution(
                    feature=name,
                    value=round(value, 4),
                    weight=weight,
                    contribution=round(contribution, 4),
                    informative=informative,
                    enabled=enabled,
                )
            )

        clipped = abs(total) > self.max_logit_delta
        if clipped:
            total = self.max_logit_delta if total > 0 else -self.max_logit_delta

        return total, contributions


class NeuralScorer(WeightedScorer):
    """Trainable scorer (spec section 48 / Phase 9).

    Replaces the hand-set weights with a learned function of the same feature
    vector::

        9 features -> Linear(9, 32) -> ReLU -> Linear(32, 16) -> ReLU -> Linear(16, 1)

    Trained separately from the base LLM. Until a checkpoint exists it defers to the
    configured weights, so enabling ``backend: neural`` prematurely degrades to the
    documented baseline instead of failing.
    """

    name = "neural"

    def __init__(
        self,
        weights: dict[str, float],
        *,
        checkpoint: Path | str | None = None,
        hidden_sizes: tuple[int, ...] = (32, 16),
        **kwargs: Any,
    ) -> None:
        super().__init__(weights, **kwargs)
        self.checkpoint = Path(checkpoint) if checkpoint else None
        self.hidden_sizes = tuple(hidden_sizes)
        self._model: Any | None = None
        self._load()

    def _load(self) -> None:
        if self.checkpoint is None or not self.checkpoint.is_file():
            logger.info(
                "no scorer checkpoint at %s; falling back to configured weights",
                self.checkpoint,
            )
            return
        try:
            import torch

            from splm.training.scorer_model import CandidateScorerNet

            payload = torch.load(self.checkpoint, map_location="cpu", weights_only=False)
            self._model = CandidateScorerNet(
                input_dim=payload.get("input_dim", len(FEATURE_ORDER)),
                hidden_sizes=payload.get("hidden_sizes", list(self.hidden_sizes)),
            )
            self._model.load_state_dict(payload["state_dict"])
            self._model.eval()
            logger.info("loaded candidate scorer from %s", self.checkpoint)
        except Exception as exc:
            logger.warning("could not load scorer %s: %s", self.checkpoint, exc)
            self._model = None

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def delta(self, features: CandidateFeatures) -> tuple[float, list[FeatureContribution]]:
        if self._model is None:
            return super().delta(features)

        import torch

        # Disabled features are zeroed at the neutral point so ablations still work.
        vector = []
        for name in FEATURE_ORDER:
            value = float(getattr(features, name, self.neutral))
            if not self.is_enabled(name) or not features.informative.get(name, False):
                value = self.neutral
            vector.append(value)

        tensor = torch.tensor([vector], dtype=torch.float32, requires_grad=True)
        output = self._model(tensor)
        total = float(output.squeeze())

        # Attribute the output to each feature by gradient x (value - neutral), so the
        # UI's contribution chart stays meaningful for a learned scorer too.
        output.backward()
        gradients = tensor.grad.squeeze(0).tolist() if tensor.grad is not None else [0.0] * len(vector)

        contributions = [
            FeatureContribution(
                feature=name,
                value=round(vector[index], 4),
                weight=round(gradients[index], 4),
                contribution=round(gradients[index] * (vector[index] - self.neutral), 4),
                informative=bool(features.informative.get(name, False)),
                enabled=self.is_enabled(name),
            )
            for index, name in enumerate(FEATURE_ORDER)
            if name != "llm"
        ]

        clipped = abs(total) > self.max_logit_delta
        if clipped:
            total = self.max_logit_delta if total > 0 else -self.max_logit_delta
        return total, contributions


class PhraseCandidateScorer:
    """Scores a step's candidates end to end (spec section 24)."""

    def __init__(
        self,
        *,
        extractor: CandidateFeatureExtractor,
        backend: ScorerBackend,
        neutral: float = 0.5,
    ) -> None:
        self.extractor = extractor
        self.backend = backend
        self.neutral = neutral

    @classmethod
    def from_config(
        cls, config: Any | None = None, *, registry: Any | None = None, lexicon: Any | None = None
    ) -> "PhraseCandidateScorer":
        from splm.config import get_config
        from splm.language.packs import get_registry

        config = config or get_config()
        registry = registry or get_registry(config.language_packs_dir)

        neutral = float(config.get("scoring.scoring.neutral", 0.5))
        common = {
            "features_enabled": config.features,
            "neutral": neutral,
            "logit_scale": float(config.get("scoring.scoring.logit_scale", 2.0)),
            "max_logit_delta": float(config.get("scoring.scoring.max_logit_delta", 6.0)),
        }

        backend_name = str(config.get("scoring.backend", "weighted") or "weighted").lower()
        if backend_name == "neural":
            checkpoint = config.get("scoring.neural.checkpoint")
            backend: ScorerBackend = NeuralScorer(
                config.scoring_weights,
                checkpoint=config.root / checkpoint if checkpoint else None,
                hidden_sizes=tuple(config.get("scoring.neural.hidden_sizes", [32, 16])),
                **common,
            )
        else:
            if backend_name != "weighted":
                logger.warning("unknown scoring backend %r; using weighted", backend_name)
            backend = WeightedScorer(config.scoring_weights, **common)

        return cls(
            extractor=CandidateFeatureExtractor(
                registry, config=config, lexicon=lexicon, neutral=neutral
            ),
            backend=backend,
            neutral=neutral,
        )

    # -- scoring -----------------------------------------------------------

    def score_candidates(
        self, candidates: list[Any], context: ScoringContext
    ) -> list[CandidateScore]:
        """Score every candidate and assign SPLM ranks."""
        feature_sets = self.extractor.extract_all(candidates, context)
        scored: list[CandidateScore] = []

        for candidate, features in zip(candidates, feature_sets):
            delta, contributions = self.backend.delta(features)
            # Round once, then derive the final logit from the rounded value, so that
            # base + delta == final holds exactly in anything that displays all three.
            delta = round(delta, 4)
            scored.append(
                CandidateScore(
                    token=candidate.token,
                    token_id=candidate.token_id,
                    word=features.word,
                    base_logit=candidate.logit,
                    base_probability=candidate.probability,
                    base_rank=candidate.rank,
                    splm_logit=candidate.logit + delta,
                    delta_logit=delta,
                    contributions=contributions,
                    features=features,
                    reasons=list(features.reasons),
                )
            )

        return self._rank_and_normalise(scored)

    def score(
        self,
        context: ScoringContext,
        candidate: Any,
    ) -> CandidateScore:
        """Score a single candidate - the signature from spec section 24."""
        return self.score_candidates([candidate], context)[0]

    @staticmethod
    def _rank_and_normalise(scored: list[CandidateScore]) -> list[CandidateScore]:
        """Assign SPLM ranks and a softmax over the re-scored candidates.

        The SPLM probabilities are a distribution over *this candidate set*, not over
        the whole vocabulary, because only these candidates were re-scored. The base
        probabilities are whole-vocabulary. The engine therefore renormalises the base
        figures over the same set before comparing them, so the two columns in the UI
        are apples to apples.
        """
        import math

        if not scored:
            return scored

        highest = max(item.splm_logit for item in scored)
        exponentials = [math.exp(item.splm_logit - highest) for item in scored]
        total = sum(exponentials) or 1.0

        for item, value in zip(scored, exponentials):
            item.splm_probability = value / total

        for rank, item in enumerate(
            sorted(scored, key=lambda s: s.splm_logit, reverse=True), start=1
        ):
            item.splm_rank = rank

        return scored
