"""Multimodal demo endpoints: report which live backends work, and run live text.

    GET  /api/multimodal/status   which flows can run live, and what is missing
    POST /api/multimodal/text     live: MLM parser -> meaning -> ACM (needs a parser model and ACM)

The dashboard's Demo mode never calls these for results - it replays bundled
fixtures. Live mode is enabled only for the flows this status reports as
available; nothing falls back to a fixture while claiming to be live.
ACM is an optional, lazily imported dependency of this API.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LiveTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    action: Literal["none", "push_edge", "move_center"] = "push_edge"


def register(app: FastAPI, prefix: str) -> None:
    cache: dict[str, Any] = {}

    def pipeline():
        if "pipeline" not in cache:
            from splm.pipeline import SPLMPipeline

            cache["pipeline"] = SPLMPipeline()
        return cache["pipeline"]

    def parser_status() -> tuple[bool, str]:
        if "parser_ok" not in cache:
            try:
                analysis = pipeline().analyze("The cup is on the table.", language="en", detect_style=False)
                ok = bool(analysis.frames) and analysis.parsed
                cache["parser_ok"] = (ok, "parser ready" if ok else "; ".join(analysis.warnings) or "parser produced no frame")
            except Exception as exc:  # noqa: BLE001 - reported to the UI as a reason
                cache["parser_ok"] = (False, f"parser unavailable: {exc}")
        return cache["parser_ok"]

    def acm_status() -> tuple[bool, str]:
        try:
            import acm.multimodal  # noqa: F401
        except ImportError as exc:
            return False, f"ACM is not installed in the API environment ({exc})"
        return True, "ACM available"

    @app.get(f"{prefix}/multimodal/status")
    def multimodal_status() -> dict[str, Any]:
        acm_ok, acm_reason = acm_status()
        parser_ok, parser_reason = parser_status()
        vlm = bool(os.environ.get("SPLM_VLM_ENDPOINT"))
        missing_media = "Live image/video analysis is not wired into the dashboard yet"
        return {
            "live": {
                "text": acm_ok and parser_ok,
                "image": False,
                "video": False,
            },
            "reasons": {
                "text": "ready" if acm_ok and parser_ok else "; ".join(r for ok, r in ((acm_ok, acm_reason), (parser_ok, parser_reason)) if not ok),
                "image": f"{missing_media}; VLM endpoint {'configured' if vlm else 'not configured (SPLM_VLM_ENDPOINT)'}. "
                         "Use splm.meaning.adapters.ImageAdapter with OpenAICompatibleVLM from Python.",
                "video": f"{missing_media}; needs opencv, YOLO weights and a VLM endpoint. "
                         "Use splm.meaning.adapters.VideoAdapter with LiveVideoBackend from Python.",
            },
        }

    @app.post(f"{prefix}/multimodal/text")
    def multimodal_text(request: LiveTextRequest) -> dict[str, Any]:
        acm_ok, acm_reason = acm_status()
        parser_ok, parser_reason = parser_status()
        if not (acm_ok and parser_ok):
            raise HTTPException(status_code=503, detail=f"live text unavailable: {acm_reason if not acm_ok else parser_reason}")
        from acm.demo import live_text_result

        try:
            return live_text_result(request.text, request.action, pipeline())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
