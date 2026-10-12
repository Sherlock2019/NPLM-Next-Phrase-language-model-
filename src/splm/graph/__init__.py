"""The context graph: what has happened, who is involved, how events relate."""

from __future__ import annotations

from splm.graph.context_graph import (
    ContextGraph,
    Coreference,
    GraphEdge,
    GraphNode,
)

__all__ = ["ContextGraph", "Coreference", "GraphEdge", "GraphNode"]
