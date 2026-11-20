"""Speech lab endpoints: talk to the model, get Phrase DNA and a spoken answer.

    GET  /api/speech/status              models, languages, modes, whether loaded
    POST /api/speech/turn                audio (base64) or text -> one mode, or all modes
    GET  /api/speech/benchmark/results   stored speech benchmark runs, newest first
    GET  /api/speech/benchmark/results/{run_id}

Audio travels as base64 inside JSON so the API needs no multipart dependency.
Models load on first use (or at /status?warm=true); nothing is faked when a model is
missing - the request fails with the loader's own message.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import threading
from typing import Any, Callable, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

#: ~30 s of 48 kHz WebM/Opus is well under this; WAV at 16 kHz mono is ~1 MB.
MAX_AUDIO_BYTES = 12 * 1024 * 1024


class TurnRequest(BaseModel):
    audio_base64: str | None = Field(default=None, description="Recorded audio (WebM/Ogg/WAV/MP3), base64")
    text: str | None = Field(default=None, max_length=1000, description="Typed input instead of audio")
    mode: Literal["base", "nplm", "nplm_validated", "compare"] = "nplm_validated"
    language: Literal["en", "fr", "vi"] | None = Field(default=None, description="None = let Whisper detect")
    speak: bool = True


def register(app: FastAPI, prefix: str, engine: Callable[[], Any], config: Any) -> None:
    state: dict[str, Any] = {"pipeline": None}
    lock = threading.Lock()

    def pipeline() -> Any:
        if state["pipeline"] is None:
            with lock:
                if state["pipeline"] is None:
                    from splm.speech.pipeline import SpeechPipeline

                    state["pipeline"] = SpeechPipeline(config, engine=engine())
        return state["pipeline"]

    if os.environ.get("SPLM_SPEECH_WARMUP", "").strip().lower() in {"1", "true", "yes"}:
        # Load Whisper, the voices and the answer model in the background at startup,
        # so the first spoken turn is not a minute of model loading.
        def _warm() -> None:
            try:
                instance = pipeline()
                instance.warmup()
                logger.info("speech lab warm")
            except Exception as exc:  # noqa: BLE001
                logger.warning("speech warmup failed: %s", exc)

        threading.Thread(target=_warm, name="speech-warmup", daemon=True).start()

    @app.get(f"{prefix}/speech/status")
    def speech_status(warm: bool = False) -> dict[str, Any]:
        from splm.speech.provenance import provenance

        info: dict[str, Any] = {"provenance": provenance(config)}
        try:
            instance = pipeline()
            if warm and not instance.warm:
                info["warmup_ms"] = instance.warmup()
            info.update(instance.describe())
            info["available"] = True
        except Exception as exc:  # noqa: BLE001 - shown in the UI as the reason
            logger.warning("speech lab unavailable: %s", exc)
            info.update({"available": False, "reason": str(exc)})
        return info

    @app.post(f"{prefix}/speech/turn")
    def speech_turn(request: TurnRequest) -> dict[str, Any]:
        from splm.speech.asr import AsrUnavailable
        from splm.speech.audio import AudioError

        if not request.audio_base64 and not (request.text or "").strip():
            raise HTTPException(status_code=422, detail="send audio_base64 or text")
        audio = None
        if request.audio_base64:
            payload = request.audio_base64.split(",", 1)[-1]  # tolerate data: URLs
            try:
                audio = base64.b64decode(payload, validate=False)
            except (binascii.Error, ValueError) as exc:
                raise HTTPException(status_code=422, detail=f"audio is not valid base64: {exc}") from exc
            if len(audio) > MAX_AUDIO_BYTES:
                raise HTTPException(status_code=413, detail="audio too large (max 12 MB)")

        instance = pipeline()
        try:
            if request.mode == "compare":
                return instance.compare(audio=audio, text=request.text, language=request.language,
                                        speak=request.speak)
            if audio is not None:
                turn = instance.run_audio(audio, request.mode, request.language, speak=request.speak)
            else:
                turn = instance.run_text(request.text or "", request.mode, request.language, speak=request.speak)
        except AudioError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except AsrUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"turns": {request.mode: turn.model_dump(mode="json")}, "shared_asr": False}

    @app.get(f"{prefix}/speech/benchmark/results")
    def speech_benchmark_results() -> dict[str, Any]:
        from splm.evaluation.store import list_results

        return {"results": list_results(_results_dir(config))}

    @app.get(f"{prefix}/speech/benchmark/results/{{run_id}}")
    def speech_benchmark_result(run_id: str) -> dict[str, Any]:
        from splm.evaluation.store import load_result

        if not run_id.replace("-", "").replace("_", "").isalnum():
            raise HTTPException(status_code=400, detail="invalid run id")
        payload = load_result(_results_dir(config), run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"no speech benchmark run {run_id!r}")
        return payload


def _results_dir(config: Any) -> Any:
    return config.results_dir / str(config.get("speech.benchmark.results_subdir", "speech"))
