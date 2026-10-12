"""The Transformer-facing half of SPLM: candidates, features, scoring, decoding."""

from __future__ import annotations

from splm.model.advantage import SearchSpace, SemanticFocus, TargetOutcome
from splm.model.base_llm import BaseLanguageModel, Candidate, ModelUnavailable
from splm.model.candidate_features import (
    FEATURE_ORDER,
    CandidateFeatureExtractor,
    CandidateFeatures,
    ScoringContext,
)
from splm.model.candidate_scorer import (
    CandidateScore,
    NeuralScorer,
    PhraseCandidateScorer,
    WeightedScorer,
)
from splm.model.engine import PredictionResult, SPLMEngine
from splm.model.word_tracker import LexicalTrie, WordCandidateTracker

__all__ = [
    "BaseLanguageModel",
    "Candidate",
    "CandidateFeatureExtractor",
    "CandidateFeatures",
    "CandidateScore",
    "FEATURE_ORDER",
    "LexicalTrie",
    "ModelUnavailable",
    "NeuralScorer",
    "PhraseCandidateScorer",
    "PredictionResult",
    "SPLMEngine",
    "ScoringContext",
    "SearchSpace",
    "SemanticFocus",
    "TargetOutcome",
    "WeightedScorer",
    "WordCandidateTracker",
]
