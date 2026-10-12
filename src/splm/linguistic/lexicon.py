"""Dictionary / lexicon access (spec section 15).

Wiktionary-derived data in SQLite, queried one word at a time. The spec is explicit
that the dictionary must never be injected into the model's context - only relevant
lookups happen, and they happen here.

The lexicon is *optional*. Until ``scripts/build_lexicon.py`` has run there is no
database, and every method returns "unknown" rather than "absent". That distinction
is the whole reason the lexical feature carries an ``informative`` flag: a candidate
must never be penalised because SPLM has no dictionary to check it against.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from splm.storage import Database

logger = logging.getLogger(__name__)


@dataclass
class LexemeEntry:
    """One dictionary entry, with the provenance spec section 15 requires."""

    language: str
    word: str
    lemma: str
    pos: str | None = None
    definitions: list[str] = field(default_factory=list)
    semantic_classes: list[str] = field(default_factory=list)
    gender: str | None = None
    number: str | None = None
    register: str | None = None
    source: str | None = None
    source_version: str | None = None
    license: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.definitions and not self.semantic_classes


class Lexicon:
    """Read-only lexical lookups, safe to use when the database does not exist."""

    def __init__(self, database: Database | None = None) -> None:
        self._database = database
        self._loaded: set[str] = set()
        self._words: dict[str, list[str]] = {}
        self._words_lock = threading.Lock()

    @property
    def available(self) -> bool:
        """Whether a built lexicon database is actually present."""
        return self._database is not None and self._database.exists

    def has_language(self, language: str) -> bool:
        """Whether ``language`` is fully built.

        The builder writes a language's metadata row last, so rows from a build still
        in progress do not count.
        """
        if language in self._loaded:
            return True
        if not self.available:
            return False
        if self._query("SELECT 1 FROM language_metadata WHERE language = ?", (language,)):
            self._loaded.add(language)
            return True
        return False

    def sorted_words(self, language: str) -> list[str]:
        """Every surface form of a loaded language, lowercased, unique and sorted.

        Read once and kept: this is what the candidate scorer's prefix checks run
        against. Empty until the language is fully built.
        """
        with self._words_lock:
            words = self._words.get(language)
            if words is None:
                if not self.has_language(language):
                    return []
                words = sorted({word.lower() for word in self.iter_words(language)})
                self._words[language] = words
            return words

    def describe(self) -> dict[str, Any]:
        """Status for the UI, so a missing lexicon is visible rather than silent."""
        if not self.available:
            return {
                "available": False,
                "note": "no lexicon database; run python scripts/build_lexicon.py",
            }
        assert self._database is not None
        try:
            counts = self._database.table_counts()
            languages = [
                dict(row)
                for row in self._database.query(
                    "SELECT language, source, source_version, license, lexeme_count "
                    "FROM language_metadata"
                )
            ]
        except Exception as exc:
            return {"available": False, "note": f"database unreadable: {exc}"}
        return {
            "available": True,
            "path": str(self._database.path),
            "tables": counts,
            "languages": languages,
        }

    # -- lookups -----------------------------------------------------------

    def lookup(self, word: str, language: str) -> LexemeEntry | None:
        """Find a surface form. Returns ``None`` when unknown *or* unavailable."""
        if not self.available or not word:
            return None
        rows = self._query(
            "SELECT * FROM lexeme WHERE language = ? AND word = ? COLLATE NOCASE LIMIT 5",
            (language, word),
        )
        return self._build_entry(rows, language)

    def lookup_lemma(self, lemma: str, language: str) -> LexemeEntry | None:
        if not self.available or not lemma:
            return None
        rows = self._query(
            "SELECT * FROM lexeme WHERE language = ? AND lemma = ? COLLATE NOCASE LIMIT 5",
            (language, lemma),
        )
        return self._build_entry(rows, language)

    def get_possible_pos(self, word: str, language: str = "en") -> list[str]:
        """Every part of speech this form can have. Empty means unknown."""
        if not self.available or not word:
            return []
        rows = self._query(
            "SELECT DISTINCT pos FROM lexeme "
            "WHERE language = ? AND word = ? COLLATE NOCASE AND pos IS NOT NULL",
            (language, word),
        )
        return [row["pos"] for row in rows]

    def get_semantic_classes(self, word: str, language: str = "en") -> list[str]:
        """Semantic categories for a word, via its lemma."""
        if not self.available or not word:
            return []
        rows = self._query(
            "SELECT DISTINCT sc.class_name FROM semantic_class sc "
            "WHERE sc.language = ? AND sc.lemma IN ("
            "  SELECT lemma FROM lexeme WHERE language = ? AND word = ? COLLATE NOCASE"
            ") "
            "UNION "
            "SELECT DISTINCT class_name FROM semantic_class "
            "WHERE language = ? AND lemma = ? COLLATE NOCASE",
            (language, language, word, language, word),
        )
        return [row["class_name"] for row in rows]

    def get_word_forms(self, lemma: str, language: str = "en") -> list[dict[str, Any]]:
        """Inflected forms of a lemma, with their morphological features."""
        if not self.available or not lemma:
            return []
        rows = self._query(
            "SELECT form, pos, features FROM morphology "
            "WHERE language = ? AND lemma = ? COLLATE NOCASE",
            (language, lemma),
        )
        forms: list[dict[str, Any]] = []
        for row in rows:
            features: dict[str, Any] = {}
            if row["features"]:
                try:
                    features = json.loads(row["features"])
                except (TypeError, ValueError):
                    features = {"raw": row["features"]}
            forms.append({"form": row["form"], "pos": row["pos"], "features": features})
        return forms

    def predicate_roles(self, lemma: str, language: str = "en") -> list[dict[str, Any]]:
        """PropBank-derived argument structure for a predicate.

        Returned per argument with its own descriptor, because PropBank arguments are
        predicate-specific: ARG0 is not always an agent (spec section 18).
        """
        if not self.available or not lemma:
            return []
        rows = self._query(
            "SELECT roleset, argument, descriptor, function_tag, splm_role "
            "FROM semantic_role WHERE language = ? AND predicate_lemma = ? COLLATE NOCASE",
            (language, lemma),
        )
        return [dict(row) for row in rows]

    def iter_words(self, language: str, limit: int | None = None) -> Iterator[str]:
        """Stream surface forms, for building a :class:`LexicalTrie`."""
        if not self.available:
            return iter(())
        sql = "SELECT word FROM lexeme WHERE language = ?"
        parameters: tuple[Any, ...] = (language,)
        if limit:
            sql += " LIMIT ?"
            parameters = (language, int(limit))
        return (row["word"] for row in self._iterate(sql, parameters))

    def word_count(self, language: str) -> int:
        if not self.available:
            return 0
        rows = self._query(
            "SELECT COUNT(*) AS n FROM lexeme WHERE language = ?", (language,)
        )
        return int(rows[0]["n"]) if rows else 0

    # -- internals ---------------------------------------------------------

    def _query(self, sql: str, parameters: tuple[Any, ...]) -> list[Any]:
        assert self._database is not None
        try:
            return self._database.query(sql, parameters)
        except Exception as exc:
            logger.debug("lexicon query failed: %s", exc)
            return []

    def _iterate(self, sql: str, parameters: tuple[Any, ...]) -> Iterator[Any]:
        assert self._database is not None
        try:
            yield from self._database.iterate(sql, parameters)
        except Exception as exc:
            logger.debug("lexicon iteration failed: %s", exc)

    def _build_entry(self, rows: list[Any], language: str) -> LexemeEntry | None:
        if not rows:
            return None
        primary = rows[0]
        definitions = [
            row["definition"]
            for row in self._query(
                "SELECT definition FROM definition WHERE lexeme_id = ? ORDER BY sense_index",
                (primary["id"],),
            )
        ]
        return LexemeEntry(
            language=language,
            word=primary["word"],
            lemma=primary["lemma"],
            pos=primary["pos"],
            definitions=definitions,
            semantic_classes=self.get_semantic_classes(primary["lemma"], language),
            gender=primary["gender"],
            number=primary["number"],
            register=primary["register"],
            source=primary["source"],
            source_version=primary["source_version"],
            license=primary["license"],
        )


@lru_cache(maxsize=4)
def _open_lexicon_at(path_text: str) -> Lexicon:
    """Cache by path - a Config object is not hashable and may be rebuilt freely."""
    path = Path(path_text)
    if not path.is_file():
        logger.info("no lexicon database at %s; lexical features stay neutral", path)
    # Bound to the path even when the file is absent, so a database built while the
    # app is running is picked up without reopening.
    return Lexicon(Database(path, read_only=True))


def open_lexicon(config: Any | None = None) -> Lexicon:
    """Open the configured lexicon, or an empty one when the database is absent."""
    from splm.config import get_config

    config = config or get_config()
    return _open_lexicon_at(str(config.database_path))
