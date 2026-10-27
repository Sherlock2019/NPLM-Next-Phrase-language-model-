"""Multimodal demo endpoints: report which live backends work, and run live text.

    GET  /api/multimodal/status   which flows can run live, and what is missing
    POST /api/multimodal/text     live: MLM parser -> meaning -> ACM (needs a parser model and ACM)
    POST /api/acm/phrase          live: any action sentence (+ context) -> ACM's full blast radius
    POST /api/acm/ask             live: a question about that action -> ACM's answer in Phrase DNA,
                                  worded by the local LLM from ACM's facts (acm.llm)
    POST /api/acm/llm/plan        LLM: a physics question -> object, intent and hypothetical action
    POST /api/acm/llm/answer      LLM: question + simulator/library facts -> answer in Phrase DNA

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


class LivePhraseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000, description="The action sentence")
    context: list[str] = Field(default_factory=list, max_length=10, description="Earlier sentences")


class AskRequest(LivePhraseRequest):
    question: str = Field(min_length=1, max_length=500, description="A question about the action")
    llm: bool = Field(default=True, description="Also have the local LLM word the answer from ACM's facts")


class PlanRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    objects: list[dict[str, Any]] = Field(max_length=20)
    selected: str = Field(min_length=1, max_length=80)


class FactsRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    facts: dict[str, Any]


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
        try:
            from acm import llm

            llm_ok, llm_reason = llm.status()
        except ImportError as exc:
            llm_ok, llm_reason = False, f"ACM is not installed ({exc})"
        return {
            "live": {
                "text": acm_ok and parser_ok,
                "image": False,
                "video": False,
                "llm": llm_ok,
            },
            "reasons": {
                "llm": llm_reason,
                "text": "ready" if acm_ok and parser_ok else "; ".join(r for ok, r in ((acm_ok, acm_reason), (parser_ok, parser_reason)) if not ok),
                "image": f"{missing_media}; VLM endpoint {'configured' if vlm else 'not configured (SPLM_VLM_ENDPOINT)'}. "
                         "Use splm.meaning.adapters.ImageAdapter with OpenAICompatibleVLM from Python.",
                "video": f"{missing_media}; needs opencv, YOLO weights and a VLM endpoint. "
                         "Use splm.meaning.adapters.VideoAdapter with LiveVideoBackend from Python.",
            },
        }

    @app.post(f"{prefix}/acm/phrase")
    def acm_phrase(request: LivePhraseRequest) -> dict[str, Any]:
        """Live: MLM parses context + action; ACM predicts the whole blast radius."""
        acm_ok, acm_reason = acm_status()
        parser_ok, parser_reason = parser_status()
        if not (acm_ok and parser_ok):
            raise HTTPException(status_code=503, detail=f"live phrase unavailable: {acm_reason if not acm_ok else parser_reason}")
        from acm.demo import live_phrase_result

        try:
            return live_phrase_result(request.text, [c for c in request.context if c.strip()], pipeline())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(f"{prefix}/acm/ask")
    def acm_ask(request: AskRequest) -> dict[str, Any]:
        """Live: MLM parses the question; ACM answers it from the action's report, in Phrase DNA."""
        acm_ok, acm_reason = acm_status()
        parser_ok, parser_reason = parser_status()
        if not (acm_ok and parser_ok):
            raise HTTPException(status_code=503, detail=f"live ask unavailable: {acm_reason if not acm_ok else parser_reason}")
        from acm.ask import ask
        from acm.engine import ConsequenceEngine

        context = [c for c in request.context if c.strip()]
        if "engine" not in cache:
            cache["engine"] = ConsequenceEngine(pipeline=pipeline())
        engine = cache["engine"]
        # A chat asks many questions about one action: parse and predict it once.
        reports: dict[tuple, Any] = cache.setdefault("reports", {})
        key = (request.text.strip(), tuple(context))
        if key not in reports:
            if len(reports) >= 64:
                reports.pop(next(iter(reports)))
            reports[key] = engine.analyze(request.text, context=context)
        try:
            result = ask(request.text, context, request.question, pipeline(), engine=engine, report=reports[key])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if request.llm:
            from acm import llm

            try:
                result["llm"] = llm.answer(request.question, llm.phrase_facts(result), kind="phrase")
            except llm.LLMUnavailable as exc:
                result["llm"] = {"error": str(exc)}  # ACM's own answer still stands
        return result

    @app.post(f"{prefix}/acm/llm/plan")
    def acm_llm_plan(request: PlanRequest) -> dict[str, Any]:
        from acm import llm

        try:
            return llm.physics_plan(request.question, request.objects, request.selected)
        except llm.LLMUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post(f"{prefix}/acm/llm/answer")
    def acm_llm_answer(request: FactsRequest) -> dict[str, Any]:
        from acm import llm

        try:
            return llm.answer(request.question, request.facts, kind="physics")
        except llm.LLMUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

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
