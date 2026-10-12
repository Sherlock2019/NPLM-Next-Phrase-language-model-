"""Parser construction, kept apart from both the interface and the backends."""

from __future__ import annotations

import logging
from typing import Any

from splm.linguistic.parser import LinguisticParser, ParserUnavailable

logger = logging.getLogger(__name__)


def build_parser(config: Any | None = None, backend: str | None = None) -> LinguisticParser:
    """Instantiate the configured :class:`LinguisticParser`.

    Backends are imported lazily so that importing ``splm`` never pulls in a heavy
    NLP stack, and so an unused backend's absence is never an error.
    """
    from splm.config import get_config

    config = config or get_config()
    backend = (backend or config.get("app.parser.backend", "stanza") or "").lower()

    if backend in {"stanza", ""}:
        from splm.linguistic.stanza_parser import StanzaParser

        return StanzaParser.from_config(config)

    if backend in {"none", "null"}:
        raise ParserUnavailable(
            "parser.backend is set to none; set it to 'stanza' in config/app.yaml"
        )

    raise ParserUnavailable(f"unknown parser backend {backend!r}")
