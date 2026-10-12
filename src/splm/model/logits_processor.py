"""Custom logits processor (spec section 26).

Lets SPLM take part in ordinary Hugging Face decoding:

    Transformer logits -> top-K candidates -> feature extraction -> SPLM scoring
                       -> modified candidate logits -> return

Only the top-K are re-scored, which bounds the per-step cost. Everything outside K
keeps its original logit; since those logits are all lower than the K-th, the
selected token always comes from the re-scored set.

The processor re-analyses the growing text as generation proceeds, so the Phrase
Frame and the expected slot update as the sentence takes shape - which is what makes
the live view in the UI real rather than decorative.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:  # transformers is an optional dependency of the parsing-only install
    from transformers import LogitsProcessor as _LogitsProcessor
except Exception:  # pragma: no cover

    class _LogitsProcessor:  # type: ignore[no-redef]
        """Stand-in so this module imports without transformers installed."""


class PhraseLanguageLogitsProcessor(_LogitsProcessor):
    """Applies SPLM re-scoring at every decoding step."""

    def __init__(
        self,
        *,
        engine: Any,
        prompt: str,
        language: str | None = None,
        top_k: int | None = None,
        reanalyse_every: int = 1,
        record_steps: bool = False,
    ) -> None:
        self.engine = engine
        self.prompt = prompt
        self.language = language
        self.top_k = top_k
        # Re-parsing on every token is the most faithful option but also the most
        # expensive; raising this trades freshness for speed.
        self.reanalyse_every = max(1, int(reanalyse_every))
        self.record_steps = record_steps

        self.steps: list[dict[str, Any]] = []
        self._calls = 0
        self._cached_context: Any | None = None
        self._cached_text: str | None = None

    # -- decoding hook -----------------------------------------------------

    def __call__(self, input_ids: Any, scores: Any) -> Any:
        import torch

        self._calls += 1
        try:
            text = self._current_text(input_ids)
            context = self._context_for(text)
            if context is None:
                return scores

            k = int(self.top_k or self.engine.llm.top_k_candidates)
            # scores is [batch, vocab]; SPLM runs one sequence at a time.
            row = scores[0]
            k = min(k, row.shape[-1])
            top = torch.topk(row, k=k)

            candidates = self._candidates_from(top, row)
            scored = self.engine.scorer.score_candidates(candidates, context)

            adjusted = row.clone()
            for candidate, score in zip(candidates, scored):
                adjusted[candidate.token_id] = score.splm_logit

            if self.record_steps:
                self._record(text, context, scored)

            scores = scores.clone()
            scores[0] = adjusted
            return scores

        except Exception as exc:
            # A failure here must not abort generation: fall back to the base model
            # and say so, rather than producing a half-scored distribution.
            logger.warning("SPLM re-scoring failed at step %d: %s", self._calls, exc)
            return scores

    # -- internals ---------------------------------------------------------

    def _current_text(self, input_ids: Any) -> str:
        """Decode the sequence so far, so analysis sees the real growing sentence."""
        try:
            return self.engine.llm.tokenizer.decode(
                input_ids[0], skip_special_tokens=True
            )
        except Exception:
            return self.prompt

    def _context_for(self, text: str) -> Any | None:
        """Build (or reuse) the scoring context for the current text."""
        from splm.model.candidate_features import ScoringContext
        from splm.phrase.slot_predictor import SlotContext

        reuse = (
            self._cached_context is not None
            and self._calls % self.reanalyse_every != 1
        )
        if reuse:
            return self._cached_context

        analysis = self.engine.pipeline.analyze(text, language=self.language)
        slots = self.engine.slot_predictor.predict(
            SlotContext(
                text=text,
                language=analysis.language,
                frame=analysis.frame,
                sentence=analysis.sentence,
                style=analysis.style,
            )
        )
        context = ScoringContext(
            text=text,
            language=analysis.language,
            frame=analysis.frame,
            slots=slots,
            style=analysis.style,
            context_graph=getattr(self.engine.pipeline, "context_graph", None),
            tracker=self.engine._tracker(analysis.language, text),
            trailing_word=text.rstrip().split()[-1].lower() if text.strip() else None,
        )
        self._cached_context = context
        self._cached_text = text
        return context

    def _candidates_from(self, top: Any, row: Any) -> list[Any]:
        import torch

        probabilities = torch.softmax(row.float(), dim=-1)
        return [
            self.engine.llm.make_candidate(
                token_id=int(token_id),
                logit=float(row[token_id]),
                probability=float(probabilities[token_id]),
                rank=rank + 1,
            )
            for rank, token_id in enumerate(top.indices.tolist())
        ]

    def _record(self, text: str, context: Any, scored: list[Any]) -> None:
        """Capture per-step state for the UI's step-by-step generation view."""
        best = min(scored, key=lambda s: s.splm_rank) if scored else None
        self.steps.append(
            {
                "step": self._calls,
                "text": text,
                "expected_slot": context.slots.top_slot if context.slots else None,
                "slot_confidence": context.slots.confidence if context.slots else None,
                "filled_slots": (
                    [s for s in context.frame.filled_slots()] if context.frame else []
                ),
                "dangling_marker": (
                    context.frame.dangling_marker if context.frame else None
                ),
                "chosen": best.word if best else None,
                "delta_logit": best.delta_logit if best else None,
            }
        )
