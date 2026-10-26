"""Adapter plumbing: errors, fixture replay, and the guard for media content.

Every adapter turns one input into a :class:`MeaningDocument`. Model backends are
optional and loaded lazily; recorded model output can be replayed from a fixture,
and a replay is always labelled as one (``BackendInfo.live = False``).

Media content is data. Text that appears inside an image, a video or a model
response is never executed, never followed as an instruction and never used to
choose a tool - it can only become a quoted attribute value.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from splm.meaning.schema import BackendInfo


class AdapterError(ValueError):
    """An input or a model response the adapter cannot turn into valid meaning."""


class BackendUnavailable(RuntimeError):
    """A requested live backend is not installed or not reachable. Never silently replaced."""


class ExtractionBackend(Protocol):
    info: BackendInfo

    def extract(self, media: Path, **kwargs: Any) -> dict[str, Any]: ...


class FixtureReplay:
    """Returns a committed extraction instead of running a model.

    The fixture records what a model said for one specific input. It is not
    inference on any other file: replaying it for a different input is refused.
    """

    def __init__(self, fixture: Path | str, *, kind: str = "fixture_replay") -> None:
        self.path = Path(fixture)
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise AdapterError(f"fixture not found: {self.path}") from exc
        except json.JSONDecodeError as exc:
            raise AdapterError(f"fixture is not valid JSON: {self.path}: {exc}") from exc
        recorded = self.data.get("recorded_backend", {})
        self.info = BackendInfo(
            name=f"fixture-replay:{self.path.name}",
            version=str(self.data.get("version", "1")),
            kind="fixture_replay",
            live=False,
            config={"recorded_backend": recorded, "media": self.data.get("media")},
        )

    def extract(self, media: Path | str | None = None, **_: Any) -> dict[str, Any]:
        expected = self.data.get("media")
        if media is not None and expected is not None and Path(media).name != Path(expected).name:
            raise AdapterError(
                f"fixture {self.path.name} records {expected!r}, not {Path(media).name!r}: "
                "a replay is not an analysis of other media"
            )
        return self.data


def parse_model_json(raw: str) -> dict[str, Any]:
    """Parse a model's JSON answer. Code fences are tolerated; anything else is an error."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"model response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterError("model response must be a JSON object")
    return data
