"""Logging setup, driven by ``config/app.yaml`` and ``SPLM_LOG_LEVEL``."""

from __future__ import annotations

import logging
import os
from typing import Any

DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"

#: Third-party loggers that are noisy at INFO.
QUIET_LOGGERS = ("stanza", "torch", "transformers", "urllib3", "filelock", "httpx")


def setup_logging(config: Any | None = None, level: str | None = None) -> None:
    """Configure root logging once, idempotently."""
    if config is None:
        try:
            from splm.config import get_config

            config = get_config()
        except Exception:  # pragma: no cover - logging must never block startup
            config = None

    resolved = (
        level
        or os.environ.get("SPLM_LOG_LEVEL")
        or (config.get("app.logging.level") if config else None)
        or "INFO"
    )
    fmt = (config.get("app.logging.format") if config else None) or DEFAULT_FORMAT

    logging.basicConfig(level=getattr(logging, str(resolved).upper(), logging.INFO), format=fmt)

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
