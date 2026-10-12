"""Evaluation: datasets, metrics, the base-model control arm, and the runner."""

from __future__ import annotations

from splm.evaluation.baseline import Baseline, BaselineResult
from splm.evaluation.benchmark import Benchmark, BenchmarkReport, ItemResult
from splm.evaluation.datasets import TestCase, diagnostic_suite
from splm.evaluation.metrics import Comparison, Continuous, Proportion, RankMetrics
from splm.evaluation.store import list_results, load_result, write_result

__all__ = [
    "Baseline",
    "BaselineResult",
    "Benchmark",
    "BenchmarkReport",
    "Comparison",
    "Continuous",
    "ItemResult",
    "Proportion",
    "RankMetrics",
    "TestCase",
    "diagnostic_suite",
    "list_results",
    "load_result",
    "write_result",
]
