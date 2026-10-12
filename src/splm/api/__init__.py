"""HTTP API for the SPLM dashboard."""

from __future__ import annotations

__all__ = ["create_app"]


def __getattr__(name: str):  # pragma: no cover - lazy re-export
    # Imported lazily so that `import splm.api` does not require FastAPI.
    if name == "create_app":
        from splm.api.main import create_app

        return create_app
    raise AttributeError(name)
