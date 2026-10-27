"""The base Transformer wrapper (spec section 6).

SPLM must work with *any* Hugging Face causal LM, so nothing outside this module
knows which model is loaded, and no model id is ever hard-coded - it comes from
``config/model.yaml``.

The wrapper deliberately exposes little: logits for a prompt, the top-k candidates,
and generation. That small surface is what keeps the structural layers portable.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

from splm.device import resolve_device, resolve_dtype

logger = logging.getLogger(__name__)

#: One model load at a time in this process: transformers' loader is not thread-safe.
_LOAD_LOCK = threading.Lock()


@dataclass(frozen=True)
class Candidate:
    """One next-token candidate as the base model sees it.

    ``token`` is the tokenizer's internal symbol (``Ġthe``, ``Ċ``); ``surface`` is
    what that symbol actually spells, obtained from the tokenizer rather than by
    rewriting marker characters by hand. The distinction matters: byte-level BPE
    spells a newline ``Ċ``, whose first character is an uppercase letter, so naive
    string handling mistakes control characters for proper nouns.
    """

    token_id: int
    token: str
    logit: float
    probability: float
    rank: int
    surface: str = ""

    @property
    def text(self) -> str:
        return self.surface if self.surface else self.token

    @property
    def stripped(self) -> str:
        """The candidate's word, or empty for whitespace, punctuation and controls."""
        return self.text.strip()

    @property
    def is_word_start(self) -> bool:
        """Whether this token begins a new word rather than continuing one.

        Matters because SPLM reasons about words and roles while the model predicts
        sub-word pieces (spec section 25).
        """
        if self.surface:
            return self.surface[:1].isspace()
        return self.token.startswith((" ", "Ġ", "▁"))

    @property
    def is_word_like(self) -> bool:
        """Whether the candidate contains any letters at all."""
        return any(char.isalpha() for char in self.stripped)


class ModelUnavailable(RuntimeError):
    """Raised when the configured base model cannot be loaded."""


