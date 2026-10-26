"""Meaning Language Model (MLM).

An explicit linguistic and semantic layer wrapped around a pretrained causal
Transformer. SPLM converts text into a language-independent
:class:`~splm.phrase.schema.UniversalPhraseFrame`, predicts which semantic slot
should come next, and re-ranks the Transformer's candidate tokens accordingly.

The project exists to *test* whether that helps, not to assume it does
(spec section 51): every component is ablatable and every claim benchmarkable.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
