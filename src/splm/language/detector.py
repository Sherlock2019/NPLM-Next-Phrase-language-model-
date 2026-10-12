"""Language detection (spec section 12).

Returns language, confidence and - separately - locale, script and style hints.
Language and country are never conflated.

Two backends:

``ScriptHeuristicDetector``
    Dependency-free. Scores stopword hits and diacritic signatures. Deterministic,
    instant, good enough for the three POC languages and for unit tests.

``LangidDetector``
    Wraps ``py3langid`` when installed, restricted to the configured language set,
    and falls back to the heuristic on short or low-confidence input.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from splm.language.locale import Locale

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

#: High-frequency function words. Function words are the strongest cheap signal
#: because they are short, frequent and rarely borrowed.
STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        """the a an and or but if of to in on at by for with from as is are was were
        be been being will would can could should must have has had do does did not
        he she it they we you i this that these those there here his her their our
        my your its who what when where why how tomorrow yesterday today""".split()
    ),
    "fr": frozenset(
        """le la les un une des du de au aux et ou mais si que qui quoi dont ou
        est sont etait etaient sera seront avoir a ai as ont avons avez etre suis
        es sommes etes ne pas plus tres je tu il elle nous vous ils elles ce cet
        cette ces mon ton son notre votre leur dans sur sous avec pour par chez
        demain hier aujourd rencontrera train contrat negocier""".split()
    ),
    "vi": frozenset(
        """la co khong va hoac neu thi cua cho voi tu den o tai ve mot nhung cac
        nay do kia ay toi ban anh chi em ho no chung se dang da roi cung rat qua
        nguoi viec lam di duoc phai nen ma nhu boi vi tai sao khi nao dau gi
        ngay mai hom qua hom nay gap tau hop dong dam phan""".split()
    ),
}

#: Characters that only appear in some of the supported languages.
DIACRITIC_SIGNATURES: dict[str, str] = {
    # Vietnamese-only letters (horn and breve vowels, d with stroke).
    "vi": "ăâđêôơưĂÂĐÊÔƠƯ",
    # French accents; note none of these are Vietnamese-exclusive.
    "fr": "çœæÇŒÆ",
}

#: Letter+tone combinations typical of Vietnamese. Vietnamese stacks a tone mark
#: on an already-modified vowel, which French never does.
_VI_TONE_BASES = set("aăâeêioôơuưy")


@runtime_checkable
class LanguageDetectorBackend(Protocol):
    """Anything that can name the language of a string."""

    def detect(self, text: str) -> "LanguageDetection": ...


class LanguageDetection(BaseModel):
    """Result of language detection.

    ``language`` is an identity; ``locale`` is where/how it is being used. They are
    reported separately and a null locale is the normal case.
    """

    language: str
    confidence: float = Field(ge=0.0, le=1.0)
    locale: str | None = None
    script: str | None = None
    dialect: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    backend: str = "heuristic"

    @property
    def parsed_locale(self) -> Locale | None:
        return Locale.parse(self.locale)

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.6


def _dominant_script(text: str) -> str | None:
    """Name the script of the majority of the letters, e.g. ``Latin``."""
    counts: dict[str, int] = {}
    for char in text:
        if not char.isalpha():
            continue
        try:
            name = unicodedata.name(char)
        except ValueError:
            continue
        script = name.split(" ")[0].title()
        counts[script] = counts.get(script, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda key: counts[key])


def _vietnamese_tone_hits(text: str) -> int:
    """Count vowels carrying both a base modification and a tone mark."""
    hits = 0
    for char in unicodedata.normalize("NFD", text.lower()):
        if char in _VI_TONE_BASES:
            continue
        # Combining tone marks used by Vietnamese: grave, acute, tilde, hook, dot below.
        if char in "̣̀́̃̉":
            hits += 1
    return hits


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class ScriptHeuristicDetector:
    """Dependency-free detector over the configured candidate languages."""

    name = "heuristic"

    def __init__(self, languages: list[str] | None = None) -> None:
        self.languages = [lang for lang in (languages or ["en", "fr", "vi"])]

    def detect(self, text: str) -> LanguageDetection:
        stripped = text.strip()
        if not stripped:
            return LanguageDetection(
                language=self.languages[0] if self.languages else "en",
                confidence=0.0,
                backend=self.name,
            )

        # Accent-insensitive word list, so the stopword tables can stay ASCII.
        words = [w.lower() for w in _WORD.findall(_strip_accents(stripped))]
        total = max(len(words), 1)
        scores: dict[str, float] = {}

        for language in self.languages:
            stop = STOPWORDS.get(language, frozenset())
            hits = sum(1 for word in words if word in stop)
            score = hits / total

            signature = DIACRITIC_SIGNATURES.get(language, "")
            if signature and any(char in signature for char in stripped):
                score += 0.35

            if language == "vi":
                tone_hits = _vietnamese_tone_hits(stripped)
                if tone_hits:
                    score += min(0.45, 0.12 * tone_hits)
                # Vietnamese is strongly monosyllabic: many very short words.
                short_ratio = sum(1 for w in words if len(w) <= 4) / total
                if short_ratio > 0.8 and len(words) >= 4:
                    score += 0.1

            scores[language] = round(score, 4)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best, best_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0

        if best_score <= 0.0:
            # No evidence at all: say so rather than guessing confidently.
            confidence = 0.0
        else:
            margin = (best_score - runner_up) / best_score
            # Blend absolute evidence with how far ahead the winner is.
            confidence = min(0.99, 0.35 + 0.45 * min(best_score * 2, 1.0) + 0.2 * margin)

        return LanguageDetection(
            language=best,
            confidence=round(confidence, 4),
            script=_dominant_script(stripped),
            scores=scores,
            backend=self.name,
        )


class LangidDetector:
    """``py3langid`` backend, constrained to the configured languages."""

    name = "py3langid"

    def __init__(self, languages: list[str] | None = None) -> None:
        import py3langid  # noqa: PLC0415 - optional dependency, imported on use

        self.languages = languages or ["en", "fr", "vi"]
        self._identifier = py3langid.langid.LanguageIdentifier.from_pickled_model(
            py3langid.langid.MODEL_FILE, norm_probs=True
        )
        self._identifier.set_languages(self.languages)
        self._fallback = ScriptHeuristicDetector(self.languages)

    def detect(self, text: str) -> LanguageDetection:
        stripped = text.strip()
        if len(stripped) < 12:
            # Statistical identification is unreliable on fragments; the heuristic
            # is better there because function words dominate short strings.
            return self._fallback.detect(text)

        language, probability = self._identifier.classify(stripped)
        heuristic = self._fallback.detect(text)

        if heuristic.language != language and heuristic.confidence > probability:
            logger.debug(
                "langid said %s (%.2f), heuristic said %s (%.2f); taking heuristic",
                language,
                probability,
                heuristic.language,
                heuristic.confidence,
            )
            return heuristic

        return LanguageDetection(
            language=language,
            confidence=round(float(probability), 4),
            script=_dominant_script(stripped),
            scores={**heuristic.scores, language: round(float(probability), 4)},
            backend=self.name,
        )


class LanguageDetector:
    """Public entry point. Picks the best available backend.

    ``locale`` may be supplied by the caller (from a user profile, HTTP header,
    document metadata ...). It is passed through untouched and never used to
    decide the language.
    """

    def __init__(
        self,
        languages: list[str] | None = None,
        *,
        backend: LanguageDetectorBackend | None = None,
        prefer_statistical: bool = True,
    ) -> None:
        if languages is None:
            from splm.config import get_config

            languages = get_config().supported_languages
        self.languages = list(languages)

        if backend is not None:
            self._backend: LanguageDetectorBackend = backend
        elif prefer_statistical:
            try:
                self._backend = LangidDetector(self.languages)
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.debug("py3langid unavailable (%s); using heuristic detector", exc)
                self._backend = ScriptHeuristicDetector(self.languages)
        else:
            self._backend = ScriptHeuristicDetector(self.languages)

    @property
    def backend_name(self) -> str:
        return getattr(self._backend, "name", type(self._backend).__name__)

    def detect(
        self,
        text: str,
        *,
        locale: str | None = None,
        language_hint: str | None = None,
    ) -> LanguageDetection:
        """Detect the language of ``text``.

        ``language_hint`` short-circuits detection - use it when the caller already
        knows the language (a labelled corpus, an explicit ``--language`` flag).
        """
        if language_hint:
            return LanguageDetection(
                language=language_hint.lower(),
                confidence=1.0,
                locale=locale,
                script=_dominant_script(text),
                backend="hint",
            )

        result = self._backend.detect(text)
        if locale:
            parsed = Locale.parse(locale)
            result = result.model_copy(update={"locale": locale})
            if parsed and parsed.language != result.language:
                # Trust the text, not the locale tag, but say that they disagree.
                logger.debug(
                    "locale %s disagrees with detected language %s",
                    locale,
                    result.language,
                )
        return result
