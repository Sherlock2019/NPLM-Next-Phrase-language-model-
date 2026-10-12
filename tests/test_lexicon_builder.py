"""Building a language's dictionary from a public dump, and loading it on demand.

No network: the dump is a three-line file in the kaikki.org JSONL shape, and the one
test that exercises the background loader replaces the download with it.
"""

from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

import pytest

from splm.config import Config
from splm.linguistic.lexicon import Lexicon
from splm.linguistic.lexicon_builder import LexiconBuilder, LexiconLoader
from splm.model.word_tracker import LexicalStatus, WordCandidateTracker, build_trie_from_lexicon
from splm.storage import Database

ENTRIES = [
    {"word": "Paris", "pos": "name", "senses": [{"glosses": ["The capital city of France."]}]},
    {"word": "go", "pos": "verb", "senses": [{"glosses": ["To move."]}, {"glosses": ["To leave."]}]},
    {
        "word": "went",
        "pos": "verb",
        "senses": [{"glosses": ["simple past of go"], "form_of": [{"word": "go"}]}],
    },
]


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    path = tmp_path / "en.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for entry in ENTRIES:
            handle.write(json.dumps(entry) + "\n")
        handle.write("not json\n")
    return path


def make_config(project_root: Path, tmp_path: Path, *, auto_download: bool) -> Config:
    return Config.load(
        project_root,
        apply_env=False,
        overrides={
            "app.lexicon.auto_download": auto_download,
            "app.paths.database": str(tmp_path / "splm.db"),
            "data_sources.manifest": str(tmp_path / "MANIFEST.json"),
            "data_sources.sources.wiktionary.dest": str(tmp_path / "raw"),
        },
    )


def open_built(config: Config) -> Lexicon:
    return Lexicon(Database(config.database_path, read_only=True))


def test_build_makes_the_language_available(project_root, tmp_path, archive):
    config = make_config(project_root, tmp_path, auto_download=False)
    assert not open_built(config).has_language("en")

    count = LexiconBuilder(config).build("en", archive=archive)

    lexicon = open_built(config)
    assert count == 3
    assert lexicon.has_language("en")
    assert not lexicon.has_language("fr")
    assert lexicon.sorted_words("en") == ["go", "paris", "went"]


def test_inflected_form_points_at_its_lemma(project_root, tmp_path, archive):
    config = make_config(project_root, tmp_path, auto_download=False)
    LexiconBuilder(config).build("en", archive=archive)

    entry = open_built(config).lookup("went", "en")
    assert entry is not None
    assert entry.lemma == "go"
    assert entry.definitions == ["simple past of go"]
    assert entry.license


def test_rebuild_replaces_rather_than_duplicates(project_root, tmp_path, archive):
    config = make_config(project_root, tmp_path, auto_download=False)
    builder = LexiconBuilder(config)
    builder.build("en", archive=archive)
    assert builder.build("en", archive=archive) == 3
    assert open_built(config).lookup("go", "en").definitions == ["To move.", "To leave."]


def test_built_lexicon_judges_candidates(project_root, tmp_path, archive):
    config = make_config(project_root, tmp_path, auto_download=False)
    LexiconBuilder(config).build("en", archive=archive)

    tracker = WordCandidateTracker(build_trie_from_lexicon(open_built(config), "en"))
    assert tracker.judge("ĠParis").status is LexicalStatus.COMPLETE_WORD
    assert tracker.judge("ĠPar").status is LexicalStatus.VALID_PREFIX
    assert tracker.judge("Ġzzz").status is LexicalStatus.NOT_A_PREFIX


def test_unbuilt_language_stays_unknown(project_root, tmp_path, archive):
    """One language's dictionary must not make another language's words look wrong."""
    config = make_config(project_root, tmp_path, auto_download=False)
    LexiconBuilder(config).build("en", archive=archive)

    tracker = WordCandidateTracker(build_trie_from_lexicon(open_built(config), "fr"))
    assert tracker.judge("Ġbonjour").status is LexicalStatus.UNKNOWN


def test_loader_does_nothing_when_auto_download_is_off(project_root, tmp_path, monkeypatch):
    config = make_config(project_root, tmp_path, auto_download=False)
    monkeypatch.setattr(
        LexiconBuilder, "download", lambda *args, **kwargs: pytest.fail("must not download")
    )

    assert LexiconLoader(config).ensure("en")["state"] == "missing"
    assert not config.database_path.exists()


def test_loader_builds_a_language_it_meets(project_root, tmp_path, archive, monkeypatch):
    config = make_config(project_root, tmp_path, auto_download=True)
    monkeypatch.setattr(LexiconBuilder, "download", lambda self, language, progress=None: archive)
    loader = LexiconLoader(config)

    assert loader.ensure("en")["state"] in {"queued", "downloading", "building", "ready"}
    deadline = time.monotonic() + 10
    while loader.status("en")["state"] != "ready" and time.monotonic() < deadline:
        time.sleep(0.05)

    assert loader.status("en") == {
        "language": "en",
        "state": "ready",
        "detail": "dictionary loaded",
        "entries": 3,
    }


def test_loader_reports_a_language_with_no_source(project_root, tmp_path):
    config = make_config(project_root, tmp_path, auto_download=True)
    assert LexiconLoader(config).ensure("xx")["state"] == "unavailable"
