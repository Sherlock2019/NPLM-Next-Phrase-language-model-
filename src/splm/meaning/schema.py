"""The shared meaning layer: what text, images and video say, in one schema.

MLM's Universal Phrase DNA (:mod:`splm.phrase.schema`) is the meaning of one
clause. This module adds what a scene needs on top of it, without replacing it:

    SceneEntity        a participant with a stable id (cup_01, cup_02)
    Observation        a property or relation of entities, with evidence
    SceneState         everything known at one moment, with frames and units
    MeaningEvent       something that happened - MLM roles + interval + evidence
    ProposedAction     an intervention that has NOT happened
    PredictedOutcome   possible future state changes from a named backend
    Goal               a stated, supplied or (explicitly marked) inferred goal
    OutcomeComparison  a prediction checked against what was observed later

Observed events, proposed actions and predictions live in separate lists of a
:class:`MeaningDocument` and are never merged. A missing role stays missing:
nothing here fills a purpose or an intention to complete a frame.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from splm.meaning.geometry import BoundingBox, Calibration, CoordinateFrame, Length, Point
from splm.phrase.schema import UniversalPhraseFrame

#: MLM's universal role inventory (language_packs/universal/semantic_roles.yaml),
#: mirrored here so schema validation needs no pack loading.
MLM_ROLES = frozenset(
    {
        "AGENT", "EXPERIENCER", "PATIENT", "THEME", "OBJECT", "RECIPIENT", "BENEFICIARY",
        "PARTICIPANT", "DESTINATION", "SOURCE", "LOCATION", "TIME", "MANNER",
        "INSTRUMENT", "CAUSE", "PURPOSE", "CONDITION",
    }
)
#: Roles that state an intention or reason. Only a stated source (text) may fill them.
INTENT_ROLES = frozenset({"PURPOSE", "CAUSE"})

ENTITY_ID = re.compile(r"^(self|[a-z][a-z0-9]*(?:_[a-z0-9]+)*_\d{2,})$")


class Status(str, Enum):
    """How a piece of meaning is known. Rendered as a label, never only as a colour."""

    OBSERVED = "observed"  # directly supported by the evidence
    INFERRED = "inferred"  # derived from observations by a stated rule or model
    ASSUMED = "assumed"  # supplied as a parameter, not observed
    PREDICTED = "predicted"  # a possible future, from a named backend
    UNKNOWN = "unknown"  # not established; kept, not guessed


class SourceType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    SIMULATION = "simulation"
    SUPPLIED = "supplied"  # given by a person or a scenario file


class BackendInfo(BaseModel):
    """Which component produced something, and whether it actually ran."""

    name: str
    version: str = "unknown"
    kind: Literal[
        "parser", "vlm", "detector", "tracker", "simulator", "world_model", "fixture_replay", "manual"
    ]
    live: bool = Field(description="False for fixture replay: recorded output, not live inference")
    config: dict[str, Any] = Field(default_factory=dict)


class TimeInterval(BaseModel):
    start_s: float = Field(ge=0.0)
    end_s: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _ordered(self) -> "TimeInterval":
        if self.end_s < self.start_s:
            raise ValueError("interval end is before its start")
        return self

    def overlaps(self, other: "TimeInterval") -> bool:
        return self.start_s <= other.end_s and other.start_s <= self.end_s


class EvidenceReference(BaseModel):
    """Where a claim comes from: which input, which frame, which time, which backend."""

    source_type: SourceType
    uri: str = Field(description="File path, URL or scenario id of the input")
    frame_index: int | None = Field(default=None, ge=0)
    timestamp_s: float | None = Field(default=None, ge=0.0)
    interval: TimeInterval | None = None
    region: BoundingBox | None = Field(default=None, description="Image region supporting the claim")
    text_span: str | None = None
    backend: BackendInfo
    extraction: str | None = Field(default=None, description="Prompt id, rule or method used")

    @model_validator(mode="after")
    def _anchored(self) -> "EvidenceReference":
        if self.source_type == SourceType.VIDEO and self.timestamp_s is None and self.interval is None:
            raise ValueError("video evidence needs a timestamp or an interval")
        if self.region is not None and self.region.frame == CoordinateFrame.WORLD:
            raise ValueError("an evidence region is an image region, not a world box")
        return self

    @property
    def time_end(self) -> float | None:
        """The latest moment this evidence depends on (for leakage checks)."""
        if self.interval is not None:
            return self.interval.end_s
        return self.timestamp_s


class TrackRef(BaseModel):
    """A tracker id. Only meaningful inside its own tracking session."""

    session_id: str
    track_id: int


class Geometry(BaseModel):
    image_box: BoundingBox | None = None
    position: Point | None = Field(default=None, description="Reference point; world frame when calibrated")
    footprint_radius: Length | None = Field(
        default=None, description="Radius of the contact footprint on its support (world, metric)"
    )
    extent: BoundingBox | None = Field(default=None, description="For surfaces: the support boundary")


class SceneEntity(BaseModel):
    """One participant. Two cups are cup_01 and cup_02 - never merged by class."""

    id: str
    cls: str = Field(description="Object class, e.g. cup, table, person")
    label: str | None = None
    tracks: list[TrackRef] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict, description="Visible attributes only")
    geometry: Geometry = Field(default_factory=Geometry)
    status: Status = Status.OBSERVED
    evidence: list[EvidenceReference] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_format(cls, value: str) -> str:
        if not ENTITY_ID.match(value):
            raise ValueError(f"entity id {value!r} must look like cup_01 (class + _NN) or be 'self'")
        return value

    @property
    def display(self) -> str:
        return self.label or self.id


class Observation(BaseModel):
    """A property of one entity, or a relation between two, with how it is known."""

    subject: str
    property: str | None = None
    relation: str | None = None
    object: str | None = None
    value: Any = None
    unit: str | None = None
    status: Status
    evidence: list[EvidenceReference] = Field(default_factory=list)
    detection_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    interpretation_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    note: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> "Observation":
        if (self.property is None) == (self.relation is None):
            raise ValueError("an observation is either a property or a relation")
        if self.relation is not None and self.object is None:
            raise ValueError(f"relation {self.relation!r} needs an object")
        if self.status == Status.OBSERVED and not self.evidence:
            raise ValueError("an observed fact needs evidence")
        return self


class SceneState(BaseModel):
    """Everything known about a scene at one moment."""

    timestamp_s: float | None = Field(default=None, ge=0.0)
    entities: list[SceneEntity] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    coordinate_frames: list[CoordinateFrame] = Field(default_factory=list)
    calibration: Calibration | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "SceneState":
        ids = [e.id for e in self.entities]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate entity ids: {sorted({i for i in ids if ids.count(i) > 1})}")
        known = set(ids)
        for obs in self.observations:
            for ref in (obs.subject, obs.object):
                if ref is not None and ref not in known:
                    raise ValueError(f"observation refers to unknown entity {ref!r}")
        for entity in self.entities:
            for item in (entity.geometry.image_box, entity.geometry.position, entity.geometry.extent):
                if item is None:
                    continue
                if item.frame not in self.coordinate_frames:
                    raise ValueError(f"{entity.id}: frame {item.frame.value} is not declared by the state")
                if item.frame == CoordinateFrame.WORLD and (
                    self.calibration is None or item.calibration_id != self.calibration.id
                ):
                    raise ValueError(f"{entity.id}: world coordinates need the state's calibration")
        return self

    def entity(self, entity_id: str) -> SceneEntity:
        for entity in self.entities:
            if entity.id == entity_id:
                return entity
        raise KeyError(entity_id)

    def relation(self, subject: str, relation: str) -> Observation | None:
        return next(
            (o for o in self.observations if o.subject == subject and o.relation == relation), None
        )


class RoleFiller(BaseModel):
    """Who or what fills an MLM role. Without an entity id, the filler is unresolved."""

    entity_id: str | None = None
    text: str
    status: Status = Status.OBSERVED


class MeaningEvent(BaseModel):
    """Something that happened (or was hypothesised to), in MLM's role terms."""

    id: str
    predicate: str = Field(description="Lemma, e.g. push, fall")
    roles: dict[str, list[RoleFiller]] = Field(default_factory=dict)
    interval: TimeInterval | None = None
    tense: Literal["past", "present"] = "past"
    negation: bool = False
    conditions: list[str] = Field(default_factory=list)
    status: Status = Status.OBSERVED
    hypothesis: bool = Field(default=False, description="True when not established by the evidence")
    causal_attribution: Literal["stated", "supported", "uncertain", "not_applicable"] = Field(
        default="not_applicable",
        description="Whether a cause/agent link is established; a change between frames is not a cause",
    )
    evidence: list[EvidenceReference] = Field(default_factory=list)
    frame: UniversalPhraseFrame | None = Field(default=None, description="The MLM frame, for text events")

    @model_validator(mode="after")
    def _valid(self) -> "MeaningEvent":
        unknown = set(self.roles) - MLM_ROLES
        if unknown:
            raise ValueError(f"unknown MLM roles {sorted(unknown)}")
        stated = any(e.source_type in {SourceType.TEXT, SourceType.SUPPLIED} for e in self.evidence)
        if (set(self.roles) & INTENT_ROLES) and not stated:
            raise ValueError("a purpose or cause may only come from stated (text or supplied) evidence")
        if self.status == Status.OBSERVED and not self.evidence:
            raise ValueError("an observed event needs evidence")
        if self.status in {Status.PREDICTED, Status.ASSUMED}:
            raise ValueError("predictions and assumptions are not events; use PredictedOutcome/ProposedAction")
        return self

    @property
    def time_end(self) -> float | None:
        ends = [e.time_end for e in self.evidence if e.time_end is not None]
        if self.interval is not None:
            ends.append(self.interval.end_s)
        return max(ends) if ends else None

    def entity_ids(self, role: str) -> list[str]:
        return [f.entity_id for f in self.roles.get(role, []) if f.entity_id]


