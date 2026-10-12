"""Shared test fixtures.

Two ways to get a parsed sentence:

``frames`` / ``frame_for``
    Built from the committed CoNLL-U fixtures in ``tests/fixtures``. No parser
    model needed, deterministic, fast. This is what most tests use.

``pipeline``
    The real pipeline including the parser. Tests using it are marked ``parser``
    and skip when no model is installed, so the suite passes on a clean checkout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from splm.config import Config
from splm.language.packs import LanguagePackRegistry
from splm.linguistic.conllu import parse_conllu
from splm.linguistic.morphology import MorphologyEngine
from splm.linguistic.parser import ParsedSentence
from splm.linguistic.semantic_roles import SemanticRoleEngine
from splm.phrase.builder import PhraseFrameBuilder
from splm.phrase.schema import UniversalPhraseFrame

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def config(project_root: Path) -> Config:
    # No dictionary, and no fetching one: results must not depend on what happens to
    # have been downloaded onto this machine.
    return Config.load(
        project_root,
        apply_env=False,
        overrides={
            "app.lexicon.auto_download": False,
            "app.paths.database": "data/no-lexicon-in-tests.db",
        },
    )


@pytest.fixture(scope="session")
def registry(config: Config) -> LanguagePackRegistry:
    return LanguagePackRegistry(config.language_packs_dir)


@pytest.fixture(scope="session")
def universal(registry: LanguagePackRegistry):
    return registry.universal()


@pytest.fixture(scope="session")
def morphology(registry: LanguagePackRegistry) -> MorphologyEngine:
    return MorphologyEngine(registry)


@pytest.fixture(scope="session")
def role_engine(registry: LanguagePackRegistry) -> SemanticRoleEngine:
    return SemanticRoleEngine(registry)


@pytest.fixture(scope="session")
def builder(
    registry: LanguagePackRegistry,
    morphology: MorphologyEngine,
    role_engine: SemanticRoleEngine,
) -> PhraseFrameBuilder:
    return PhraseFrameBuilder(registry, morphology=morphology, semantic_roles=role_engine)


def _load_fixture(language: str, registry: LanguagePackRegistry) -> dict[str, ParsedSentence]:
    path = FIXTURE_DIR / f"{language}.conllu"
    if not path.is_file():
        return {}
    document = parse_conllu(
        path.read_text(encoding="utf-8"), language, entity_normalizer=registry.universal()
    )
    return {sentence.text.strip(): sentence for sentence in document.sentences}


@pytest.fixture(scope="session")
def sentences(registry: LanguagePackRegistry) -> dict[str, dict[str, ParsedSentence]]:
    """Every fixture sentence, keyed by language then by surface text."""
    return {
        language: _load_fixture(language, registry)
        for language in ("en", "fr", "vi")
    }


@pytest.fixture(scope="session")
def sentence_for(
    sentences: dict[str, dict[str, ParsedSentence]]
) -> Callable[..., ParsedSentence]:
    """Look up a fixture sentence, skipping the test when it is missing."""

    def lookup(text: str, language: str = "en") -> ParsedSentence:
        available = sentences.get(language, {})
        if not available:
            pytest.skip(
                f"no CoNLL-U fixture for {language!r}; "
                f"run python scripts/make_fixtures.py --languages {language}"
            )
        parsed = available.get(text.strip())
        if parsed is None:
            pytest.skip(f"sentence not in the {language} fixture: {text!r}")
        return parsed

    return lookup


@pytest.fixture(scope="session")
def frame_for(
    sentence_for: Callable[..., ParsedSentence], builder: PhraseFrameBuilder
) -> Callable[..., UniversalPhraseFrame]:
    """Build the Universal Phrase Frame for a fixture sentence."""

    def build(text: str, language: str = "en", **kwargs) -> UniversalPhraseFrame:
        return builder.build(sentence_for(text, language), **kwargs)

    return build


@pytest.fixture(scope="session")
def pipeline(config: Config):
    """The real pipeline. Skips if the parser or its models are unavailable."""
    from splm.linguistic.factory import build_parser
    from splm.linguistic.parser import ParserUnavailable
    from splm.pipeline import SPLMPipeline

    try:
        parser = build_parser(config)
    except ParserUnavailable as exc:
        pytest.skip(str(exc))

    if not getattr(parser, "supports", lambda _: True)("en"):
        pytest.skip("no English parser model; run python scripts/download_resources.py")

    return SPLMPipeline(config, parser=parser)


def texts(frame: UniversalPhraseFrame, slot: str) -> list[str]:
    """Surface texts in a slot - the assertion helper most tests want."""
    return [element.text for element in frame.slot(slot)]


def roles(frame: UniversalPhraseFrame, slot: str) -> list[str]:
    return [element.semantic_role for element in frame.slot(slot)]
