"""Configuration loading for SPLM.

Every tunable value - model id, scoring weight, ablation switch, file path -
lives in ``config/*.yaml`` and is read through this module. Nothing in the
package may hard-code a model, a weight, or a language (spec sections 6, 23, 52).

Environment variables override the files, so experiments can be scripted::

    SPLM_MODEL_ID=Qwen/Qwen3-4B-Base python -m splm.cli predict "..."
"""

from __future__ import annotations

import copy
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_FILES = {
    "app": "app.yaml",
    "model": "model.yaml",
    "scoring": "scoring.yaml",
    "data_sources": "data_sources.yaml",
}

#: Environment variable -> dotted path inside the merged configuration.
ENV_OVERRIDES = {
    "SPLM_MODEL_ID": "model.model.model_id",
    "SPLM_DEVICE": "model.model.device",
    "SPLM_DTYPE": "model.model.dtype",
    "SPLM_TOP_K": "model.model.top_k_candidates",
    "SPLM_LOG_LEVEL": "app.logging.level",
    "SPLM_STANZA_DIR": "app.paths.stanza_resources",
    "SPLM_API_HOST": "app.api.host",
    "SPLM_API_PORT": "app.api.port",
    "SPLM_PARSER_BACKEND": "app.parser.backend",
    "SPLM_SCORER_BACKEND": "scoring.backend",
    "SPLM_SLOT_BACKEND": "app.slot_predictor.backend",
    "SPLM_LEXICON_AUTO_DOWNLOAD": "app.lexicon.auto_download",
}


def find_project_root(start: Path | None = None) -> Path:
    """Locate the repository root by walking up to the nearest ``pyproject.toml``."""
    env_root = os.environ.get("SPLM_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    # Installed as a package with no source tree next to it: fall back to CWD.
    return Path.cwd().resolve()


def _coerce(value: str) -> Any:
    """Turn an environment string into the YAML scalar it represents."""
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", ""}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _set_dotted(tree: dict[str, Any], dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    node = tree
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value


def _get_dotted(tree: dict[str, Any], dotted: str, default: Any = None) -> Any:
    node: Any = tree
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


class Config:
    """The merged contents of ``config/`` plus resolved filesystem paths."""

    def __init__(self, data: dict[str, Any], root: Path) -> None:
        self._data = data
        self.root = root

    # -- construction ------------------------------------------------------

    @classmethod
    def load(
        cls,
        root: Path | None = None,
        *,
        overrides: dict[str, Any] | None = None,
        apply_env: bool = True,
    ) -> "Config":
        """Read every file in ``config/``, then apply env and explicit overrides."""
        root = root or find_project_root()
        config_dir = root / "config"
        data: dict[str, Any] = {}

        for key, filename in CONFIG_FILES.items():
            path = config_dir / filename
            if not path.is_file():
                logger.warning("config file missing: %s", path)
                data[key] = {}
                continue
            with path.open("r", encoding="utf-8") as handle:
                data[key] = yaml.safe_load(handle) or {}

        if apply_env:
            for env_name, dotted in ENV_OVERRIDES.items():
                raw = os.environ.get(env_name)
                if raw is not None:
                    _set_dotted(data, dotted, _coerce(raw))
                    logger.debug("config override from %s -> %s", env_name, dotted)

        if overrides:
            for dotted, value in overrides.items():
                _set_dotted(data, dotted, value)

        return cls(data, root)

    # -- access ------------------------------------------------------------

    def get(self, dotted: str, default: Any = None) -> Any:
        """Read a value by dotted path, e.g. ``"model.model.model_id"``."""
        return _get_dotted(self._data, dotted, default)

    def section(self, name: str) -> dict[str, Any]:
        """Return one whole config file's contents (``app``, ``model``, ...)."""
        return self._data.get(name, {})

    def __contains__(self, dotted: str) -> bool:
        sentinel = object()
        return _get_dotted(self._data, dotted, sentinel) is not sentinel

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    # -- derived views -----------------------------------------------------

    @property
    def model(self) -> dict[str, Any]:
        """Model settings with any selected profile already merged in."""
        model_cfg = copy.deepcopy(self.get("model.model", {}) or {})
        profile_name = os.environ.get("SPLM_PROFILE") or model_cfg.get("profile")
        if profile_name:
            profile = self.get(f"model.profiles.{profile_name}")
            if profile:
                model_cfg = _deep_merge(model_cfg, profile)
            else:
                logger.warning("unknown model profile %r; using defaults", profile_name)
        # An explicit env model id wins over any profile.
        env_model = os.environ.get("SPLM_MODEL_ID")
        if env_model:
            model_cfg["model_id"] = env_model
        return model_cfg

    def with_profile(self, profile_name: str) -> "Config":
        """Return a copy whose model section is the named profile."""
        data = copy.deepcopy(self._data)
        _set_dotted(data, "model.model.profile", profile_name)
        return Config(data, self.root)

    @property
    def scoring_weights(self) -> dict[str, float]:
        return {k: float(v) for k, v in (self.get("scoring.weights", {}) or {}).items()}

    @property
    def features(self) -> dict[str, bool]:
        """Ablation switches (spec section 39)."""
        return {k: bool(v) for k, v in (self.get("scoring.features", {}) or {}).items()}

    def with_features(self, features: dict[str, bool]) -> "Config":
        """Return a copy with some ablation switches flipped."""
        data = copy.deepcopy(self._data)
        merged = {**self.features, **features}
        _set_dotted(data, "scoring.features", merged)
        return Config(data, self.root)

    def ablation(self, name: str) -> "Config":
        """Return a copy configured for the named ablation preset."""
        preset = self.get(f"scoring.ablations.{name}")
        if preset is None:
            known = sorted((self.get("scoring.ablations", {}) or {}).keys())
            raise KeyError(f"unknown ablation {name!r}; known presets: {known}")
        return self.with_features(preset)

    @property
    def supported_languages(self) -> list[str]:
        return list(self.get("app.languages.supported", ["en"]) or ["en"])

    @property
    def default_language(self) -> str:
        return str(self.get("app.languages.default", "en"))

    # -- paths -------------------------------------------------------------

    def path(self, dotted: str, default: str | None = None) -> Path:
        """Resolve a configured path against the project root."""
        raw = self.get(dotted, default)
        if raw is None:
            raise KeyError(f"no path configured at {dotted!r}")
        candidate = Path(str(raw)).expanduser()
        return candidate if candidate.is_absolute() else (self.root / candidate)

    @property
    def language_packs_dir(self) -> Path:
        return self.path("app.paths.language_packs", "language_packs")

    @property
    def data_dir(self) -> Path:
        return self.path("app.paths.data", "data")

    @property
    def database_path(self) -> Path:
        return self.path("app.paths.database", "data/splm.db")

    @property
    def results_dir(self) -> Path:
        return self.path("app.paths.results", "results")

    @property
    def stanza_dir(self) -> Path:
        return self.path("app.paths.stanza_resources", "data/raw/stanza_resources")


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Process-wide configuration singleton.

    Tests and benchmarks that need a modified configuration should build one with
    :meth:`Config.load` or :meth:`Config.with_features` instead of mutating this.
    """
    return Config.load()
