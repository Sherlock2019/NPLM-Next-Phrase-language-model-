"""Context graph (spec section 27).

Tracks entities, events and the relations between them across sentences, so later
text can be interpreted against what is already known:

    John met Sarah in Paris.     -> event(meet), agent John, participant Sarah, location Paris
    She gave him a document.     -> she = Sarah, him = John
    He read it later.            -> he = John, it = document

Built on NetworkX. The graph is populated from Universal Phrase Frames, so it
inherits their language independence: the same graph results from the English,
French or Vietnamese rendering of the same events.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel, Field

from splm.phrase.schema import FrameElement, UniversalPhraseFrame

logger = logging.getLogger(__name__)

#: Entity types that can be referred to by a pronoun.
REFERRABLE = frozenset({"PERSON", "ORG", "LOCATION", "FACILITY", "PRODUCT", "OTHER"})


class GraphNode(BaseModel):
    """One node: an entity, an event, or a circumstance."""

    id: str
    kind: str = Field(description="entity | event | state | time | location | value")
    label: str
    entity_type: str | None = None
    lemma: str | None = None
    sentence_index: int = 0
    features: dict[str, Any] = Field(default_factory=dict)
    mentions: list[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    """A labelled relation between two nodes."""

    source: str
    target: str
    relation: str
    confidence: float = 1.0
    sentence_index: int = 0


@dataclass
class CandidateVerdict:
    """The context layer's opinion on a candidate word."""

    score: float
    reason: str | None = None


class Coreference(BaseModel):
    """A resolved (or unresolved) pronoun."""

    mention: str
    sentence_index: int
    resolved_to: str | None = None
    resolved_label: str | None = None
    confidence: float = 0.0
    alternatives: list[str] = Field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.resolved_to is not None