class BaseLanguageModel:
    """A lazily loaded Hugging Face causal LM."""

    def __init__(
        self,
        model_id: str,
        *,
        device: str = "auto",
        dtype: str = "auto",
        top_k_candidates: int = 100,
        max_context_tokens: int = 1024,
        cache_dir: str | None = None,
        local_files_only: bool = False,
        generation: dict[str, Any] | None = None,
    ) -> None:
        self.model_id = model_id
        self.requested_device = device
        self.requested_dtype = dtype
        self.top_k_candidates = int(top_k_candidates)
        self.max_context_tokens = int(max_context_tokens)
        self.cache_dir = cache_dir
        self.local_files_only = bool(local_files_only)
        self.generation_defaults = dict(generation or {})

        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._device: str | None = None
        self._dtype: Any | None = None
        self.load_time_ms: float | None = None

    # -- construction ------------------------------------------------------

    @classmethod
    def from_config(cls, config: Any | None = None) -> "BaseLanguageModel":
        from splm.config import get_config

        config = config or get_config()
        model_cfg = config.model
        if not model_cfg.get("model_id"):
            raise ModelUnavailable("no model.model_id configured in config/model.yaml")
        return cls(
            model_id=str(model_cfg["model_id"]),
            device=str(model_cfg.get("device", "auto")),
            dtype=str(model_cfg.get("dtype", "auto")),
            top_k_candidates=int(model_cfg.get("top_k_candidates", 100)),
            max_context_tokens=int(model_cfg.get("max_context_tokens", 1024)),
            cache_dir=model_cfg.get("cache_dir"),
            local_files_only=bool(model_cfg.get("local_files_only", False)),
            generation=model_cfg.get("generation"),
        )

    # -- loading -----------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> "BaseLanguageModel":
        """Load the tokenizer and weights. Idempotent and thread-safe.

        The model is kept only once it is fully loaded, tied and on its device: a load
        that fails half-way (e.g. concurrent loads, which transformers does not support)
        must never leave a half-initialised model behind to serve predictions.
        """
        if self._model is not None:
            return self
        with _LOAD_LOCK:
            if self._model is not None:
                return self
            return self._load()

    def _load(self) -> "BaseLanguageModel":
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ModelUnavailable(
                "transformers and torch are required; install with `pip install -e '.[llm]'`"
            ) from exc

        started = time.perf_counter()
        self._device = resolve_device(self.requested_device)
        self._dtype = resolve_dtype(self.requested_dtype, self._device)

        kwargs: dict[str, Any] = {"local_files_only": self.local_files_only}
        if self.cache_dir:
            kwargs["cache_dir"] = self.cache_dir

        logger.info(
            "loading base model %s on %s (%s)", self.model_id, self._device, self._dtype
        )
        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model_id, **kwargs)
            model = AutoModelForCausalLM.from_pretrained(self.model_id, dtype=self._dtype, **kwargs)
            model.to(self._device)
            model.eval()
        except Exception as exc:
            raise ModelUnavailable(f"could not load {self.model_id!r}: {exc}") from exc
        if getattr(model.config, "tie_word_embeddings", False):
            output = model.get_output_embeddings()
            if output is not None and output.weight.data_ptr() != model.get_input_embeddings().weight.data_ptr():
                raise ModelUnavailable(f"{self.model_id!r} loaded with untied output embeddings; refusing a corrupt model")

        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        self._tokenizer, self._model = tokenizer, model

        self.load_time_ms = (time.perf_counter() - started) * 1000
        logger.info("loaded %s in %.0f ms", self.model_id, self.load_time_ms)
        return self

    # -- accessors ---------------------------------------------------------

    @property
    def tokenizer(self) -> Any:
        self.load()
        return self._tokenizer

    @property
    def model(self) -> Any:
        self.load()
        return self._model

    @property
    def device(self) -> str:
        self.load()
        return self._device or "cpu"

    @property
    def vocab_size(self) -> int:
        """Size of the tokenizer's vocabulary.

        Used as the honest denominator for search-space figures: it is how many
        distinct tokens the base model chooses between at each step.
        """
        self.load()
        return int(getattr(self._model.config, "vocab_size", len(self._tokenizer)))

    @property
    def parameter_count(self) -> int:
        self.load()
        return sum(p.numel() for p in self._model.parameters())

    def describe(self) -> dict[str, Any]:
        """Model metadata for the UI's system page and benchmark provenance."""
        from splm.device import device_report

        info: dict[str, Any] = {
            "model_id": self.model_id,
            "loaded": self.is_loaded,
            "top_k_candidates": self.top_k_candidates,
            "requested_device": self.requested_device,
            "requested_dtype": self.requested_dtype,
        }
        if self.is_loaded:
            info.update(
                {
                    "device": self.device,
                    "dtype": str(self._dtype),
                    "vocab_size": self.vocab_size,
                    "parameters": self.parameter_count,
                    "tokenizer": type(self._tokenizer).__name__,
                    "load_time_ms": round(self.load_time_ms or 0.0, 1),
                }
            )
        info["hardware"] = device_report()
        return info

    # -- inference ---------------------------------------------------------

    def encode(self, text: str) -> Any:
        """Tokenise, truncating from the left so the most recent context survives."""
        tokenizer = self.tokenizer
        encoded = tokenizer(text, return_tensors="pt")
        input_ids = encoded["input_ids"]
        if input_ids.shape[-1] > self.max_context_tokens:
            input_ids = input_ids[:, -self.max_context_tokens :]
        return input_ids.to(self.device)

    def token_count(self, text: str) -> int:
        """Number of tokens in ``text`` - needed for context-efficiency metrics."""
        return int(self.tokenizer(text, return_tensors="pt")["input_ids"].shape[-1])

    def get_logits(self, text: str) -> Any:
        """Next-token logits for ``text`` as a 1-D tensor over the vocabulary."""
        import torch

        input_ids = self.encode(text)
        with torch.no_grad():
            outputs = self.model(input_ids)
        return outputs.logits[0, -1, :]

    def get_top_candidates(self, text: str, k: int | None = None) -> list[Candidate]:
        """The ``k`` most likely next tokens, with logits and probabilities.

        Probabilities come from a softmax over the *whole* vocabulary, not over the
        top-k, so they remain comparable with SPLM's re-scored distribution.
        """
        import torch

        k = int(k or self.top_k_candidates)
        logits = self.get_logits(text)
        probabilities = torch.softmax(logits.float(), dim=-1)
        top = torch.topk(logits, k=min(k, logits.shape[-1]))

        return [
            self.make_candidate(
                token_id=int(token_id),
                logit=float(logits[token_id]),
                probability=float(probabilities[token_id]),
                rank=rank + 1,
            )
            for rank, token_id in enumerate(top.indices.tolist())
        ]

    def make_candidate(
        self, *, token_id: int, logit: float, probability: float, rank: int
    ) -> Candidate:
        """Build a :class:`Candidate`, decoding its surface text via the tokenizer."""
        tokenizer = self.tokenizer
        token = tokenizer.convert_ids_to_tokens(token_id)
        return Candidate(
            token_id=token_id,
            token=token,
            logit=logit,
            probability=probability,
            rank=rank,
            surface=self.token_surface(token),
        )

    def token_surface(self, token: str) -> str:
        """The text a tokenizer symbol spells, boundary whitespace preserved."""
        try:
            return self.tokenizer.convert_tokens_to_string([token])
        except Exception:
            # Not every tokenizer implements it; fall back to marker substitution.
            return token.replace("Ġ", " ").replace("▁", " ")

    def decode(self, token_ids: Iterable[int]) -> str:
        return self.tokenizer.decode(list(token_ids), skip_special_tokens=True)

    def generate(
        self, text: str, *, logits_processor: Any | None = None, **kwargs: Any
    ) -> str:
        """Continue ``text``.

        ``logits_processor`` is how SPLM injects itself into decoding without the
        model knowing anything about SPLM (spec section 26).
        """
        import torch

        options = {**self.generation_defaults, **kwargs}
        options.setdefault("pad_token_id", self.tokenizer.pad_token_id)

        if logits_processor is not None:
            from transformers import LogitsProcessorList

            options["logits_processor"] = (
                logits_processor
                if isinstance(logits_processor, LogitsProcessorList)
                else LogitsProcessorList([logits_processor])
            )

        input_ids = self.encode(text)
        with torch.no_grad():
            output = self.model.generate(input_ids, **options)

        # Return only the continuation.
        generated = output[0, input_ids.shape[-1] :]
        return self.tokenizer.decode(generated, skip_special_tokens=True)

    def sequence_log_probability(self, text: str) -> tuple[float, int]:
        """Total log probability of ``text`` and its token count.

        The building block for perplexity (spec section 38).
        """
        import torch

        input_ids = self.encode(text)
        if input_ids.shape[-1] < 2:
            return 0.0, 0

        with torch.no_grad():
            logits = self.model(input_ids).logits[0]

        log_probabilities = torch.log_softmax(logits[:-1].float(), dim=-1)
        targets = input_ids[0, 1:]
        gathered = log_probabilities.gather(1, targets.unsqueeze(-1)).squeeze(-1)
        return float(gathered.sum()), int(targets.shape[0])
