"""The speech pipeline: audio in, Phrase DNA + spoken answer out.

    audio -> Whisper n-best -> [validation] -> Phrase DNA sort -> answer -> TTS

Reuses the project's :class:`SPLMEngine` (its parser pipeline, scorer, lexicon and
configuration). The answer model is ``speech.generation.model_id`` - by default
Qwen2.5-0.5B-Instruct - loaded once and used by every mode:

* ``base``: the model alone (no logits processor);
* ``nplm``: the same weights with NPLM re-scoring at every decoding step;
* ``nplm_validated``: as ``nplm``, after Phrase-DNA validation of the n-best
  transcript, plus a rule-based clarifying question when a request is missing
  information (see :func:`splm.speech.dna.clarify`).

Decoding is greedy with identical settings in every mode, so for a given
transcript the base and NPLM answers differ only by the NPLM layer.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from splm.config import Config, get_config
from splm.speech import MODES
from splm.speech.asr import AsrResult, Hypothesis, WhisperASR
from splm.speech.audio import decode_audio, encode_wav
from splm.speech.dna import Clarification, DnaSort, clarify, sort_frame
from splm.speech.metrics import memory_snapshot
from splm.speech.tts import MultilingualTTS, TtsUnavailable
from splm.speech.validation import ValidationResult, validate

logger = logging.getLogger(__name__)


class SpeechTurn(BaseModel):
    """One spoken exchange in one mode, fully timed."""

    mode: str
    language: str | None = None
    transcript: str = ""
    asr: dict[str, Any] | None = None
    validation: ValidationResult | None = None
    dna: DnaSort | None = None
    phrase_frame: dict[str, Any] | None = None
    clarification: Clarification | None = None
    response_text: str = ""
    response_source: str = "generation"  # generation | clarification | none
    response_dna: DnaSort | None = None
    audio_wav_base64: str | None = None
    audio_seconds: float = 0.0
    timings_ms: dict[str, float] = Field(default_factory=dict)
    rtf: dict[str, float | None] = Field(default_factory=dict)
    tokens_generated: int = 0
    memory: dict[str, float | None] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SpeechPipeline:
    """Holds the ASR, TTS and answer engines; all components are injectable."""

    def __init__(self, config: Config | None = None, *, engine: Any | None = None,
                 asr: Any | None = None, tts: Any | None = None,
                 answer_engine: Any | None = None) -> None:
        self.config = config or get_config()
        self._engine = engine
        self._asr = asr
        self._tts = tts
        self._answer_engine = answer_engine
        self._lock = threading.Lock()
        self.warm = False

    # -- components -----------------------------------------------------------

    @property
    def engine(self) -> Any:
        if self._engine is None:
            from splm.model.engine import SPLMEngine

            self._engine = SPLMEngine(self.config)
        return self._engine

    @property
    def asr(self) -> Any:
        if self._asr is None:
            self._asr = WhisperASR.from_config(self.config)
        return self._asr

    @property
    def tts(self) -> Any:
        if self._tts is None:
            self._tts = MultilingualTTS.from_config(self.config)
        return self._tts

    @property
    def answer_engine(self) -> Any:
        """SPLMEngine sharing the parser and lexicon, with the answer model as its LLM."""
        if self._answer_engine is None:
            from splm.model.base_llm import BaseLanguageModel
            from splm.model.engine import SPLMEngine

            model_id = self.config.get("speech.generation.model_id")
            base = self.engine
            if not model_id or model_id == base.config.model.get("model_id"):
                self._answer_engine = base
            else:
                cfg = base.config.model
                llm = BaseLanguageModel(
                    model_id=str(model_id),
                    device=str(cfg.get("device", "auto")),
                    dtype=str(cfg.get("dtype", "auto")),
                    top_k_candidates=int(cfg.get("top_k_candidates", 100)),
                    max_context_tokens=int(cfg.get("max_context_tokens", 1024)),
                    cache_dir=cfg.get("cache_dir"),
                    local_files_only=bool(cfg.get("local_files_only", False)),
                    generation=cfg.get("generation"),
                )
                self._answer_engine = SPLMEngine(
                    base.config, pipeline=base.pipeline, llm=llm, lexicon=base.lexicon,
                    scorer=None, slot_predictor=base.slot_predictor,
                )
        return self._answer_engine

    def warmup(self, languages: list[str] | None = None) -> dict[str, float]:
        """Load every model before anything is timed."""
        timings: dict[str, float] = {}
        languages = languages or [l for l in self.config.supported_languages if self.tts.supports(l)]
        started = time.perf_counter()
        self.asr.load()
        timings["asr_load_ms"] = round((time.perf_counter() - started) * 1000, 1)
        started = time.perf_counter()
        for language in languages:
            try:
                self.tts.load(language)
                self.engine.pipeline.analyze("Warmup.", language=language)
            except Exception as exc:  # noqa: BLE001
                logger.warning("speech warmup for %s failed: %s", language, exc)
        timings["tts_parser_load_ms"] = round((time.perf_counter() - started) * 1000, 1)
        started = time.perf_counter()
        self.answer_engine.llm.load()
        self.answer_engine.generate("Hello", max_new_tokens=2, use_splm=False)
        _ = self.answer_engine.scorer
        timings["answer_model_load_ms"] = round((time.perf_counter() - started) * 1000, 1)
        self.warm = True
        return timings

    def describe(self) -> dict[str, Any]:
        gen = self.config.get("speech.generation", {}) or {}
        return {
            "modes": {mode: self.config.get(f"speech.modes.{mode}", mode) for mode in MODES},
            "asr": self.asr.describe(),
            "tts": self.tts.describe(),
            "answer_model": gen.get("model_id") or self.config.model.get("model_id"),
            "generation": {k: gen.get(k) for k in ("max_new_tokens", "use_chat_template", "reanalyse_every")},
            "languages": [l for l in self.config.supported_languages if self.tts.supports(l)],
            "warm": self.warm,
        }

    # -- steps ----------------------------------------------------------------

    def analyse(self, text: str, language: str | None) -> tuple[DnaSort, dict[str, Any] | None]:
        analysis = self.engine.pipeline.analyze(text, language=language)
        frame = analysis.frame
        return (
            sort_frame(frame, analysis.sentence, text=text, language=analysis.language),
            frame.model_dump(mode="json") if frame else None,
        )

    def build_prompt(self, transcript: str) -> str:
        gen = self.config.get("speech.generation", {}) or {}
        template = str(gen.get("prompt_template") or "{transcript}")
        user = template.format(transcript=transcript)
        tokenizer = self.answer_engine.llm.tokenizer
        if gen.get("use_chat_template", True) and getattr(tokenizer, "chat_template", None):
            messages = []
            if gen.get("system_prompt"):
                messages.append({"role": "system", "content": str(gen["system_prompt"]).strip()})
            messages.append({"role": "user", "content": user})
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        return user

    def generate(self, transcript: str, *, use_splm: bool, language: str | None) -> tuple[str, float, int]:
        gen = self.config.get("speech.generation", {}) or {}
        engine = self.answer_engine
        prompt = self.build_prompt(transcript)
        chat = prompt != transcript
        started = time.perf_counter()
        options: dict[str, Any] = {"max_new_tokens": int(gen.get("max_new_tokens", 40)), "do_sample": False}
        if use_splm:
            text = engine.generate(
                prompt, language=language, use_splm=True,
                analysis_prefix="" if chat else None,
                reanalyse_every=int(gen.get("reanalyse_every", 1)), **options,
            )
        else:
            text = engine.generate(prompt, use_splm=False, **options)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        try:
            tokens = engine.llm.token_count(text) if text else 0
        except Exception:  # noqa: BLE001
            tokens = 0
        return text.strip(), elapsed, tokens

    def recognise(self, audio: bytes, language: str | None) -> AsrResult:
        cfg = self.config.get("speech.asr", {}) or {}
        samples = decode_audio(audio, int(cfg.get("sample_rate", 16000)), cfg.get("max_audio_seconds"))
        return self.asr.transcribe(samples, language=language or None)

    # -- turns ----------------------------------------------------------------

    def run_audio(self, audio: bytes, mode: str = "nplm", language: str | None = None,
                  *, speak: bool = True) -> SpeechTurn:
        started = time.perf_counter()
        asr = self.recognise(audio, language)
        return self.run_mode(asr, mode, speak=speak, started=started)

    def run_text(self, text: str, mode: str = "nplm", language: str | None = None,
                 *, speak: bool = True) -> SpeechTurn:
        """The same pipeline from typed text (no ASR); for testing without a microphone."""
        if not language:
            language = self.engine.pipeline.detector.detect(text).language
        asr = AsrResult(hypotheses=[Hypothesis(text=text.strip(), score=0.0, rank=1)],
                        language=language, language_source="typed")
        return self.run_mode(asr, mode, speak=speak)

    def compare(self, audio: bytes | None = None, text: str | None = None,
                language: str | None = None, *, speak: bool = True,
                modes: tuple[str, ...] = MODES) -> dict[str, Any]:
        """Every mode on one recognition result: identical input, hardware, settings."""
        if audio is not None:
            asr = self.recognise(audio, language)
        else:
            if not language:
                language = self.engine.pipeline.detector.detect(text or "").language
            asr = AsrResult(hypotheses=[Hypothesis(text=(text or "").strip(), score=0.0, rank=1)],
                            language=language, language_source="typed")
        turns = {mode: self.run_mode(asr, mode, speak=speak) for mode in modes}
        return {
            "turns": {mode: turn.model_dump(mode="json") for mode, turn in turns.items()},
            "shared_asr": True,
            "note": (
                "One Whisper beam search is shared by all modes (each mode is charged its "
                "latency). Generation is greedy with identical settings, so base vs NPLM "
                "differ only by the NPLM layer. A single utterance is an example, not evidence."
            ),
        }

    def run_mode(self, asr: AsrResult, mode: str, *, speak: bool = True,
                 started: float | None = None) -> SpeechTurn:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; choose one of {MODES}")
        with self._lock:  # one turn at a time: models are shared and not re-entrant
            return self._run(asr, mode, speak=speak, started=started)

    def _run(self, asr: AsrResult, mode: str, *, speak: bool, started: float | None) -> SpeechTurn:
        clock = time.perf_counter()
        timings: dict[str, float] = {"asr": asr.latency_ms}
        language = asr.language
        gen = self.config.get("speech.generation", {}) or {}
        turn = SpeechTurn(
            mode=mode,
            language=language,
            asr={
                "hypotheses": [h.model_dump() for h in asr.hypotheses],
                "language": asr.language,
                "language_source": asr.language_source,
                "audio_seconds": asr.audio_seconds,
                "latency_ms": asr.latency_ms,
                "model_id": getattr(self.asr, "model_id", None) if asr.language_source != "typed" else None,
            },
            settings={
                "answer_model": gen.get("model_id") or self.config.model.get("model_id"),
                "max_new_tokens": int(gen.get("max_new_tokens", 40)),
                "decoding": "greedy",
                "nplm": mode != "base",
            },
        )
        if not asr.hypotheses:
            turn.warnings.append("no speech recognised")
            turn.response_source = "none"
            return turn
        if language and language not in self.config.supported_languages:
            turn.warnings.append(f"language {language!r} has no language pack; Phrase DNA will be weak")

        # 1. transcript (validated in mode C)
        step = time.perf_counter()
        sort: DnaSort | None = None
        if mode == "nplm_validated" and len(asr.hypotheses) > 1:
            vcfg = self.config.get("speech.validation", {}) or {}
            frames: dict[str, Any] = {}

            def analyse(text: str) -> DnaSort:
                result, frames[text] = self.analyse(text, language)
                return result

            validation, sorts = validate(
                asr.hypotheses, analyse, language=language,
                weights=vcfg.get("weights"), max_acoustic_gap=float(vcfg.get("max_acoustic_gap", 1.5)),
            )
            validation.latency_ms = round((time.perf_counter() - step) * 1000, 1)
            turn.validation = validation
            turn.transcript = validation.chosen
            sort, turn.phrase_frame = sorts.get(validation.chosen), frames.get(validation.chosen)
            turn.warnings.extend(validation.warnings)
            timings["validation"] = validation.latency_ms
        else:
            turn.transcript = asr.hypotheses[0].text
            if mode == "nplm_validated":
                timings["validation"] = 0.0
                turn.warnings.append("only one ASR hypothesis: nothing to validate")

        # 2. Phrase DNA of what the user said
        step = time.perf_counter()
        if sort is None:
            sort, turn.phrase_frame = self.analyse(turn.transcript, language)
        turn.dna = sort
        timings["analysis"] = round((time.perf_counter() - step) * 1000, 1)
        language = language or sort.language

        # 3. answer
        if mode == "nplm_validated" and (self.config.get("speech.dialogue.ask_when_missing", True)):
            turn.clarification = clarify(sort)
        if turn.clarification is not None:
            turn.response_text = turn.clarification.question
            turn.response_source = "clarification"
            timings["generation"] = 0.0
        else:
            text, elapsed, tokens = self.generate(turn.transcript, use_splm=(mode != "base"), language=language)
            turn.response_text, turn.tokens_generated = text, tokens
            timings["generation"] = elapsed
            if not text:
                turn.response_source = "none"
                turn.warnings.append("the model produced no text")

        # 4. speech
        before_tts = (time.perf_counter() - clock) * 1000 + asr.latency_ms
        if speak and turn.response_text:
            if self.tts.supports(language):
                try:
                    audio, info = self.tts.synthesize(turn.response_text, language)
                    turn.audio_wav_base64 = base64.b64encode(encode_wav(audio, info.sample_rate)).decode("ascii")
                    turn.audio_seconds = info.audio_seconds
                    timings["tts"] = info.latency_ms
                    timings["tts_first_chunk"] = info.first_chunk_ms
                    turn.settings["tts_model"] = info.model_id
                    timings["time_to_first_audio"] = round(before_tts + info.first_chunk_ms, 1)
                except TtsUnavailable as exc:
                    turn.warnings.append(str(exc))
            else:
                turn.warnings.append(f"no TTS voice for {language!r}; answer shown as text only")

        end_to_end = (time.perf_counter() - clock) * 1000 + asr.latency_ms
        if started is not None:  # include audio decoding when the caller timed it
            end_to_end = max(end_to_end, (time.perf_counter() - started) * 1000)
        timings["end_to_end"] = round(end_to_end, 1)
        turn.timings_ms = timings
        audio_s = asr.audio_seconds or 0.0
        turn.rtf = {
            "asr": asr.rtf,
            "end_to_end": round(end_to_end / 1000 / audio_s, 4) if audio_s > 0 else None,
            "tts": round(timings["tts"] / 1000 / turn.audio_seconds, 4)
            if timings.get("tts") and turn.audio_seconds else None,
        }

        # Not timed: the answer's own DNA, for display.
        if turn.response_text:
            try:
                turn.response_dna, _ = self.analyse(turn.response_text, language)
            except Exception as exc:  # noqa: BLE001
                logger.debug("response analysis failed: %s", exc)
        turn.memory = memory_snapshot()
        return turn
