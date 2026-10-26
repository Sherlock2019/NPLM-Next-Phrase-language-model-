"""Coordinates with their frame and unit attached - never bare numbers.

Three frames are kept apart on purpose:

    image_pixel       pixels from the top-left corner of one image ("px")
    image_normalized  the same, divided by width/height, in [0, 1] ("normalized")
    world             a calibrated metric frame ("m", "cm" or "mm")

A pixel is not a metre. The only way from an image frame into the world frame
is an explicit :class:`Calibration`; without one, world quantities stay unknown.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CoordinateFrame(str, Enum):
    IMAGE_PIXEL = "image_pixel"
    IMAGE_NORMALIZED = "image_normalized"
    WORLD = "world"


FRAME_UNITS: dict[CoordinateFrame, frozenset[str]] = {
    CoordinateFrame.IMAGE_PIXEL: frozenset({"px"}),
    CoordinateFrame.IMAGE_NORMALIZED: frozenset({"normalized"}),
    CoordinateFrame.WORLD: frozenset({"m", "cm", "mm"}),
}
TO_METRES = {"m": 1.0, "cm": 0.01, "mm": 0.001}


class GeometryError(ValueError):
    """Coordinates used across frames, or in a frame that cannot answer the question."""


def _check_unit(frame: CoordinateFrame, unit: str) -> None:
    if unit not in FRAME_UNITS[frame]:
        raise ValueError(f"unit {unit!r} is not valid in frame {frame.value}; use {sorted(FRAME_UNITS[frame])}")


class Length(BaseModel):
    """A metric length. There is no pixel length: pixel sizes depend on depth."""

    value: float = Field(ge=0.0)
    unit: str = "m"

    @model_validator(mode="after")
    def _metric(self) -> "Length":
        if self.unit not in TO_METRES:
            raise ValueError(f"length unit {self.unit!r} is not metric; use m, cm or mm")
        return self

    @property
    def metres(self) -> float:
        return self.value * TO_METRES[self.unit]


class Point(BaseModel):
    frame: CoordinateFrame
    unit: str
    x: float
    y: float
    z: float | None = None
    calibration_id: str | None = Field(
        default=None, description="Required in the world frame: which calibration produced it"
    )

    @model_validator(mode="after")
    def _valid(self) -> "Point":
        _check_unit(self.frame, self.unit)
        if self.frame == CoordinateFrame.IMAGE_NORMALIZED and not (0 <= self.x <= 1 and 0 <= self.y <= 1):
            raise ValueError("normalized image coordinates must lie in [0, 1]")
        if self.frame != CoordinateFrame.WORLD and self.z is not None:
            raise ValueError("an image point has no depth; z is only valid in the world frame")
        if self.frame == CoordinateFrame.WORLD and not self.calibration_id:
            raise ValueError("a world point needs the calibration_id that produced it")
        return self

    def in_metres(self) -> tuple[float, float, float | None]:
        if self.frame != CoordinateFrame.WORLD:
            raise GeometryError(f"a {self.frame.value} point has no metric position without calibration")
        scale = TO_METRES[self.unit]
        return self.x * scale, self.y * scale, None if self.z is None else self.z * scale


class BoundingBox(BaseModel):
    frame: CoordinateFrame
    unit: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    calibration_id: str | None = None

    @model_validator(mode="after")
    def _valid(self) -> "BoundingBox":
        _check_unit(self.frame, self.unit)
        if self.x_max < self.x_min or self.y_max < self.y_min:
            raise ValueError("bounding box max must not be below min")
        if self.frame == CoordinateFrame.IMAGE_NORMALIZED and not all(
            0 <= v <= 1 for v in (self.x_min, self.y_min, self.x_max, self.y_max)
        ):
            raise ValueError("normalized image coordinates must lie in [0, 1]")
        if self.frame == CoordinateFrame.WORLD and not self.calibration_id:
            raise ValueError("a world box needs the calibration_id that produced it")
        return self

    def bottom_centre(self) -> tuple[float, float]:
        """Where an object standing on a surface touches it, in a side/oblique camera image."""
        return (self.x_min + self.x_max) / 2, self.y_max

    def centre(self) -> tuple[float, float]:
        return (self.x_min + self.x_max) / 2, (self.y_min + self.y_max) / 2

    def contains(self, point: Point) -> bool:
        require_same_frame(self, point)
        return self.x_min <= point.x <= self.x_max and self.y_min <= point.y <= self.y_max


class Calibration(BaseModel):
    """A plane homography from normalized image coordinates to world metres.

    It maps points on one plane (the table top) only. Anything off that plane -
    a falling object, the floor seen in perspective - is not calibrated by it.
    """

    id: str
    homography: list[list[float]] = Field(description="3x3, image_normalized -> world (m)")
    plane: str = Field(description="The world plane the homography is valid on, e.g. table_01 top")
    source: str = Field(description="How the calibration was obtained (measured markers, supplied, ...)")
    reference_point: Literal["bottom_centre", "centre"] = Field(
        default="bottom_centre",
        description="Which box point touches the plane: bottom_centre for a camera view, centre for top-down",
    )

    @model_validator(mode="after")
    def _shape(self) -> "Calibration":
        if len(self.homography) != 3 or any(len(row) != 3 for row in self.homography):
            raise ValueError("homography must be 3x3")
        return self

    def contact_point(self, box: "BoundingBox") -> Point:
        """The image point of a box that lies on the calibrated plane."""
        u, v = box.bottom_centre() if self.reference_point == "bottom_centre" else box.centre()
        return Point(frame=CoordinateFrame.IMAGE_NORMALIZED, unit="normalized", x=u, y=v)

    def footprint_radius(self, box: "BoundingBox") -> float | None:
        """Half the box width on the plane, in metres - only for a top-down view, where the box is the footprint."""
        if self.reference_point != "centre":
            return None  # in a side view the box is the silhouette, not the footprint
        v = box.centre()[1]
        left = self.to_world(Point(frame=CoordinateFrame.IMAGE_NORMALIZED, unit="normalized", x=box.x_min, y=v))
        right = self.to_world(Point(frame=CoordinateFrame.IMAGE_NORMALIZED, unit="normalized", x=box.x_max, y=v))
        return round(abs(right.x - left.x) / 2, 4)

    def to_world(self, point: Point) -> Point:
        if point.frame != CoordinateFrame.IMAGE_NORMALIZED:
            raise GeometryError("calibration maps image_normalized points only")
        h = self.homography
        u, v = point.x, point.y
        w = h[2][0] * u + h[2][1] * v + h[2][2]
        if abs(w) < 1e-12:
            raise GeometryError("point maps to infinity under this calibration")
        x = (h[0][0] * u + h[0][1] * v + h[0][2]) / w
        y = (h[1][0] * u + h[1][1] * v + h[1][2]) / w
        return Point(frame=CoordinateFrame.WORLD, unit="m", x=round(x, 6), y=round(y, 6), calibration_id=self.id)


def require_same_frame(a: Point | BoundingBox, b: Point | BoundingBox) -> None:
    if a.frame != b.frame:
        raise GeometryError(f"cannot compare {a.frame.value} with {b.frame.value} coordinates")
    if a.frame == CoordinateFrame.WORLD and a.calibration_id != b.calibration_id:
        raise GeometryError(
            f"world coordinates from different calibrations ({a.calibration_id} vs {b.calibration_id})"
        )


def distance_m(a: Point, b: Point) -> float:
    """Metric distance; only defined in one calibrated world frame."""
    require_same_frame(a, b)
    ax, ay, _ = a.in_metres()
    bx, by, _ = b.in_metres()
    return math.hypot(ax - bx, ay - by)


def normalize(point: Point, width_px: int, height_px: int) -> Point:
    if point.frame != CoordinateFrame.IMAGE_PIXEL:
        raise GeometryError("only image_pixel points can be normalized")
    if width_px <= 0 or height_px <= 0:
        raise GeometryError("image size must be positive")
    return Point(
        frame=CoordinateFrame.IMAGE_NORMALIZED,
        unit="normalized",
        x=min(max(point.x / width_px, 0.0), 1.0),
        y=min(max(point.y / height_px, 0.0), 1.0),
    )