class Quantity(BaseModel):
    value: float
    unit: str


class ProposedAction(BaseModel):
    """An intervention that has not (necessarily) happened. Never an observed event."""

    id: str
    predicate: str = Field(description="move, push, drop, ...")
    actor: str | None = Field(default=None, description="Entity id, 'self', or unknown")
    target: str
    parameters: dict[str, Quantity] = Field(default_factory=dict)
    destination: Point | None = None
    preconditions: list[str] = Field(default_factory=list)
    issued_at_s: float | None = Field(default=None, ge=0.0, description="Decision time T")


class Assumption(BaseModel):
    """A value the predictor used without observing it."""

    name: str
    value: Any = None
    unit: str | None = None
    reason: str


class StateChange(BaseModel):
    entity_id: str
    property: str
    before: Any = None
    after: Any = None
    unit: str | None = None
    status: Status = Status.PREDICTED


class OutcomeEvent(BaseModel):
    """A supported outcome interpretation: remains_supported, crosses_edge, falls, collides."""

    kind: str
    entity_id: str
    other_id: str | None = None
    at_s: float | None = None
    note: str | None = None


class UncertaintyReport(BaseModel):
    """Kinds of uncertainty kept apart. There is deliberately no combined score."""

    detection: str | None = None
    interpretation: str | None = None
    prediction: str | None = None
    rule_applicability: str | None = None
    simulation_assumptions: str | None = None