class ContextGraph:
    """A growing semantic record of the discourse."""

    def __init__(self) -> None:
        try:
            import networkx as nx

            self._graph = nx.MultiDiGraph()
            self._backend = "networkx"
        except ImportError:  # pragma: no cover - networkx is a core dependency
            self._graph = None
            self._backend = "none"
            logger.warning("networkx unavailable; the context graph is disabled")

        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self.coreferences: list[Coreference] = []
        self._sentence_count = 0
        self._counter = itertools.count(1)

    # -- introspection -----------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._graph is not None

    def __len__(self) -> int:
        return len(self.nodes)

    def describe(self) -> dict[str, Any]:
        """Counts for the UI's compression and efficiency panels."""
        kinds: dict[str, int] = {}
        for node in self.nodes.values():
            kinds[node.kind] = kinds.get(node.kind, 0) + 1
        return {
            "backend": self._backend,
            "sentences": self._sentence_count,
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "by_kind": kinds,
            "coreferences_resolved": sum(1 for c in self.coreferences if c.resolved),
            "coreferences_total": len(self.coreferences),
        }

    def reset(self) -> None:
        self.__init__()  # type: ignore[misc]

    # -- building ----------------------------------------------------------

    def add_frame(self, frame: UniversalPhraseFrame, *, resolve: bool = True) -> str | None:
        """Add one frame (and its nested frames) to the graph."""
        if not self.enabled:
            return None
        index = self._sentence_count
        self._sentence_count += 1
        return self._add_frame(frame, index, resolve=resolve)

    def add_frames(self, frames: Iterable[UniversalPhraseFrame], *, resolve: bool = True) -> None:
        for frame in frames:
            self.add_frame(frame, resolve=resolve)

    def _add_frame(
        self, frame: UniversalPhraseFrame, index: int, *, resolve: bool
    ) -> str | None:
        if frame.predicate is None:
            return None

        event_id = self._new_id("event")
        kind = "state" if frame.predicate.type.value in {"STATE", "EXISTENCE"} else "event"
        self._add_node(
            GraphNode(
                id=event_id,
                kind=kind,
                label=frame.predicate.lemma,
                lemma=frame.predicate.lemma,
                sentence_index=index,
                features={
                    "predicate_type": frame.predicate.type.value,
                    "sense": frame.predicate.sense,
                    "tense": frame.tense.value if frame.tense else None,
                    "negation": frame.negation,
                    "modality": frame.modality,
                },
            )
        )

        for slot, element in frame.elements():
            node_id = self._entity_for(element, index, resolve=resolve)
            if node_id is None:
                continue
            self._add_edge(
                GraphEdge(
                    source=event_id,
                    target=node_id,
                    relation=element.semantic_role,
                    confidence=element.confidence,
                    sentence_index=index,
                )
            )
            if element.frame is not None:
                nested = self._add_frame(element.frame, index, resolve=resolve)
                if nested:
                    self._add_edge(
                        GraphEdge(
                            source=event_id,
                            target=nested,
                            relation=element.semantic_role,
                            sentence_index=index,
                        )
                    )

        for child in frame.children:
            nested = self._add_frame(child, index, resolve=resolve)
            if nested:
                self._add_edge(
                    GraphEdge(
                        source=event_id,
                        target=nested,
                        relation="COORDINATE",
                        sentence_index=index,
                    )
                )

        return event_id

    def _entity_for(
        self, element: FrameElement, index: int, *, resolve: bool
    ) -> str | None:
        """Find or create the node an element refers to."""
        if element.frame is not None:
            return None

        label = element.text.strip()
        if not label:
            return None

        pronoun_type = element.features.get("pronoun_type")
        is_pronoun = pronoun_type is not None or element.features.get("person") in {1, 2}

        if resolve and is_pronoun:
            reference = self.resolve_pronoun(element, index)
            self.coreferences.append(reference)
            if reference.resolved_to is not None:
                node = self.nodes[reference.resolved_to]
                if label not in node.mentions:
                    node.mentions.append(label)
                return reference.resolved_to
            # Unresolved: keep it as its own node rather than guessing.

        existing = self._find_entity(label)
        if existing is not None:
            return existing

        node_id = self._new_id("entity")
        kind = {
            "LOCATION": "location",
            "FACILITY": "location",
            "TIME": "time",
        }.get(element.entity_type or "", "entity")
        if element.semantic_role in {"TIME"}:
            kind = "time"
        elif element.semantic_role in {"LOCATION", "DESTINATION", "SOURCE"}:
            kind = "location"

        self._add_node(
            GraphNode(
                id=node_id,
                kind=kind,
                label=label,
                entity_type=element.entity_type,
                lemma=element.head_lemma,
                sentence_index=index,
                features=dict(element.features),
                mentions=[label],
            )
        )
        return node_id

    def _find_entity(self, label: str) -> str | None:
        wanted = label.lower()
        for node in self.nodes.values():
            if node.label.lower() == wanted or wanted in {m.lower() for m in node.mentions}:
                return node.id
        return None

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}{next(self._counter)}"

    def _add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node
        if self._graph is not None:
            self._graph.add_node(node.id, **node.model_dump())

    def _add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)
        if self._graph is not None:
            self._graph.add_edge(edge.source, edge.target, key=edge.relation, **edge.model_dump())

    # -- coreference -------------------------------------------------------

    def resolve_pronoun(self, element: FrameElement, index: int) -> Coreference:
        """Resolve a pronoun against earlier entities.

        Matching is on the grammatical features the morphology engine extracted -
        person, number, gender, animacy - plus recency. Confidence reflects how many
        candidates survived: a single match is confident, several is not, and none
        leaves the reference unresolved rather than guessed.
        """
        features = element.features
        wanted_gender = features.get("gender")
        wanted_number = features.get("number")

        candidates: list[GraphNode] = []
        for node in self.nodes.values():
            if node.kind not in {"entity", "location"}:
                continue
            if node.sentence_index > index:
                continue
            if node.label.lower() == element.text.strip().lower():
                continue

            if wanted_gender and node.features.get("gender"):
                if node.features["gender"] != wanted_gender:
                    continue
            if wanted_number and node.features.get("number"):
                if node.features["number"] != wanted_number:
                    continue

            # An inanimate pronoun must not resolve to a person, and vice versa.
            animate_pronoun = wanted_gender in {"masculine", "feminine"}
            node_is_person = node.entity_type == "PERSON"
            if animate_pronoun and node.entity_type and not node_is_person:
                continue
            if wanted_gender == "neuter" and node_is_person:
                continue

            candidates.append(node)

        if not candidates:
            return Coreference(
                mention=element.text, sentence_index=index, confidence=0.0
            )

        # An untyped noun survives the animacy filter above, so in "John owns a car.
        # He sold it." both John and the car are candidates for "he". A gendered
        # pronoun refers to a known person whenever one is available.
        if wanted_gender in {"masculine", "feminine"}:
            people = [node for node in candidates if node.entity_type == "PERSON"]
            if people:
                candidates = people

        # Prefer the most recently mentioned surviving candidate.
        candidates.sort(key=lambda n: (n.sentence_index, n.id), reverse=True)
        best = candidates[0]

        # Confidence falls as the number of equally plausible antecedents rises.
        confidence = round(1.0 / (1.0 + 0.6 * (len(candidates) - 1)), 4)

        return Coreference(
            mention=element.text,
            sentence_index=index,
            resolved_to=best.id,
            resolved_label=best.label,
            confidence=confidence,
            alternatives=[node.label for node in candidates[1:4]],
        )

    # -- querying ----------------------------------------------------------

    def entities(self) -> list[GraphNode]:
        return [n for n in self.nodes.values() if n.kind in {"entity", "location", "time"}]

    def events(self) -> list[GraphNode]:
        return [n for n in self.nodes.values() if n.kind in {"event", "state"}]

    def neighbours(self, node_id: str, relation: str | None = None) -> list[GraphNode]:
        return [
            self.nodes[edge.target]
            for edge in self.edges
            if edge.source == node_id
            and (relation is None or edge.relation == relation)
            and edge.target in self.nodes
        ]

    def role_values(self, relation: str) -> list[str]:
        """Every value ever seen in a role, e.g. all LOCATIONs mentioned so far."""
        return [
            self.nodes[edge.target].label
            for edge in self.edges
            if edge.relation == relation and edge.target in self.nodes
        ]

    def score_candidate(self, word: str, *, slot: str | None = None) -> CandidateVerdict | None:
        """Score a candidate word for consistency with the discourse so far.

        Returns ``None`` when the graph knows nothing relevant, which the feature
        extractor records as "no evidence" rather than as a neutral judgement.
        """
        if not self.enabled or not self.nodes or not word:
            return None

        wanted = word.strip().lower()
        if not wanted:
            return None

        for node in self.nodes.values():
            if node.label.lower() == wanted or wanted in {m.lower() for m in node.mentions}:
                return CandidateVerdict(
                    score=0.85,
                    reason=f"{word!r} is already established in this context as a {node.kind}",
                )

        if slot:
            roles = {
                "location": "LOCATION",
                "destination": "DESTINATION",
                "time": "TIME",
                "participants": "PARTICIPANT",
                "subject": "AGENT",
            }.get(slot)
            if roles and self.role_values(roles):
                # The slot has been filled before by something else: a brand new value
                # is normal, so this is mild evidence at most.
                return CandidateVerdict(score=0.55, reason=None)

        return None

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Node/edge lists, shaped for a graph view in the UI."""
        return {
            "nodes": [node.model_dump() for node in self.nodes.values()],
            "edges": [edge.model_dump() for edge in self.edges],
            "coreferences": [c.model_dump() for c in self.coreferences],
            "summary": self.describe(),
        }

    def serialized_token_estimate(self, tokenizer: Any | None = None) -> int:
        """Token count of a plain-text serialisation of the graph.

        Needed for any honest claim about context compression: comparing a token
        count against a node count would be meaningless, so the graph is serialised
        and measured with the same tokenizer as the raw text.
        """
        lines = []
        for edge in self.edges:
            source = self.nodes.get(edge.source)
            target = self.nodes.get(edge.target)
            if source and target:
                lines.append(f"{source.label} {edge.relation} {target.label}")
        text = "\n".join(lines)
        if tokenizer is None:
            # Rough fallback: whitespace words. Marked approximate by the caller.
            return len(text.split())
        try:
            return int(len(tokenizer(text)["input_ids"]))
        except Exception:
            return len(text.split())
