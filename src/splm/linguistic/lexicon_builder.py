"""Build the lexicon from public dictionary dumps, one language at a time (spec section 15).

The source is Wiktionary as extracted by wiktextract and published per language on
kaikki.org; which dump belongs to which language is read from
``config/data_sources.yaml``, never from here.

Two entry points share this module:

* ``scripts/build_lexicon.py`` builds languages explicitly, in the foreground.
* :func:`ensure_lexicon` is called by the pipeline with the language it was given or
  detected. When ``app.lexicon.auto_download`` is on and that language has no
  dictionary yet, it fetches and builds one on a background thread.

The second path is the one exception to "nothing is downloaded at runtime", and it is
not silent: it is opt-in through config, logged, visible through :func:`lexicon_status`,
and writes the same provenance to ``data/MANIFEST.json`` as every other download.
A language only counts as loaded once its ``language_metadata`` row exists, which is
written last, so a half-built dictionary is never consulted.
"""

from __future__ import annotations

import gzip
import json
import logging
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from splm.config import Config, get_config
from splm.linguistic.lexicon import open_lexicon
from splm.storage import Database

logger = logging.getLogger(__name__)

SOURCE_KEY = "data_sources.sources.wiktionary"

#: Entries between commits and progress reports while ingesting.
BATCH_SIZE = 20_000

#: States in which a build is under way and the dictionary is not yet usable.
LOADING_STATES = frozenset({"queued", "downloading", "building"})

Progress = Callable[[str, dict[str, Any]], None]


class LexiconSourceError(RuntimeError):
    """No public dictionary is configured for the requested language."""