class PredictedOutcome(BaseModel):
    action_id: str | None = Field(default=None, description="None for the no-action branch")
    changes: list[StateChange] = Field(default_factory=list)
    events: list[OutcomeEvent] = Field(default_factory=list)
    horizon_s: float = Field(gt=0.0)
    backend: BackendInfo
    assumptions: list[Assumption] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    uncertainty: UncertaintyReport = Field(default_factory=UncertaintyReport)
    final_state: SceneState | None = None

    @model_validator(mode="after")
    def _predicted(self) -> "PredictedOutcome":
        for change in self.changes:
            if change.status not in {Status.PREDICTED, Status.UNKNOWN}:
                raise ValueError("a predicted outcome only holds predicted or unknown changes")
        return self


class DesiredState(BaseModel):
    entity_id: str
    property: str
    value: Any


class Goal(BaseModel):
    owner: str
    text: str
    source: Literal["stated", "supplied", "inferred"]
    desired: list[DesiredState] = Field(default_factory=list)
    frame: UniversalPhraseFrame | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class OutcomeComparison(BaseModel):
    action_id: str | None
    predicted: list[StateChange]
    observed: list[StateChange]
    metrics: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class MeaningDocument(BaseModel):
    """One input's meaning: a state timeline, events, proposals, goals, predictions - all separate."""

    source: EvidenceReference
    states: list[SceneState] = Field(default_factory=list)
    events: list[MeaningEvent] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)
    predictions: list[PredictedOutcome] = Field(default_factory=list)
    rejected_claims: list[dict[str, Any]] = Field(
        default_factory=list, description="Model claims the evidence does not support, with the reason"
    )
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ordered(self) -> "MeaningDocument":
        times = [s.timestamp_s for s in self.states if s.timestamp_s is not None]
        if times != sorted(times):
            raise ValueError("scene states must be in time order")
        ids = [e.id for e in self.events] + [a.id for a in self.proposed_actions]
        if len(ids) != len(set(ids)):
            raise ValueError("event and action ids must be unique")
        return self

    def state_at(self, t: float | None) -> SceneState:
        """The latest state at or before ``t`` (the only state not known by then is excluded)."""
        candidates = [s for s in self.states if t is None or s.timestamp_s is None or s.timestamp_s <= t]
        if not candidates:
            raise LookupError(f"no scene state available at or before t={t}")
        return candidates[-1]

    def available_at(self, t: float) -> "MeaningDocument":
        """Only what was knowable at time ``t``: the input for a prediction made at T.

        Later states and events (and every prediction) are removed, so frames after T
        can serve as evaluation targets but can never leak into prediction input.
        """
        def known(time_end: float | None) -> bool:
            return time_end is not None and time_end <= t

        return self.model_copy(
            update={
                "states": [s for s in self.states if s.timestamp_s is not None and s.timestamp_s <= t],
                "events": [e for e in self.events if known(e.time_end)],
                "proposed_actions": [
                    a for a in self.proposed_actions if a.issued_at_s is None or a.issued_at_s <= t
                ],
                "predictions": [],
                "notes": [*self.notes, f"restricted to information available at t={t}s"],
            },
            deep=True,
        )
