"""The SPLM analysis pipeline (spec section 29).

    INPUT -> detect language -> parse -> lexical lookup -> Phrase DNA
          -> update context graph -> expected slot -> (candidates, re-scoring)

This module owns the first half of that cycle: everything that turns text into
structure. Candidate generation and re-ranking live in :mod:`splm.model`, which
consumes an :class:`Analysis` produced here.

One object, lazily constructed, shared by the CLI, the API and the UI so they can
never drift apart.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from splm.config import Config, get_config
from splm.language.detector import LanguageDetection, LanguageDetector
from splm.language.packs import LanguagePackRegistry, get_registry
from splm.linguistic.factory import build_parser
from splm.linguistic.lexicon_builder import LOADING_STATES, ensure_lexicon
from splm.linguistic.morphology import Morphology, MorphologyEngine
from splm.linguistic.parser import LinguisticParser, ParsedDocument, ParsedSentence
from splm.linguistic.semantic_roles import SemanticRoleEngine
from splm.phrase.builder import PhraseFrameBuilder
from splm.phrase.schema import UniversalPhraseFrame

logger = logging.getLogger(__name__)


@dataclass
class Analysis:
    """Everything SPLM has understood about a piece of text."""

    text: str
    detection: LanguageDetection
    document: ParsedDocument | None = None
    frames: list[UniversalPhraseFrame] = field(default_factory=list)
    morphology: list[dict[int, Morphology]] = field(default_factory=list)
    style: str | None = None
    style_confidence: float | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def language(self) -> str:
        return self.detection.language

    @property
    def frame(self) -> UniversalPhraseFrame | None:
        """The frame of the last sentence - the one a prediction continues."""
        return self.frames[-1] if self.frames else None

    @property
    def sentence(self) -> ParsedSentence | None:
        if self.document is None or not self.document.sentences:
            return None
        return self.document.sentences[-1]

    @property
    def parsed(self) -> bool:
        return self.document is not None and bool(self.document.sentences)


class SPLMPipeline:
    """Text in, structure out. Components are injectable for testing."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        registry: LanguagePackRegistry | None = None,
        detector: LanguageDetector | None = None,
        parser: LinguisticParser | None = None,
        builder: PhraseFrameBuilder | None = None,
        style_engine: Any | None = None,
    ) -> None:
        self.config = config or get_config()
        self.registry = registry or get_registry(self.config.language_packs_dir)

        self._detector = detector
        self._parser = parser
        self._builder = builder
        self._style_engine = style_engine

        self.morphology = MorphologyEngine(self.registry)
        self.semantic_roles = SemanticRoleEngine(self.registry)

        self._context_graph: Any | None = None

    # -- lazily built components ------------------------------------------

    @property
    def detector(self) -> LanguageDetector:
        if self._detector is None:
            self._detector = LanguageDetector(self.config.supported_languages)
        return self._detector

    @property
    def parser(self) -> LinguisticParser:
        if self._parser is None:
            self._parser = build_parser(self.config)
        return self._parser

    @property
    def builder(self) -> PhraseFrameBuilder:
        if self._builder is None:
            self._builder = PhraseFrameBuilder(
                self.registry,
                morphology=self.morphology,
                semantic_roles=self.semantic_roles,
            )
        return self._builder

    @property
    def style_engine(self) -> Any | None:
        if self._style_engine is None:
            try:
                from splm.style.detector import StyleDetector

                self._style_engine = StyleDetector(self.registry)
            except Exception as exc:  # pragma: no cover - style layer is optional
                logger.debug("style detector unavailable: %s", exc)
                self._style_engine = False
        return self._style_engine or None

    @property
    def context_graph(self) -> Any | None:
        """The discourse graph, or ``None`` when disabled in config."""
        if not self.config.get("app.context_graph.enabled", True):
            return None
        if self._context_graph is None:
            from splm.graph.context_graph import ContextGraph

            self._context_graph = ContextGraph()
        return self._context_graph

    def reset_context(self) -> None:
        """Forget the discourse so far - a new conversation, not a new sentence."""
        self._context_graph = None

    # -- analysis ----------------------------------------------------------

    def analyze(
        self,
        text: str,
        *,
        language: str | None = None,
        locale: str | None = None,
        style: str | None = None,
        detect_style: bool = True,
        update_context: bool = False,
    ) -> Analysis:
        """Run language detection, parsing and frame building over ``text``.

        ``update_context`` adds the resulting frames to the discourse graph. It is
        off by default because a prediction step re-analyses the same growing text
        many times, and adding it repeatedly would corrupt the record. Callers that
        advance the discourse - a chat turn, a document sentence - pass True.
        """
        timings: dict[str, float] = {}
        warnings: list[str] = []

        started = time.perf_counter()
        detection = self.detector.detect(text, locale=locale, language_hint=language)
        timings["detect"] = (time.perf_counter() - started) * 1000

        if detection.language not in self.config.supported_languages:
            warnings.append(
                f"detected language {detection.language!r} has no language pack; "
                f"supported: {self.config.supported_languages}"
            )
        else:
            # The language is now known, chosen or detected: make sure its dictionary
            # is loaded, or on its way. This never waits for a download.
            try:
                lexicon = ensure_lexicon(self.config, detection.language)
            except Exception as exc:
                logger.warning("lexicon check failed for %r: %s", detection.language, exc)
            else:
                if lexicon["state"] in LOADING_STATES:
                    warnings.append(
                        f"dictionary for {detection.language!r} is still loading "
                        f"({lexicon['detail']}); lexical features are neutral until it is ready"
                    )

        detected_style, style_confidence = style, None
        if style is None and detect_style and self.style_engine is not None:
            started = time.perf_counter()
            result = self.style_engine.detect(text, detection.language)
            detected_style = result.style
            style_confidence = result.confidence
            timings["style"] = (time.perf_counter() - started) * 1000

        analysis = Analysis(
            text=text,
            detection=detection,
            style=detected_style,
            style_confidence=style_confidence,
            timings_ms=timings,
            warnings=warnings,
        )

        started = time.perf_counter()
        try:
            document = self.parser.parse(text, detection.language)
        except Exception as exc:
            # A missing parser model must not take down the whole pipeline: the base
            # model can still answer, just without structural help.
            logger.warning("parsing failed for %r: %s", detection.language, exc)
            analysis.warnings.append(f"parse failed: {exc}")
            return analysis
        timings["parse"] = (time.perf_counter() - started) * 1000
        analysis.document = document

        started = time.perf_counter()
        analysis.frames = [
            self.builder.build(sentence, style=detected_style, locale=locale)
            for sentence in document.sentences
        ]
        analysis.morphology = [
            self.morphology.analyze_sentence(sentence) for sentence in document.sentences
        ]
        timings["frames"] = (time.perf_counter() - started) * 1000

        if update_context:
            graph = self.context_graph
            if graph is not None:
                started = time.perf_counter()
                graph.add_frames(analysis.frames)
                timings["context_graph"] = (time.perf_counter() - started) * 1000

        return analysis

    def parse_frame(
        self, text: str, *, language: str | None = None
    ) -> UniversalPhraseFrame | None:
        """Convenience wrapper: the frame of the first sentence, or ``None``."""
        analysis = self.analyze(text, language=language)
        return analysis.frames[0] if analysis.frames else None