class LexiconBuilder:
    """Downloads one language's dictionary dump and loads it into the database."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()
        self.source: dict[str, Any] = self.config.get(SOURCE_KEY, {}) or {}

    # -- source ------------------------------------------------------------

    def supports(self, language: str) -> bool:
        return self.url_for(language) is not None

    def url_for(self, language: str) -> str | None:
        name = (self.source.get("dump_names") or {}).get(language)
        template = self.source.get("url_template")
        if not name or not template:
            return None
        return str(template).format(name=name)

    def archive_path(self, language: str) -> Path:
        directory = self.config.path(f"{SOURCE_KEY}.dest", "data/raw/wiktionary")
        return directory / f"{language}.jsonl.gz"

    @property
    def manifest_path(self) -> Path:
        return self.config.path("data_sources.manifest", "data/MANIFEST.json")

    # -- download ----------------------------------------------------------

    def download(self, language: str, progress: Progress | None = None) -> Path:
        """Fetch the dump for ``language`` and record where it came from."""
        url = self.url_for(language)
        if url is None:
            raise LexiconSourceError(f"no dictionary source configured for {language!r}")

        target = self.archive_path(language)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")

        logger.info("downloading %s dictionary from %s", language, url)
        request = urllib.request.Request(url, headers={"User-Agent": "splm-lexicon-builder"})
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            version = response.headers.get("Last-Modified")
            done = 0
            while chunk := response.read(1 << 20):
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress("downloading", {"bytes_done": done, "bytes_total": total})
        partial.replace(target)

        self._record_provenance(
            {
                "name": "wiktionary",
                "language": language,
                "provider": self.source.get("provider"),
                "homepage": self.source.get("homepage"),
                "url": url,
                "version": version,
                "license": self.source.get("license"),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "destination": str(target),
            }
        )
        return target

    # -- build -------------------------------------------------------------

    def build(
        self,
        language: str,
        *,
        archive: Path | None = None,
        force: bool = False,
        progress: Progress | None = None,
    ) -> int:
        """Make ``language`` available in the lexicon. Returns its entry count.

        ``archive`` supplies an already downloaded dump; otherwise the cached one is
        reused, or fetched when absent or when ``force`` is set.
        """
        if archive is None:
            archive = self.archive_path(language)
            if force or not archive.is_file():
                archive = self.download(language, progress)

        provenance = self._provenance(language)
        database = Database(self.config.database_path)
        try:
            database.initialise()
            count = self._ingest(database, language, archive, provenance, progress)
            database.execute(
                "INSERT OR REPLACE INTO language_metadata "
                "(language, name, source, source_version, license, downloaded_at, lexeme_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    language,
                    (self.source.get("dump_names") or {}).get(language),
                    self.source.get("provider"),
                    provenance.get("version"),
                    self.source.get("license"),
                    provenance.get("downloaded_at"),
                    count,
                ),
            )
            database.commit()
        finally:
            database.close()

        logger.info("lexicon for %s built: %d entries", language, count)
        return count

    def _ingest(
        self,
        database: Database,
        language: str,
        archive: Path,
        provenance: dict[str, Any],
        progress: Progress | None,
    ) -> int:
        """Stream the dump into ``lexeme`` and ``definition``, replacing old rows."""
        provider = self.source.get("provider")
        version = provenance.get("version")
        licence = self.source.get("license")
        max_definitions = int(self.config.get("app.lexicon.max_definitions", 3))

        # Removing the metadata row first is what marks the language as not loaded
        # for the duration of the rebuild.
        database.execute("DELETE FROM language_metadata WHERE language = ?", (language,))
        database.execute("DELETE FROM lexeme WHERE language = ?", (language,))
        database.commit()

        seen = 0
        with gzip.open(archive, "rt", encoding="utf-8") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                word = entry.get("word")
                if not word:
                    continue

                # An inflected form's entry names its lemma; anything else is its own.
                lemma = word
                glosses: list[str] = []
                for sense in entry.get("senses") or ():
                    form_of = sense.get("form_of") or ()
                    if lemma == word and form_of and form_of[0].get("word"):
                        lemma = form_of[0]["word"]
                    if sense.get("glosses") and len(glosses) < max_definitions:
                        glosses.append(sense["glosses"][-1])

                cursor = database.execute(
                    "INSERT OR IGNORE INTO lexeme "
                    "(language, word, lemma, pos, source, source_version, license) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (language, word, lemma, entry.get("pos"), provider, version, licence),
                )
                if cursor.rowcount and glosses:
                    database.executemany(
                        "INSERT INTO definition (lexeme_id, sense_index, definition, source) "
                        "VALUES (?, ?, ?, ?)",
                        [
                            (cursor.lastrowid, index, gloss, provider)
                            for index, gloss in enumerate(glosses)
                        ],
                    )

                seen += 1
                if seen % BATCH_SIZE == 0:
                    database.commit()
                    if progress:
                        progress("building", {"entries": seen})
        database.commit()

        rows = database.query("SELECT COUNT(*) AS n FROM lexeme WHERE language = ?", (language,))
        return int(rows[0]["n"])

    # -- provenance --------------------------------------------------------

    def _load_manifest(self) -> dict[str, Any]:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"artefacts": []}

    def _provenance(self, language: str) -> dict[str, Any]:
        for entry in self._load_manifest().get("artefacts", []):
            if (entry.get("name"), entry.get("language")) == ("wiktionary", language):
                return entry
        return {}

    def _record_provenance(self, entry: dict[str, Any]) -> None:
        """Add or replace a manifest entry, keyed like scripts/download_resources.py."""
        manifest = self._load_manifest()
        artefacts: list[dict[str, Any]] = manifest.setdefault("artefacts", [])
        key = (entry["name"], entry.get("language"))
        artefacts[:] = [
            existing
            for existing in artefacts
            if (existing.get("name"), existing.get("language")) != key
        ]
        artefacts.append(entry)
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )


class LexiconLoader:
    """Loads a language's dictionary the first time the app meets that language."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()
        self.builder = LexiconBuilder(self.config)
        self._status: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        # SQLite takes one writer at a time, so builds queue behind each other.
        self._build_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("app.lexicon.auto_download", False))

    def status(self, language: str) -> dict[str, Any]:
        """Where ``language`` stands, without starting anything."""
        with self._lock:
            return dict(self._status.get(language) or self._resolve(language))

    def ensure(self, language: str) -> dict[str, Any]:
        """Report where ``language`` stands, starting a background build if needed."""
        with self._lock:
            current = self._status.get(language) or self._resolve(language)
            if current["state"] == "missing" and self.enabled:
                current = self._set(language, "queued", "waiting to download")
                threading.Thread(
                    target=self._run, args=(language,), name=f"lexicon-{language}", daemon=True
                ).start()
            return dict(current)

    # -- internals ---------------------------------------------------------

    def _resolve(self, language: str) -> dict[str, Any]:
        """Work out a language's state from what is on disk. Caller holds the lock."""
        if open_lexicon(self.config).has_language(language):
            return self._set(language, "ready", "dictionary loaded")
        if not self.builder.supports(language):
            return self._set(language, "unavailable", "no public dictionary source configured")
        # Not remembered: a build by scripts/build_lexicon.py should be noticed later.
        return {
            "language": language,
            "state": "missing",
            "detail": f"not built; run python scripts/build_lexicon.py --languages {language}",
        }

    def _set(self, language: str, state: str, detail: str, **extra: Any) -> dict[str, Any]:
        status = {"language": language, "state": state, "detail": detail, **extra}
        self._status[language] = status
        return status

    def _update(self, language: str, state: str, detail: str, **extra: Any) -> None:
        with self._lock:
            self._set(language, state, detail, **extra)

    def _run(self, language: str) -> None:
        def progress(state: str, info: dict[str, Any]) -> None:
            if state == "downloading":
                detail = f"downloaded {info['bytes_done'] >> 20} of {info['bytes_total'] >> 20} MB"
            else:
                detail = f"{info['entries']:,} entries read"
            self._update(language, state, detail, **info)

        with self._build_lock:
            try:
                count = self.builder.build(language, progress=progress)
            except Exception as exc:
                # Recorded rather than retried: a failing source should not be hit on
                # every request. Restarting the app tries again.
                logger.warning("lexicon build for %s failed: %s", language, exc)
                self._update(language, "failed", f"build failed: {exc}")
                return
        self._update(language, "ready", "dictionary loaded", entries=count)


_loaders: dict[str, LexiconLoader] = {}
_loaders_lock = threading.Lock()


def get_loader(config: Config | None = None) -> LexiconLoader:
    """One loader per database, so every engine sharing it shares its builds."""
    config = config or get_config()
    key = str(config.database_path)
    with _loaders_lock:
        if key not in _loaders:
            _loaders[key] = LexiconLoader(config)
        return _loaders[key]


def ensure_lexicon(config: Config | None, language: str) -> dict[str, Any]:
    """Make sure ``language`` has, or is getting, a dictionary. Never blocks on a build."""
    return get_loader(config).ensure(language)


def lexicon_status(config: Config | None = None) -> dict[str, Any]:
    """Per-language dictionary status for the supported languages."""
    loader = get_loader(config)
    return {
        "auto_download": loader.enabled,
        "languages": {
            language: loader.status(language) for language in loader.config.supported_languages
        },
    }
