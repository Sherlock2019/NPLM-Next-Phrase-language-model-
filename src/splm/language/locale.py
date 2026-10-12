"""Locale handling, kept strictly separate from language identity.

Spec section 12 is explicit: *do not equate language and country*. ``fr`` is a
language; ``fr-CA`` is a language used in a region; ``vi-Hani`` would be a script
variant. SPLM stores the language on the frame and keeps region, script and
dialect as independent, optional annotations that never affect the universal
semantic layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# language [-script] [-region] [-variant...]
_TAG = re.compile(
    r"^(?P<language>[A-Za-z]{2,3})"
    r"(?:[-_](?P<script>[A-Za-z]{4}))?"
    r"(?:[-_](?P<region>[A-Za-z]{2}|\d{3}))?"
    r"(?:[-_](?P<variant>[A-Za-z0-9]{1,8}))?$"
)

#: Regions commonly associated with a language. Informational only - never used
#: to infer a language from a region, or a region from a language.
KNOWN_REGIONS: dict[str, tuple[str, ...]] = {
    "en": ("US", "GB", "AU", "CA", "IE", "NZ", "IN", "ZA"),
    "fr": ("FR", "CA", "BE", "CH", "SN", "CI"),
    "vi": ("VN",),
}


@dataclass(frozen=True)
class Locale:
    """A language tag decomposed into independent dimensions."""

    language: str
    region: str | None = None
    script: str | None = None
    variant: str | None = None

    @classmethod
    def parse(cls, tag: str | None) -> "Locale | None":
        """Parse ``en``, ``en-GB``, ``vi_VN``, ``zh-Hant-TW`` ... or return None."""
        if not tag:
            return None
        match = _TAG.match(tag.strip())
        if not match:
            return None
        parts = match.groupdict()
        return cls(
            language=parts["language"].lower(),
            region=(parts["region"] or None) and parts["region"].upper(),
            script=(parts["script"] or None) and parts["script"].title(),
            variant=(parts["variant"] or None) and parts["variant"].lower(),
        )

    def __str__(self) -> str:
        return "-".join(
            part
            for part in (self.language, self.script, self.region, self.variant)
            if part
        )

    @property
    def tag(self) -> str:
        return str(self)

    def is_plausible(self) -> bool:
        """Whether the region is one usually seen with this language.

        A False result is *not* an error: French is spoken everywhere. This exists
        only so callers can log an unusual pairing, never to override a detection.
        """
        if self.region is None:
            return True
        return self.region in KNOWN_REGIONS.get(self.language, ())
