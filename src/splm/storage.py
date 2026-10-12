"""SQLite storage for SPLM's knowledge base (spec section 34).

SQLite for the POC, but every query goes through this module so the move to
PostgreSQL is a change of connection handling rather than a rewrite. No SQL lives
outside here and :mod:`splm.linguistic.lexicon`.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Iterator

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

#: Tables from spec section 34, with the indexes the runtime lookups need.
SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS language_metadata (
    language        TEXT PRIMARY KEY,
    name            TEXT,
    pack_version    TEXT,
    source          TEXT,
    source_version  TEXT,
    license         TEXT,
    downloaded_at   TEXT,
    lexeme_count    INTEGER DEFAULT 0,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS lexeme (
    id              INTEGER PRIMARY KEY,
    language        TEXT NOT NULL,
    word            TEXT NOT NULL,
    lemma           TEXT NOT NULL,
    pos             TEXT,
    gender          TEXT,
    number          TEXT,
    register        TEXT,
    frequency       REAL,
    source          TEXT,
    source_version  TEXT,
    license         TEXT,
    UNIQUE (language, word, lemma, pos)
);
CREATE INDEX IF NOT EXISTS idx_lexeme_word   ON lexeme (language, word);
CREATE INDEX IF NOT EXISTS idx_lexeme_lemma  ON lexeme (language, lemma);
CREATE INDEX IF NOT EXISTS idx_lexeme_pos    ON lexeme (language, pos);

CREATE TABLE IF NOT EXISTS definition (
    id              INTEGER PRIMARY KEY,
    lexeme_id       INTEGER NOT NULL REFERENCES lexeme (id) ON DELETE CASCADE,
    sense_index     INTEGER DEFAULT 0,
    definition      TEXT NOT NULL,
    usage           TEXT,
    source          TEXT
);
CREATE INDEX IF NOT EXISTS idx_definition_lexeme ON definition (lexeme_id);

CREATE TABLE IF NOT EXISTS morphology (
    id              INTEGER PRIMARY KEY,
    lexeme_id       INTEGER REFERENCES lexeme (id) ON DELETE CASCADE,
    language        TEXT NOT NULL,
    lemma           TEXT NOT NULL,
    form            TEXT NOT NULL,
    pos             TEXT,
    features        TEXT,
    source          TEXT,
    UNIQUE (language, lemma, form, features)
);
CREATE INDEX IF NOT EXISTS idx_morphology_lemma ON morphology (language, lemma);
CREATE INDEX IF NOT EXISTS idx_morphology_form  ON morphology (language, form);

CREATE TABLE IF NOT EXISTS semantic_class (
    id              INTEGER PRIMARY KEY,
    language        TEXT NOT NULL,
    lemma           TEXT NOT NULL,
    class_name      TEXT NOT NULL,
    confidence      REAL DEFAULT 1.0,
    source          TEXT,
    UNIQUE (language, lemma, class_name)
);
CREATE INDEX IF NOT EXISTS idx_semantic_class_lemma ON semantic_class (language, lemma);
CREATE INDEX IF NOT EXISTS idx_semantic_class_name  ON semantic_class (language, class_name);

CREATE TABLE IF NOT EXISTS semantic_role (
    id              INTEGER PRIMARY KEY,
    language        TEXT NOT NULL,
    predicate_lemma TEXT NOT NULL,
    roleset         TEXT,
    argument        TEXT NOT NULL,
    descriptor      TEXT,
    function_tag    TEXT,
    splm_role       TEXT,
    source          TEXT,
    UNIQUE (language, predicate_lemma, roleset, argument)
);
CREATE INDEX IF NOT EXISTS idx_semantic_role_pred ON semantic_role (language, predicate_lemma);

CREATE TABLE IF NOT EXISTS syntax_rule (
    id              INTEGER PRIMARY KEY,
    language        TEXT NOT NULL,
    deprel          TEXT NOT NULL,
    marker          TEXT,
    splm_role       TEXT NOT NULL,
    probability     REAL DEFAULT 0.5,
    source          TEXT
);
CREATE INDEX IF NOT EXISTS idx_syntax_rule ON syntax_rule (language, deprel);

CREATE TABLE IF NOT EXISTS grammar_rule (
    id              INTEGER PRIMARY KEY,
    language        TEXT NOT NULL,
    name            TEXT NOT NULL,
    category        TEXT,
    definition      TEXT,
    source          TEXT,
    UNIQUE (language, name)
);

CREATE TABLE IF NOT EXISTS style_feature (
    id              INTEGER PRIMARY KEY,
    language        TEXT NOT NULL,
    style           TEXT NOT NULL,
    feature         TEXT NOT NULL,
    value           TEXT,
    weight          REAL DEFAULT 1.0,
    UNIQUE (language, style, feature, value)
);
CREATE INDEX IF NOT EXISTS idx_style_feature ON style_feature (language, style);

CREATE TABLE IF NOT EXISTS schema_version (
    version         INTEGER PRIMARY KEY,
    applied_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    """A thin, typed wrapper over one SQLite file."""

    def __init__(self, path: Path | str, *, read_only: bool = False) -> None:
        self.path = Path(path)
        self.read_only = read_only
        self._connection: sqlite3.Connection | None = None

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def connect(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection

        if self.read_only:
            if not self.exists:
                raise FileNotFoundError(f"no database at {self.path}")
            uri = f"file:{self.path}?mode=ro"
            self._connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, check_same_thread=False)

        self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- schema ------------------------------------------------------------

    def initialise(self) -> None:
        """Create the schema if it is not already there."""
        connection = self.connect()
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
        )
        connection.commit()
        logger.info("initialised database schema v%d at %s", SCHEMA_VERSION, self.path)

    def table_counts(self) -> dict[str, int]:
        """Row counts per table, for the UI's knowledge-base panel."""
        connection = self.connect()
        tables = [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        counts: dict[str, int] = {}
        for table in tables:
            try:
                counts[table] = int(
                    connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                )
            except sqlite3.Error as exc:
                logger.debug("could not count %s: %s", table, exc)
        return counts

    # -- queries -----------------------------------------------------------

    def query(self, sql: str, parameters: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return list(self.connect().execute(sql, tuple(parameters)))

    def iterate(self, sql: str, parameters: Iterable[Any] = ()) -> Iterator[sqlite3.Row]:
        yield from self.connect().execute(sql, tuple(parameters))

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        return self.connect().execute(sql, tuple(parameters))

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        self.connect().executemany(sql, [tuple(row) for row in rows])

    def commit(self) -> None:
        if self._connection is not None:
            self._connection.commit()


def open_database(config: Any | None = None, *, read_only: bool = True) -> Database:
    """Open the configured database. Does not create it when read-only."""
    from splm.config import get_config

    config = config or get_config()
    return Database(config.database_path, read_only=read_only)
