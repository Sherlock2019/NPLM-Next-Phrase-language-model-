"""Video -> MLM meaning: a time-ordered state timeline plus events.

    video -> decode + sample frames -> detect + track -> bounded segments
          -> temporal event interpretation -> identity + timestamp reconciliation
          -> MeaningDocument(states=[...], events=[...])

Rules kept by construction:

* Every state and event keeps its timestamp and links to supporting frames.
* Tracker ids are local to one tracking session. Entity ids come from an explicit
  association table, or from first appearance within the session - never from a
  shared class name.
* A change between frames is not a cause: an event whose agent link the
  extraction did not support gets ``causal_attribution="uncertain"``.
* Overlapping duplicate event descriptions are merged.
* :meth:`MeaningDocument.available_at` cuts the timeline for prediction at time T.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

from splm.meaning.adapters.base import AdapterError, BackendUnavailable, ExtractionBackend
from splm.meaning.geometry import BoundingBox, Calibration, CoordinateFrame, Length, Point
from splm.meaning.schema import (
    ENTITY_ID,
    INTENT_ROLES,
    MLM_ROLES,
    EvidenceReference,
    Geometry,
    MeaningDocument,
    MeaningEvent,
    Observation,
    RoleFiller,
    SceneEntity,
    SceneState,
    SourceType,
    Status,
    TimeInterval,
    TrackRef,
)

ALLOWED_VIDEO_TYPES = {".mp4", ".webm", ".mov", ".mkv", ".json"}


class _Detection(BaseModel):
    track_id: int
    cls: str = Field(alias="class")
    attributes: dict[str, Any] = Field(default_factory=dict)
    box_normalized: list[float]
    confidence: float | None = Field(default=None, ge=0, le=1)
    footprint_radius_m: float | None = Field(default=None, ge=0)


class _Frame(BaseModel):
    t: float = Field(ge=0)
    frame_index: int = Field(ge=0)
    detections: list[_Detection] = Field(default_factory=list)


class _SegmentEvent(BaseModel):
    predicate: str
    roles: dict[str, str] = Field(default_factory=dict)
    causal: str = "uncertain"
    confidence: float | None = Field(default=None, ge=0, le=1)


class _Segment(BaseModel):
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    events: list[_SegmentEvent] = Field(default_factory=list)


class VideoExtraction(BaseModel):
    media: str | None = None
    duration_s: float = Field(gt=0)
    tracking_session: str
    track_ids: dict[str, str] = Field(
        default_factory=dict, description="Explicit association: track id -> entity id (this session only)"
    )
    static_entities: list[dict[str, Any]] = Field(default_factory=list, description="Surfaces, e.g. the table")
    calibration: Calibration | None = None
    frames: list[_Frame]
    segments: list[_Segment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _timeline(self) -> "VideoExtraction":
        if not self.frames:
            raise ValueError("the video has no sampled frames")
        times = [f.t for f in self.frames]
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError("frame timestamps must be strictly increasing")
        if times[-1] > self.duration_s + 1e-6:
            raise ValueError("a frame timestamp is beyond the video duration")
        for seg in self.segments:
            if seg.end_s < seg.start_s:
                raise ValueError("segment end is before its start")
        return self


class VideoAdapter:
    def __init__(
        self,
        backend: ExtractionBackend,
        *,
        sample_fps: float = 2.0,
        segment_s: float = 1.0,
        max_frames: int = 120,
        max_segments: int = 30,
    ) -> None:
        if sample_fps <= 0 or segment_s <= 0 or max_frames <= 0 or max_segments <= 0:
            raise ValueError("sampling and segment limits must be positive")
        self.backend = backend
        self.sample_fps, self.segment_s = sample_fps, segment_s
        self.max_frames, self.max_segments = max_frames, max_segments

    def analyze(self, video: Path | str) -> MeaningDocument:
        path = Path(video)
        if path.suffix.lower() not in ALLOWED_VIDEO_TYPES:
            raise AdapterError(f"unsupported video type {path.suffix!r}")
        raw = self.backend.extract(
            path, sample_fps=self.sample_fps, segment_s=self.segment_s,
            max_frames=self.max_frames, max_segments=self.max_segments,
        )
        try:
            extraction = VideoExtraction.model_validate(raw)
        except ValidationError as exc:
            raise AdapterError(f"video extraction does not match the schema:\n{exc}") from exc
        if len(extraction.frames) > self.max_frames:
            raise AdapterError(f"{len(extraction.frames)} frames exceed the limit of {self.max_frames}")
        if len(extraction.segments) > self.max_segments:
            raise AdapterError(f"{len(extraction.segments)} segments exceed the limit of {self.max_segments}")
        return self.build(extraction, uri=str(path))

    # -- building ------------------------------------------------------------

    def build(self, ex: VideoExtraction, *, uri: str) -> MeaningDocument:
        info = self.backend.info
        source = EvidenceReference(
            source_type=SourceType.VIDEO, uri=uri, backend=info,
            interval=TimeInterval(start_s=0, end_s=ex.duration_s), extraction="video-extraction-v1",
        )
        ids = self._entity_ids(ex)
        statics = [self._static(item, ex, source) for item in ex.static_entities]
        table = next((s for s in statics if s.cls == "table"), None)
        frames = [CoordinateFrame.IMAGE_NORMALIZED] + ([CoordinateFrame.WORLD] if ex.calibration else [])

        doc = MeaningDocument(source=source)
        for frame in ex.frames:
            evidence = EvidenceReference(
                source_type=SourceType.VIDEO, uri=uri, frame_index=frame.frame_index,
                timestamp_s=frame.t, backend=info, extraction="video-extraction-v1",
            )
            entities = [s.model_copy(update={"evidence": [evidence]}) for s in statics]
            observations: list[Observation] = []
            for det in frame.detections:
                entity_id = ids[det.track_id]
                box = BoundingBox(frame=CoordinateFrame.IMAGE_NORMALIZED, unit="normalized",
                                  x_min=det.box_normalized[0], y_min=det.box_normalized[1],
                                  x_max=det.box_normalized[2], y_max=det.box_normalized[3])
                ev = evidence.model_copy(update={"region": box})
                geometry = Geometry(image_box=box)
                if det.footprint_radius_m is not None:
                    geometry.footprint_radius = Length(value=det.footprint_radius_m)
                contact = (ex.calibration.contact_point(box) if ex.calibration is not None else
                           Point(frame=CoordinateFrame.IMAGE_NORMALIZED, unit="normalized", x=box.bottom_centre()[0],
                                 y=box.bottom_centre()[1]))
                on_table = (table is not None and table.geometry.image_box is not None
                            and table.geometry.image_box.contains(contact))
                if ex.calibration is not None and on_table:
                    # The calibration is valid on the table plane only; off it, position stays unknown.
                    geometry.position = ex.calibration.to_world(contact)
                    radius = ex.calibration.footprint_radius(box)
                    if radius is not None and geometry.footprint_radius is None:
                        geometry.footprint_radius = Length(value=radius)
                entities.append(SceneEntity(
                    id=entity_id, cls=det.cls, attributes=dict(det.attributes), geometry=geometry,
                    tracks=[TrackRef(session_id=ex.tracking_session, track_id=det.track_id)], evidence=[ev],
                ))
                if table is not None and det.cls != "person" and det.cls != "pusher":
                    observations.append(Observation(
                        subject=entity_id, relation="on" if on_table else "not_on", object=table.id,
                        status=Status.INFERRED, evidence=[ev], detection_confidence=det.confidence,
                        note="from the contact point's position relative to the table's image region",
                    ))
            doc.states.append(SceneState(
                timestamp_s=frame.t, entities=entities, observations=observations,
                coordinate_frames=frames, calibration=ex.calibration,
            ))
        doc.events = self._events(ex, ids, uri, info)
        return doc

    @staticmethod
    def _entity_ids(ex: VideoExtraction) -> dict[int, str]:
        ids: dict[int, str] = {}
        counters: dict[str, int] = {}
        taken = set(ex.track_ids.values())
        for frame in ex.frames:
            for det in frame.detections:
                if det.track_id in ids:
                    continue
                explicit = ex.track_ids.get(str(det.track_id))
                if explicit:
                    ids[det.track_id] = explicit
                    continue
                cls = det.cls.lower()
                n = counters.get(cls, 0) + 1
                while f"{cls}_{n:02d}" in taken:
                    n += 1
                counters[cls] = n
                ids[det.track_id] = f"{cls}_{n:02d}"
                taken.add(ids[det.track_id])
        return ids

    @staticmethod
    def _static(item: dict[str, Any], ex: VideoExtraction, source: EvidenceReference) -> SceneEntity:
        box = BoundingBox(frame=CoordinateFrame.IMAGE_NORMALIZED, unit="normalized", **dict(zip(
            ("x_min", "y_min", "x_max", "y_max"), item["box_normalized"])))
        geometry = Geometry(image_box=box)
        if "extent_m" in item and ex.calibration is not None:
            x0, y0, x1, y1 = item["extent_m"]
            geometry.extent = BoundingBox(frame=CoordinateFrame.WORLD, unit="m", calibration_id=ex.calibration.id,
                                          x_min=x0, y_min=y0, x_max=x1, y_max=y1)
        return SceneEntity(id=item["id"], cls=item["class"], attributes=item.get("attributes", {}),
                           geometry=geometry, evidence=[source])

    def _events(self, ex: VideoExtraction, ids: dict[int, str], uri: str, info) -> list[MeaningEvent]:
        merged: list[tuple[str, dict[str, str], TimeInterval, str, list[EvidenceReference]]] = []
        for seg in sorted(ex.segments, key=lambda s: (s.start_s, s.end_s)):
            interval = TimeInterval(start_s=seg.start_s, end_s=seg.end_s)
            evidence = EvidenceReference(source_type=SourceType.VIDEO, uri=uri, interval=interval,
                                         backend=info, extraction="segment-interpretation")
            for event in seg.events:
                roles = {}
                for role, filler in event.roles.items():
                    if role not in MLM_ROLES:
                        raise AdapterError(f"unknown MLM role {role!r} in segment event")
                    if role in INTENT_ROLES:
                        continue  # video does not show purposes or reasons; leave the role empty
                    roles[role] = ids[int(filler.split(":", 1)[1])] if filler.startswith("track:") else filler
                key = (event.predicate, tuple(sorted(roles.items())))
                for item in merged:
                    if (item[0], tuple(sorted(item[1].items()))) == key and item[2].overlaps(interval):
                        item[2].start_s = min(item[2].start_s, interval.start_s)
                        item[2].end_s = max(item[2].end_s, interval.end_s)
                        item[4].append(evidence)
                        break
                else:
                    causal = event.causal if event.causal in {"supported", "uncertain"} else "uncertain"
                    merged.append((event.predicate, roles, interval, causal, [evidence]))
        events = []
        for number, (predicate, roles, interval, causal, evidence) in enumerate(
            sorted(merged, key=lambda m: (m[2].start_s, m[2].end_s)), start=1
        ):
            fillers = {r: [RoleFiller(entity_id=v if ENTITY_ID.match(v) else None, text=v)] for r, v in roles.items()}
            if "AGENT" not in roles:
                # Nothing visible did it. An earlier event may have caused it - the frames
                # show the order, not the cause - so the attribution stays uncertain.
                causal = "uncertain"
            events.append(MeaningEvent(
                id=f"ev_{number:02d}", predicate=predicate, roles=fillers, interval=interval, status=Status.OBSERVED,
                causal_attribution=causal, evidence=evidence,
            ))
        return events


class LiveVideoBackend:
    """Decode + sample + track + interpret, with optional heavy dependencies.

    Needs ``opencv-python`` for decoding, a :class:`~splm.meaning.adapters.models.YoloTracker`
    and a :class:`~splm.meaning.adapters.models.OpenAICompatibleVLM`. Missing pieces raise
    :class:`BackendUnavailable`; nothing is substituted.
    """

    def __init__(self, tracker, vlm, *, tracking_session: str = "live") -> None:
        self.tracker, self.vlm, self.session = tracker, vlm, tracking_session
        from splm.meaning.schema import BackendInfo

        self.info = BackendInfo(name="live-video", kind="tracker", live=True,
                                config={"tracker": tracker.info.model_dump(), "vlm": vlm.info.model_dump()})

    def extract(self, media: Path, *, sample_fps: float, segment_s: float, max_frames: int, max_segments: int, **_: Any) -> dict[str, Any]:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise BackendUnavailable("video decoding needs opencv-python (pip install 'splm[vision]')") from exc
        capture = cv2.VideoCapture(str(media))
        if not capture.isOpened():
            raise AdapterError(f"cannot read video {media}")
        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        if fps <= 0:
            raise AdapterError("the video has no frame rate / timestamps")
        step = max(1, round(fps / sample_fps))
        frames, images, index = [], [], 0
        while len(frames) < max_frames:
            ok, image = capture.read()
            if not ok:
                break
            if index % step == 0:
                t = round(index / fps, 3)
                frames.append({"t": t, "frame_index": index, "detections": self.tracker.track(image)})
                images.append((t, image))
            index += 1
        capture.release()
        if not frames:
            raise AdapterError("the video is empty or unreadable")
        duration = index / fps
        segments = []
        start = 0.0
        while start < duration and len(segments) < max_segments:
            end = min(start + segment_s, duration)
            clip = [img for t, img in images if start <= t <= end]
            if clip:
                segments.append({"start_s": start, "end_s": end, "events": self.vlm.describe_segment(clip)})
            start = end
        return {"duration_s": duration, "tracking_session": self.session, "frames": frames, "segments": segments}
