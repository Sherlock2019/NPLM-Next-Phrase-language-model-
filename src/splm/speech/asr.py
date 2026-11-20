"""Whisper speech recognition with an n-best list.

One beam search per utterance. ``n_best`` hypotheses are read from that same beam,
so every mode pays the same ASR cost; only ``nplm_validated`` looks past the first.
The checkpoint comes from ``config/speech.yaml`` (``speech.asr.model_id``).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from splm.device import resolve_device, resolve_dtype

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()


class AsrUnavailable(RuntimeError):
    """The configured ASR checkpoint could not be loaded."""


class Hypothesis(BaseModel):
    text: str
    #: Whisper's length-normalised sequence log-probability (higher is better).
    score: float
    rank: int


class AsrResult(BaseModel):
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    language: str | None = None
    language_source: str = "requested"
    audio_seconds: float = 0.0
    latency_ms: float = 0.0

    @property
    def top(self) -> Hypothesis | None:
        return self.hypotheses[0] if self.hypotheses else None

    @property
    def rtf(self) -> float | None:
        """Real-time factor of recognition: processing time / audio duration."""
        if self.audio_seconds <= 0:
            return None
        return round(self.latency_ms / 1000 / self.audio_seconds, 4)


class WhisperASR:
    """Lazily loaded Whisper (any Hugging Face Whisper checkpoint)."""

    def __init__(self, model_id: str, *, device: str = "auto", dtype: str = "auto",
                 num_beams: int = 5, n_best: int = 5, max_new_tokens: int = 128,
                 sample_rate: int = 16000) -> None:
        self.model_id = model_id
        self.requested_device = device
        self.requested_dtype = dtype
        self.num_beams = max(1, int(num_beams))
        self.n_best = max(1, min(int(n_best), self.num_beams))
        self.max_new_tokens = int(max_new_tokens)
        self.sample_rate = int(sample_rate)
        #: Reuse decoder key/values across beam steps (identical results, faster).
        self.kv_cache = True
        self._model: Any | None = None
        self._processor: Any | None = None
        self._device = "cpu"
        self._dtype: Any = None
        self.load_time_ms: float | None = None

    @classmethod
    def from_config(cls, config: Any) -> "WhisperASR":
        cfg = config.get("speech.asr", {}) or {}
        if not cfg.get("model_id"):
            raise AsrUnavailable("no speech.asr.model_id in config/speech.yaml")
        return cls(
            model_id=str(cfg["model_id"]),
            device=str(cfg.get("device", "auto")),
            dtype=str(cfg.get("dtype", "auto")),
            num_beams=int(cfg.get("num_beams", 5)),
            n_best=int(cfg.get("n_best", 5)),
            max_new_tokens=int(cfg.get("max_new_tokens", 128)),
            sample_rate=int(cfg.get("sample_rate", 16000)),
        )

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> "WhisperASR":
        if self._model is not None:
            return self
        with _LOCK:
            if self._model is not None:
                return self
            try:
                from transformers import WhisperForConditionalGeneration, WhisperProcessor
            except ImportError as exc:
                raise AsrUnavailable("transformers and torch are required for ASR") from exc
            started = time.perf_counter()
            self._device = resolve_device(self.requested_device)
            self._dtype = resolve_dtype(self.requested_dtype, self._device)
            try:
                processor = WhisperProcessor.from_pretrained(self.model_id)
                model = WhisperForConditionalGeneration.from_pretrained(self.model_id, dtype=self._dtype)
                model.to(self._device).eval()
            except Exception as exc:  # noqa: BLE001
                raise AsrUnavailable(f"could not load {self.model_id!r}: {exc}") from exc
            self._processor, self._model = processor, model
            self.load_time_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info("loaded ASR %s on %s in %.0f ms", self.model_id, self._device, self.load_time_ms)
        return self

    def describe(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "loaded": self.is_loaded,
            "device": self._device if self.is_loaded else self.requested_device,
            "num_beams": self.num_beams,
            "n_best": self.n_best,
            "load_time_ms": self.load_time_ms,
        }

    def _detect_language(self, features: Any) -> str | None:
        """Whisper's own language identification (first decoder step)."""
        import torch

        model, tokenizer = self._model, self._processor.tokenizer
        try:
            with torch.no_grad():
                ids = model.detect_language(features)
            token = tokenizer.convert_ids_to_tokens(int(ids[0]))
            return token.strip("<|>") if token else None
        except Exception as exc:  # noqa: BLE001 - older/newer API shapes
            logger.debug("detect_language failed: %s", exc)
            return None

    def _prompt_ids(self, language: str | None) -> list[int]:
        """<|startoftranscript|><|lang|><|transcribe|><|notimestamps|>."""
        tokenizer = self._processor.tokenizer
        ids = [tokenizer.convert_tokens_to_ids("<|startoftranscript|>")]
        if language:
            lang_id = tokenizer.convert_tokens_to_ids(f"<|{language}|>")
            if lang_id is not None and lang_id != tokenizer.unk_token_id:
                ids.append(lang_id)
        ids.append(tokenizer.convert_tokens_to_ids("<|transcribe|>"))
        ids.append(tokenizer.convert_tokens_to_ids("<|notimestamps|>"))
        return ids

    def _beam_search(self, features: Any, language: str | None) -> list[tuple[list[int], float]]:
        """Plain beam search over the Whisper decoder, returning distinct finished beams.

        Written here because transformers' ``num_return_sequences`` for Whisper returned
        duplicate copies of the top beam (and ran ~6x slower) in the version tested.
        Scores are length-normalised log-probabilities, as in Hugging Face's beam search.
        """
        import torch

        model, tokenizer = self._model, self._processor.tokenizer
        config = model.generation_config
        eos = int(config.eos_token_id if isinstance(config.eos_token_id, int) else config.eos_token_id[0])
        suppress = list(getattr(config, "suppress_tokens", None) or [])
        begin_suppress = list(getattr(config, "begin_suppress_tokens", None) or [])
        no_ts = tokenizer.convert_tokens_to_ids("<|notimestamps|>")
        prompt = self._prompt_ids(language)

        with torch.no_grad():
            encoded = model.model.encoder(features).last_hidden_state
        beams: list[tuple[list[int], float]] = [([], 0.0)]
        finished: list[tuple[list[int], float]] = []
        width = self.num_beams
        past: Any = None
        use_cache = self.kv_cache
        for step in range(self.max_new_tokens):
            if not beams:
                break
            with torch.no_grad():
                if use_cache and past is not None:
                    ids = torch.tensor([[tokens[-1]] for tokens, _ in beams], device=self._device)
                else:
                    ids = torch.tensor([prompt + tokens for tokens, _ in beams], device=self._device)
                out = model(
                    encoder_outputs=(encoded.expand(len(beams), -1, -1),),
                    decoder_input_ids=ids,
                    past_key_values=past if use_cache else None,
                    use_cache=use_cache,
                )
                logits = out.logits[:, -1, :].float()
                past = out.past_key_values if use_cache else None
            if suppress:
                logits[:, suppress] = -float("inf")
            if step == 0 and begin_suppress:
                logits[:, begin_suppress] = -float("inf")
            logits[:, no_ts:] = -float("inf")      # timestamps and anything after them
            if step == 0:
                logits[:, eos] = -float("inf")       # no empty transcripts
            log_probs = torch.log_softmax(logits, dim=-1)

            candidates: list[tuple[list[int], float, int]] = []
            top = torch.topk(log_probs, k=width, dim=-1)
            for row, (tokens, total) in enumerate(beams):
                for value, token in zip(top.values[row].tolist(), top.indices[row].tolist()):
                    candidates.append((tokens + [int(token)], total + float(value), row))
            candidates.sort(key=lambda item: item[1], reverse=True)

            beams, parents = [], []
            for tokens, total, row in candidates:
                if tokens[-1] == eos:
                    finished.append((tokens[:-1], total / max(1, len(tokens))))
                elif len(beams) < width:
                    beams.append((tokens, total))
                    parents.append(row)
            if use_cache and past is not None and beams:
                try:
                    past.reorder_cache(torch.tensor(parents, device=self._device))
                except Exception as exc:  # noqa: BLE001 - cache API differs: recompute instead
                    logger.debug("KV cache reorder unavailable (%s); decoding without cache", exc)
                    use_cache, past = False, None
            if len(finished) >= width and beams and \
                    max(f[1] for f in finished) > beams[0][1] / max(1, len(beams[0][0])):
                break
        finished.extend((tokens, total / max(1, len(tokens))) for tokens, total in beams)
        finished.sort(key=lambda item: item[1], reverse=True)
        return finished

    def transcribe(self, samples: np.ndarray, language: str | None = None) -> AsrResult:
        """Recognise 16 kHz mono float32 ``samples``; ``language`` None = detect."""
        import torch

        self.load()
        started = time.perf_counter()
        inputs = self._processor(samples, sampling_rate=self.sample_rate, return_tensors="pt")
        features = inputs.input_features.to(self._device, dtype=self._dtype or torch.float32)

        source = "requested"
        if not language:
            language = self._detect_language(features)
            source = "whisper"

        beams = self._beam_search(features, language)
        hypotheses: list[Hypothesis] = []
        seen: set[str] = set()
        for tokens, score in beams:
            cleaned = self._processor.tokenizer.decode(
                tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False
            ).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            hypotheses.append(Hypothesis(text=cleaned, score=round(score, 4), rank=len(hypotheses) + 1))
            if len(hypotheses) >= self.n_best:
                break

        return AsrResult(
            hypotheses=hypotheses,
            language=language,
            language_source=source,
            audio_seconds=round(samples.size / self.sample_rate, 3),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
