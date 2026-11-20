"""Speech AI lab: Whisper ASR -> NPLM generation -> multilingual TTS.

    audio -> Whisper (n-best) -> [semantic validation] -> Phrase DNA sort
          -> SPLMEngine.generate (base | NPLM) -> TTS -> audio

Three modes share one engine, one configuration and one set of decoding settings:

``base``            Whisper top-1 transcript, base Transformer generation.
``nplm``            Whisper top-1 transcript, NPLM-rescored generation.
``nplm_validated``  Whisper n-best re-ranked by Phrase DNA plausibility and
                    cross-hypothesis agreement on entities and numbers, then NPLM.

Everything heavy (torch, transformers, ffmpeg) is imported lazily so the pure
parts - metrics, DNA sorting, validation - are testable without any model.
"""

from splm.speech.dna import DNA_CATEGORIES, DnaSort, sort_frame
from splm.speech.metrics import cer, wer

MODES: tuple[str, ...] = ("base", "nplm", "nplm_validated")

__all__ = ["DNA_CATEGORIES", "DnaSort", "MODES", "cer", "sort_frame", "wer"]
