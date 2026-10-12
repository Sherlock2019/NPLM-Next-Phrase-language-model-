"""Stanza backend for :class:`splm.linguistic.parser.LinguisticParser`.

This is the only module in SPLM that imports Stanza. Everything downstream sees
:class:`ParsedSentence`, so replacing Stanza means adding a sibling of this file
and changing ``parser.backend`` in ``config/app.yaml``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from splm.linguistic.parser import (
    ParsedDocument,
    ParsedSentence,
    ParserUnavailable,
    Token,
)

logger = logging.getLogger(__name__)

DEFAULT_PROCESSORS = "tokenize,pos,lemma,depparse"


def _parse_feats(raw: str | None) -> dict[str, str]:
    """``Number=Sing|Person=3`` -> ``{"Number": "Sing", "Person": "3"}``."""
    if not raw or raw == "_":
        return {}
    features: dict[str, str] = {}
    for chunk in raw.split("|"):
        key, _, value = chunk.partition("=")
        if key and value:
            features[key] = value
    return features


class StanzaParser:
    """Universal Dependencies parsing via Stanza, one pipeline per language."""

    name = "stanza"

    def __init__(
        self,
        *,
        model_dir: Path | str,
        processors: dict[str, str] | None = None,
        use_gpu: bool | str = "auto",
        entity_normalizer: Any | None = None,
        tokenize_no_ssplit: bool = False,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.processors = processors or {}
        self.use_gpu = use_gpu
        self.tokenize_no_ssplit = tokenize_no_ssplit
        # A UniversalPack; used to normalise NER labels. Optional so the parser can
        # be constructed in isolation.
        self._entity_normalizer = entity_normalizer
        self._pipelines: dict[str, Any] = {}

    # -- construction ------------------------------------------------------

    @classmethod
    def from_config(cls, config: Any | None = None, **kwargs: Any) -> "StanzaParser":
        from splm.config import get_config
        from splm.language.packs import get_registry

        config = config or get_config()
        use_gpu = config.get("app.parser.use_gpu", "auto")
        return cls(
            model_dir=config.stanza_dir,
            processors=config.get("app.parser.processors", {}) or {},
            use_gpu=use_gpu,
            entity_normalizer=get_registry().universal(),
            **kwargs,
        )

    def _resolve_gpu(self) -> bool:
        from splm.device import resolve_use_gpu

        return resolve_use_gpu(self.use_gpu)

    def _model_present(self, language: str) -> bool:
        """Whether Stanza models for ``language`` exist in the configured directory."""
        return (self.model_dir / language).is_dir()

    def supports(self, language: str) -> bool:
        return self._model_present(language)

    def available_languages(self) -> list[str]:
        if not self.model_dir.is_dir():
            return []
        return sorted(
            child.name
            for child in self.model_dir.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )

    def _pipeline(self, language: str) -> Any:
        if language in self._pipelines:
            return self._pipelines[language]

        if not self._model_present(language):
            raise ParserUnavailable(
                f"No Stanza model for {language!r} in {self.model_dir}. "
                f"Run:  python scripts/download_resources.py --languages {language}"
            )

        try:
            import stanza
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ParserUnavailable(
                "stanza is not installed; install it with `pip install -e '.[parse]'`"
            ) from exc

        processors = self.processors.get(language, DEFAULT_PROCESSORS)
        logger.info(
            "loading Stanza pipeline lang=%s processors=%s gpu=%s",
            language,
            processors,
            self._resolve_gpu(),
        )

        kwargs: dict[str, Any] = {
            "lang": language,
            "processors": processors,
            "dir": str(self.model_dir),
            "use_gpu": self._resolve_gpu(),
            # Never fetch models mid-run - spec section 33.
            "download_method": None,
            "logging_level": "WARN",
        }
        if self.tokenize_no_ssplit:
            kwargs["tokenize_no_ssplit"] = True

        try:
            pipeline = stanza.Pipeline(**kwargs)
        except Exception as exc:
            # Most often a processor (e.g. ner) that was never downloaded. Retry
            # without the optional ones before giving up.
            reduced = ",".join(
                p for p in processors.split(",") if p in DEFAULT_PROCESSORS.split(",")
            )
            if reduced and reduced != processors:
                logger.warning(
                    "Stanza pipeline %r failed for %s (%s); retrying with %r",
                    processors,
                    language,
                    exc,
                    reduced,
                )
                kwargs["processors"] = reduced
                pipeline = stanza.Pipeline(**kwargs)
            else:
                raise ParserUnavailable(
                    f"could not build a Stanza pipeline for {language!r}: {exc}"
                ) from exc

        self._pipelines[language] = pipeline
        return pipeline

    # -- parsing -----------------------------------------------------------

    def parse(self, text: str, language: str) -> ParsedDocument:
        """Parse ``text`` into sentences of :class:`Token` objects."""
        if not text or not text.strip():
            return ParsedDocument(text=text, language=language, parser=self.name)

        doc = self._pipeline(language)(text)
        sentences = [
            self._convert_sentence(sentence, text, language) for sentence in doc.sentences
        ]
        return ParsedDocument(
            text=text, language=language, sentences=sentences, parser=self.name
        )

    def parse_sentence(self, text: str, language: str) -> ParsedSentence | None:
        """Parse ``text`` as a single sentence, without sentence splitting."""
        document = self.parse(text, language)
        if not document.sentences:
            return None
        if len(document.sentences) > 1:
            logger.debug(
                "input split into %d sentences; returning the first",
                len(document.sentences),
            )
        return document.sentences[0]

    # -- conversion --------------------------------------------------------

    def _convert_sentence(
        self, sentence: Any, doc_text: str, language: str
    ) -> ParsedSentence:
        entity_spans = self._entity_spans(sentence)
        tokens: list[Token] = []

        for word in sentence.words:
            start, end = self._word_offsets(word)
            raw_ner = self._entity_at(entity_spans, start, end) or self._word_ner(word)
            tokens.append(
                Token(
                    index=int(word.id),
                    text=word.text,
                    lemma=word.lemma or word.text,
                    upos=word.upos or "X",
                    xpos=word.xpos,
                    feats=_parse_feats(word.feats),
                    head=int(word.head or 0),
                    deprel=word.deprel or "dep",
                    start_char=start,
                    end_char=end,
                    ner=raw_ner,
                    entity_type=self._normalize_entity(raw_ner),
                )
            )

        self._repair_split_words(tokens)

        sent_start, sent_end = self._sentence_offsets(sentence, tokens)
        if sent_start is not None and sent_end is not None:
            surface = doc_text[sent_start:sent_end]
        else:
            surface = " ".join(token.text for token in tokens)

        return ParsedSentence(
            text=surface,
            language=language,
            tokens=tokens,
            start_char=sent_start,
            end_char=sent_end,
            parser=self.name,
        )

    @staticmethod
    def _repair_split_words(tokens: list[Token]) -> None:
        """Re-join a word a syllable-based tokenizer split across a punctuation token.

        Vietnamese tokenizers segment on syllables, which mishandles foreign words:
        "Paris." comes back as ``Pari`` + ``s.``, the second piece tagged PUNCT. Left
        alone, the frame records a location called "Pari", which then misses every
        gazetteer and entity lookup.

        The repair is deliberately narrow: only a PUNCT-tagged token whose text *starts
        with a letter* is touched, and only its leading letters move to the previous
        token. The punctuation itself stays where it is, so no index or head needs
        renumbering and no genuine tokenisation is altered.
        """
        for position in range(1, len(tokens)):
            token = tokens[position]
            if token.upos != "PUNCT" or not token.text[:1].isalpha():
                continue

            letters = ""
            for char in token.text:
                if not char.isalpha():
                    break
                letters += char
            if not letters:
                continue

            previous = tokens[position - 1]
            was_identity_lemma = previous.lemma == previous.text
            previous.text += letters
            if was_identity_lemma:
                previous.lemma = previous.text
            if previous.end_char is not None:
                previous.end_char += len(letters)

            remainder = token.text[len(letters) :]
            token.text = remainder
            token.lemma = remainder or "_"
            if token.start_char is not None:
                token.start_char += len(letters)
            token.misc["repaired_split"] = "true"

            logger.debug(
                "re-joined tokenizer split: %r + %r -> %r",
                previous.text[: -len(letters)],
                letters,
                previous.text,
            )

    @staticmethod
    def _word_offsets(word: Any) -> tuple[int | None, int | None]:
        """Character offsets for a word, falling back to its surface token.

        Multi-word tokens (French ``du`` -> ``de`` + ``le``) have no offsets of
        their own, so both syntactic words inherit the token's span.
        """
        start = getattr(word, "start_char", None)
        end = getattr(word, "end_char", None)
        if start is None or end is None:
            parent = getattr(word, "parent", None)
            if parent is not None:
                start = getattr(parent, "start_char", None)
                end = getattr(parent, "end_char", None)
        return (int(start) if start is not None else None, int(end) if end is not None else None)

    @staticmethod
    def _word_ner(word: Any) -> str | None:
        """Read a BIO tag off the word's surface token, stripping the B-/I- prefix."""
        parent = getattr(word, "parent", None)
        raw = getattr(parent, "ner", None) if parent is not None else None
        if not raw or raw in {"O", "_"}:
            return None
        return raw.split("-", 1)[-1] if "-" in raw else raw

    @staticmethod
    def _entity_spans(sentence: Any) -> list[tuple[int, int, str]]:
        spans: list[tuple[int, int, str]] = []
        for entity in getattr(sentence, "ents", None) or []:
            start = getattr(entity, "start_char", None)
            end = getattr(entity, "end_char", None)
            label = getattr(entity, "type", None)
            if start is not None and end is not None and label:
                spans.append((int(start), int(end), str(label)))
        return spans

    @staticmethod
    def _entity_at(
        spans: list[tuple[int, int, str]], start: int | None, end: int | None
    ) -> str | None:
        if start is None or end is None:
            return None
        for span_start, span_end, label in spans:
            if start >= span_start and end <= span_end:
                return label
        return None

    def _normalize_entity(self, label: str | None) -> str | None:
        if not label:
            return None
        if self._entity_normalizer is None:
            return label.upper()
        return self._entity_normalizer.normalize_entity_type(label)

    @staticmethod
    def _sentence_offsets(
        sentence: Any, tokens: list[Token]
    ) -> tuple[int | None, int | None]:
        surface_tokens = getattr(sentence, "tokens", None) or []
        if surface_tokens:
            start = getattr(surface_tokens[0], "start_char", None)
            end = getattr(surface_tokens[-1], "end_char", None)
            if start is not None and end is not None:
                return int(start), int(end)
        offsets = [(t.start_char, t.end_char) for t in tokens if t.start_char is not None]
        if offsets:
            return offsets[0][0], offsets[-1][1]
        return None, None
