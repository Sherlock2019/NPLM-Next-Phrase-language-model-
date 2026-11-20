"""Multilingual text-to-speech with per-language Hugging Face VITS checkpoints.

Default voices are Meta's MMS-TTS models (``facebook/mms-tts-{eng,fra,vie}``),
CC-BY-NC 4.0. Text is synthesised sentence by sentence so the first chunk is ready
early; ``first_chunk_ms`` is what time-to-first-audio is built on.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

import numpy as np
from pydantic import BaseModel

from splm.device import resolve_device

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()
_SENTENCE = re.compile(r"(?<=[.!?。])\s+")


class TtsUnavailable(RuntimeError):
    """No usable voice for the requested language."""


class TtsResult(BaseModel):
    language: str
    model_id: str
    sample_rate: int
    audio_seconds: float
    latency_ms: float
    first_chunk_ms: float
    chunks: int

    model_config = {"arbitrary_types_allowed": True}


class MultilingualTTS:
    """One lazily loaded VITS model per language."""

    def __init__(self, voices: dict[str, str], *, device: str = "auto",
                 chunk_by_sentence: bool = True, max_characters: int = 600,
                 seed: int | None = 0) -> None:
        self.seed = seed
        self.voices = {str(k): str(v) for k, v in (voices or {}).items()}
        self.requested_device = device
        self.chunk_by_sentence = chunk_by_sentence
        self.max_characters = int(max_characters)
        self._models: dict[str, tuple[Any, Any]] = {}
        self._device = "cpu"
        self.load_times_ms: dict[str, float] = {}

    @classmethod
    def from_config(cls, config: Any) -> "MultilingualTTS":
        cfg = config.get("speech.tts", {}) or {}
        return cls(
            voices=cfg.get("voices", {}) or {},
            device=str(cfg.get("device", "auto")),
            chunk_by_sentence=bool(cfg.get("chunk_by_sentence", True)),
            max_characters=int(cfg.get("max_characters", 600)),
            seed=cfg.get("seed", 0),
        )

    def supports(self, language: str | None) -> bool:
        return bool(language) and language in self.voices

    def load(self, language: str) -> tuple[Any, Any]:
        if language in self._models:
            return self._models[language]
        if language not in self.voices:
            raise TtsUnavailable(f"no TTS voice configured for {language!r} (speech.tts.voices)")
        with _LOCK:
            if language in self._models:
                return self._models[language]
            try:
                from transformers import AutoTokenizer, VitsModel
            except ImportError as exc:
                raise TtsUnavailable("transformers and torch are required for TTS") from exc
            model_id = self.voices[language]
            started = time.perf_counter()
            self._device = resolve_device(self.requested_device)
            try:
                tokenizer = AutoTokenizer.from_pretrained(model_id)
                model = VitsModel.from_pretrained(model_id)
                model.to(self._device).eval()
            except Exception as exc:  # noqa: BLE001
                raise TtsUnavailable(f"could not load {model_id!r}: {exc}") from exc
            self._models[language] = (tokenizer, model)
            self.load_times_ms[language] = round((time.perf_counter() - started) * 1000, 1)
            logger.info("loaded TTS %s in %.0f ms", model_id, self.load_times_ms[language])
        return self._models[language]

    def describe(self) -> dict[str, Any]:
        return {
            "voices": self.voices,
            "loaded": sorted(self._models),
            "device": self._device,
            "load_times_ms": self.load_times_ms,
        }

    def _chunks(self, text: str) -> list[str]:
        text = text.strip()[: self.max_characters]
        if not self.chunk_by_sentence:
            return [text] if text else []
        return [part.strip() for part in _SENTENCE.split(text) if part.strip()]

    def synthesize(self, text: str, language: str) -> tuple[np.ndarray, TtsResult]:
        """Speak ``text``; returns (float32 waveform, timings)."""
        import torch

        tokenizer, model = self.load(language)
        sample_rate = int(getattr(model.config, "sampling_rate", 16000))
        if self.seed is not None:
            # VITS samples durations and noise: without a seed the same text gives
            # slightly different audio (and so different ASR input) on every call.
            torch.manual_seed(self.seed)
        started = time.perf_counter()
        first_chunk_ms = 0.0
        pieces: list[np.ndarray] = []
        for chunk in self._chunks(text):
            inputs = tokenizer(chunk, return_tensors="pt")
            if inputs["input_ids"].shape[-1] == 0:
                continue  # nothing the voice's alphabet can pronounce
            inputs = {k: v.to(self._device) for k, v in inputs.items()}
            with torch.no_grad():
                waveform = model(**inputs).waveform[0].float().cpu().numpy()
            pieces.append(waveform)
            if not first_chunk_ms:
                first_chunk_ms = round((time.perf_counter() - started) * 1000, 1)
            pieces.append(np.zeros(int(sample_rate * 0.15), dtype=np.float32))
        audio = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)
        latency = round((time.perf_counter() - started) * 1000, 1)
        return audio, TtsResult(
            language=language,
            model_id=self.voices[language],
            sample_rate=sample_rate,
            audio_seconds=round(audio.size / sample_rate, 3),
            latency_ms=latency,
            first_chunk_ms=first_chunk_ms or latency,
            chunks=len(pieces) // 2,
        )
