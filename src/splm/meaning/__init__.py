"""The shared MLM meaning layer for text, images and video.

Text keeps going through MLM's parser into Universal Phrase DNA. Images and video
are extracted (by a VLM, a detector/tracker, or a replayed fixture) into the same
vocabulary - entities with stable ids, observations, a state timeline, events in
MLM's semantic roles - and converted straight into frames for ACM
(:mod:`splm.meaning.frames`), without rendering anything to prose.
"""

from splm.meaning.geometry import (
    BoundingBox,
    Calibration,
    CoordinateFrame,
    GeometryError,
    Length,
    Point,
    distance_m,
)
from splm.meaning.schema import (
    Assumption,
    BackendInfo,
    DesiredState,
    EvidenceReference,
    Geometry,
    Goal,
    MeaningDocument,
    MeaningEvent,
    Observation,
    OutcomeComparison,
    OutcomeEvent,
    PredictedOutcome,
    ProposedAction,
    Quantity,
    RoleFiller,
    SceneEntity,
    SceneState,
    SourceType,
    StateChange,
    Status,
    TimeInterval,
    TrackRef,
    UncertaintyReport,
)

__all__ = [
    "Assumption", "BackendInfo", "BoundingBox", "Calibration", "CoordinateFrame", "DesiredState",
    "EvidenceReference", "Geometry", "GeometryError", "Goal", "Length", "MeaningDocument", "MeaningEvent",
    "Observation", "OutcomeComparison", "OutcomeEvent", "Point", "PredictedOutcome", "ProposedAction",
    "Quantity", "RoleFiller", "SceneEntity", "SceneState", "SourceType", "StateChange", "Status",
    "TimeInterval", "TrackRef", "UncertaintyReport", "distance_m",
]
