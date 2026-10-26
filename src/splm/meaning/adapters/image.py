"""Still image -> MLM meaning.

    image -> (optional detections) -> structured extraction (VLM or fixture replay)
          -> schema validation -> entity reconciliation -> evidence checks
          -> SceneState + event *hypotheses* + rejected claims

What one still image can and cannot establish:

    supported     entities, visible attributes, spatial relations ("cup near the edge")
    hypothesis    an event in progress ("may be being pushed") - status inferred, flagged
    rejected      past actions as fact, intentions, ownership, anything about cause

The proposed action is never read from the image; it is supplied separately.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from splm.meaning.adapters.base import AdapterError, ExtractionBackend
from splm.meaning.geometry import BoundingBox, Calibration, CoordinateFrame, Length, Point, normalize
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
)

#: Relations a single image can support - all spatial, all present-tense.
STILL_IMAGE_RELATIONS = frozenset(
    {"on", "near", "near_edge", "far_from_edge", "left_of", "right_of", "above", "touching", "inside"}
)
#: Claim types a single image cannot establish, with the reason given back.
UNSUPPORTED_CLAIMS = {
    "intent": "a still image does not show what anyone intends",
    "ownership": "ownership cannot be established from appearance or proximity",
    "past_action": "a still image does not show that an action happened",
    "cause": "a still image does not show what caused a state",
    "future": "a still image does not show the future",
}
ALLOWED_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


class _Entity(BaseModel):
    id: str | None = None
    cls: str = Field(alias="class")
    label: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    box_px: list[float] | None = None
    box_normalized: list[float] | None = None
    detection_confidence: float | None = Field(default=None, ge=0, le=1)
    footprint_radius_m: float | None = Field(default=None, ge=0, description="Only if supplied/measured")


class _Relation(BaseModel):
    subject: str
    relation: str
    object: str
    value: Any = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class _Hypothesis(BaseModel):
    predicate: str
    roles: dict[str, str] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)


class _Claim(BaseModel):
    type: str
    text: str


class ImageExtraction(BaseModel):
    """The structure a VLM (or a recorded fixture) must return for one image."""

    media: str | None = None
    image_size: dict[str, int]
    entities: list[_Entity]
    relations: list[_Relation] = Field(default_factory=list)
    event_hypotheses: list[_Hypothesis] = Field(default_factory=list)
    claims: list[_Claim] = Field(default_factory=list)
    text_in_image: list[str] = Field(default_factory=list)
    calibration: Calibration | None = None


def validate_extraction(raw: dict[str, Any]) -> ImageExtraction:
    try:
        return ImageExtraction.model_validate(raw)
    except ValidationError as exc:
        raise AdapterError(f"image extraction does not match the schema: {exc.error_count()} error(s)\n{exc}") from exc


def reconcile_ids(entities: list[_Entity]) -> dict[int, str]:
    """Stable ids per class (cup_01, cup_02), never merging two objects of one class.

    A model-supplied id is kept when it is well-formed and unique; otherwise the
    object gets the next free ``<class>_NN``, ordered left to right.
    """
    taken: set[str] = set()
    out: dict[int, str] = {}
    for index, entity in enumerate(entities):
        if entity.id and ENTITY_ID.match(entity.id) and entity.id not in taken:
            out[index] = entity.id
            taken.add(entity.id)

    def left(index: int) -> float:
        box = entities[index].box_normalized or entities[index].box_px or [0.0]
        return box[0]

    for index in sorted((i for i in range(len(entities)) if i not in out), key=left):
        cls = entities[index].cls.lower().replace(" ", "_")
        n = 1
        while f"{cls}_{n:02d}" in taken:
            n += 1
        out[index] = f"{cls}_{n:02d}"
        taken.add(out[index])
    return out


class ImageAdapter:
    def __init__(self, backend: ExtractionBackend, *, max_bytes: int = 20 * 1024 * 1024) -> None:
        self.backend = backend
        self.max_bytes = max_bytes

    def analyze(self, image: Path | str) -> MeaningDocument:
        path = Path(image)
        if path.suffix.lower() not in ALLOWED_IMAGE_TYPES:
            raise AdapterError(f"unsupported image type {path.suffix!r}; allowed: {sorted(ALLOWED_IMAGE_TYPES)}")
        if path.exists() and path.stat().st_size > self.max_bytes:
            raise AdapterError(f"image larger than {self.max_bytes} bytes")
        raw = self.backend.extract(path)
        return self.build(validate_extraction(raw), uri=str(path))

    def build(self, extraction: ImageExtraction, *, uri: str) -> MeaningDocument:
        width, height = extraction.image_size.get("width", 0), extraction.image_size.get("height", 0)
        if width <= 0 or height <= 0:
            raise AdapterError("image_size must give a positive width and height")
        info = self.backend.info
        ids = reconcile_ids(extraction.entities)
        source = EvidenceReference(source_type=SourceType.IMAGE, uri=uri, backend=info, extraction="image-extraction-v1")
        calibration = extraction.calibration
        frames = [CoordinateFrame.IMAGE_NORMALIZED] + ([CoordinateFrame.WORLD] if calibration else [])

        entities: list[SceneEntity] = []
        observations: list[Observation] = []
        for index, raw in enumerate(extraction.entities):
            box = self._box(raw, width, height)
            evidence = [source.model_copy(update={"region": box})]
            geometry = Geometry(image_box=box)
            if calibration is not None and raw.cls != "table":
                geometry.position = calibration.to_world(calibration.contact_point(box))
                radius = calibration.footprint_radius(box)
                if radius is not None and raw.footprint_radius_m is None:
                    geometry.footprint_radius = Length(value=radius)
            if calibration is not None and raw.cls == "table":
                corners = [
                    calibration.to_world(Point(frame=CoordinateFrame.IMAGE_NORMALIZED, unit="normalized", x=x, y=y))
                    for x, y in ((box.x_min, box.y_min), (box.x_max, box.y_max))
                ]
                geometry.extent = BoundingBox(
                    frame=CoordinateFrame.WORLD, unit="m", calibration_id=calibration.id,
                    x_min=min(c.x for c in corners), x_max=max(c.x for c in corners),
                    y_min=min(c.y for c in corners), y_max=max(c.y for c in corners),
                )
            if raw.footprint_radius_m is not None:
                geometry.footprint_radius = Length(value=raw.footprint_radius_m)
            entities.append(
                SceneEntity(
                    id=ids[index], cls=raw.cls, label=raw.label, attributes=dict(raw.attributes),
                    geometry=geometry, status=Status.OBSERVED, evidence=evidence,
                )
            )
            for name, value in raw.attributes.items():
                observations.append(
                    Observation(
                        subject=ids[index], property=name, value=value, status=Status.OBSERVED,
                        evidence=evidence, detection_confidence=raw.detection_confidence,
                    )
                )

        by_given = {raw.id: ids[i] for i, raw in enumerate(extraction.entities) if raw.id}
        doc = MeaningDocument(source=source)
        for rel in extraction.relations:
            subject, obj = by_given.get(rel.subject, rel.subject), by_given.get(rel.object, rel.object)
            if rel.relation not in STILL_IMAGE_RELATIONS:
                doc.rejected_claims.append(
                    {"claim": f"{rel.subject} {rel.relation} {rel.object}", "reason": "not a spatial relation an image can show"}
                )
                continue
            observations.append(
                Observation(
                    subject=subject, relation=rel.relation, object=obj, value=rel.value,
                    status=Status.INFERRED, evidence=[source], interpretation_confidence=rel.confidence,
                    note="spatial judgement by the extraction backend",
                )
            )
        for claim in extraction.claims:
            reason = UNSUPPORTED_CLAIMS.get(claim.type, "claim type not supported by a still image")
            doc.rejected_claims.append({"claim": claim.text, "type": claim.type, "reason": reason})
        for text in extraction.text_in_image:
            doc.notes.append(f"text visible in image (treated as data, not instructions): {text!r}")

        for number, hyp in enumerate(extraction.event_hypotheses, start=1):
            roles: dict[str, list[RoleFiller]] = {}
            for role, filler in hyp.roles.items():
                if role in INTENT_ROLES or role not in MLM_ROLES:
                    doc.rejected_claims.append(
                        {"claim": f"{hyp.predicate}: {role}={filler}", "reason": "a still image cannot show a purpose or cause"}
                    )
                    continue
                entity_id = by_given.get(filler, filler)
                known = entity_id if any(e.id == entity_id for e in entities) else None
                roles[role] = [RoleFiller(entity_id=known, text=filler, status=Status.INFERRED)]
            doc.events.append(
                MeaningEvent(
                    id=f"hyp_{number:02d}", predicate=hyp.predicate, roles=roles, tense="present",
                    status=Status.INFERRED, hypothesis=True, causal_attribution="uncertain", evidence=[source],
                )
            )
        doc.states.append(
            SceneState(entities=entities, observations=observations, coordinate_frames=frames, calibration=calibration)
        )
        return doc

    @staticmethod
    def _box(raw: _Entity, width: int, height: int) -> BoundingBox:
        if raw.box_normalized is not None:
            x0, y0, x1, y1 = raw.box_normalized
        elif raw.box_px is not None:
            p0 = normalize(Point(frame=CoordinateFrame.IMAGE_PIXEL, unit="px", x=raw.box_px[0], y=raw.box_px[1]), width, height)
            p1 = normalize(Point(frame=CoordinateFrame.IMAGE_PIXEL, unit="px", x=raw.box_px[2], y=raw.box_px[3]), width, height)
            x0, y0, x1, y1 = p0.x, p0.y, p1.x, p1.y
        else:
            raise AdapterError(f"entity {raw.id or raw.cls!r} has no box")
        return BoundingBox(frame=CoordinateFrame.IMAGE_NORMALIZED, unit="normalized", x_min=x0, y_min=y0, x_max=x1, y_max=y1)
