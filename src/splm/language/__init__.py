"""Language identification, locales and language packs."""

from __future__ import annotations

from splm.language.detector import LanguageDetection, LanguageDetector
from splm.language.locale import Locale
from splm.language.packs import LanguagePack, LanguagePackRegistry, UniversalPack, get_registry

__all__ = [
    "LanguageDetection",
    "LanguageDetector",
    "Locale",
    "LanguagePack",
    "LanguagePackRegistry",
    "UniversalPack",
    "get_registry",
]
