"""Universal Phrase DNA (spec sections 2, 9, 10, 11, 30-32).

The language-independent representation of what a sentence means:

    WHO
    ├── IS IN WHAT STATE?
    └── DOES WHAT?
          ├── WHAT / TO WHOM?   WHERE?   WHEN?   HOW?
          ├── USING WHAT?       WITH WHOM?
          └── WHY?  FOR WHAT GOAL?  UNDER WHAT CONDITIONS?

Two properties matter more than any field list:

1. It is **recursive**. Complex language is not flattened - a conditional, a
   purpose clause or a reported thought becomes a nested frame (section 11).
2. It stores **semantic relationships, not word order**. Nothing here records
   that English puts the subject first (sections 30-32). The same frame must be
   reachable from English, French and Vietnamese.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterator

from pydantic import BaseModel, Field


class PredicateType(str, Enum):
    """The seven predicate types of spec section 10."""

    ACTION = "ACTION"
    STATE = "STATE"
    EVENT = "EVENT"
    RELATIONSHIP = "RELATIONSHIP"
    EXISTENCE = "EXISTENCE"
    POSSESSION = "POSSESSION"
    CHANGE = "CHANGE"


class Tense(str, Enum):
    PAST = "past"
    PRESENT = "present"
    FUTURE = "future"


class Aspect(str, Enum):
    SIMPLE = "simple"
    PROGRESSIVE = "progressive"
    PERFECT = "perfect"
    PERFECT_PROGRESSIVE = "perfect_progressive"
    HABITUAL = "habitual"


class Voice(str, Enum):
    ACTIVE = "active"
    PASSIVE = "passive"
    MIDDLE = "middle"


#: Frame fields that hold lists of elements, in presentation order.
ELEMENT_SLOTS: tuple[str, ...] = (
    "subject",
    "objects",
    "recipients",
    "participants",
    "location",
    "destination",
    "source",
    "time",
    "manner",
    "instrument",
    "cause",
    "goal",
    "condition",
)

#: All slots including the predicate, in the order the CLI and UI render them.
ALL_SLOTS: tuple[str, ...] = (
    "subject",
    "predicate",
    "objects",
    "recipients",
    "participants",
    "location",
    "destination",
    "source",
    "time",
    "manner",
    "instrument",
    "cause",
    "goal",
    "condition",
)


class RoleAlternative(BaseModel):
    """A role the engine considered but did not choose."""

    role: str
    probability: float = Field(ge=0.0, le=1.0)


class Predicate(BaseModel):
    """What is happening, or what state holds."""

    type: PredicateType
    lemma: str
    text: str = ""
    sense: str | None = Field(
        default=None,
        description=(
            "Coarse language-independent reading (located, identity, property, "
            "possession). Lets frames from different languages be compared even "
            "when their predicate lemmas differ."
        ),
    )
    token_index: int | None = None
    token_indices: list[int] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    def __str__(self) -> str:
        return f"{self.type.value}:{self.lemma}" + (f"/{self.sense}" if self.sense else "")


class FrameElement(BaseModel):
    """One filled participant or circumstance.

    ``frame`` makes the structure recursive: a purpose clause is an element whose
    own meaning is a complete nested frame.
    """

    text: str
    head_lemma: str = ""
    semantic_role: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    entity_type: str | None = None
    token_indices: list[int] = Field(default_factory=list)
    features: dict[str, Any] = Field(
        default_factory=dict, description="Normalised morphology of the head word"
    )
    annotations: dict[str, Any] = Field(
        default_factory=dict, description="Structured extras, e.g. {'transport': 'train'}"
    )
    alternatives: list[RoleAlternative] = Field(
        default_factory=list, description="Runner-up roles, kept for debugging and re-ranking"
    )
    deprel: str | None = None
    frame: "UniversalPhraseFrame | None" = None

    @property
    def is_ambiguous(self) -> bool:
        """Whether the runner-up role was close enough to matter."""
        if not self.alternatives:
            return False
        return (self.confidence - self.alternatives[0].probability) < 0.25

    def __str__(self) -> str:
        return f"{self.semantic_role}({self.text})"


class UniversalPhraseFrame(BaseModel):
    """The Universal Phrase DNA of one clause."""

    # -- provenance --------------------------------------------------------
    language: str
    locale: str | None = None
    style: str | None = None
    text: str = ""
    token_indices: list[int] = Field(default_factory=list)

    # -- core structure ----------------------------------------------------
    subject: list[FrameElement] = Field(default_factory=list)
    predicate: Predicate | None = None

    objects: list[FrameElement] = Field(default_factory=list)
    recipients: list[FrameElement] = Field(default_factory=list)
    participants: list[FrameElement] = Field(default_factory=list)

    location: list[FrameElement] = Field(default_factory=list)
    # destination/source are spec section 19's WHERE TO / FROM WHERE; they are kept
    # apart from `location` because motion endpoints are not settings.
    destination: list[FrameElement] = Field(default_factory=list)
    source: list[FrameElement] = Field(default_factory=list)

    time: list[FrameElement] = Field(default_factory=list)
    manner: list[FrameElement] = Field(default_factory=list)
    instrument: list[FrameElement] = Field(default_factory=list)

    cause: list[FrameElement] = Field(default_factory=list)
    goal: list[FrameElement] = Field(default_factory=list)
    condition: list[FrameElement] = Field(default_factory=list)

    # -- grammatical meaning ----------------------------------------------
    tense: Tense | None = None
    aspect: Aspect | None = None
    modality: str | None = None
    voice: Voice | None = None

    negation: bool = False
    certainty: float | None = Field(default=None, ge=0.0, le=1.0)

    intent: str | None = None
    emotion: str | None = None

    # -- bookkeeping -------------------------------------------------------
    unresolved_slots: list[str] = Field(
        default_factory=list,
        description="Slots this predicate plausibly takes but the text has not filled",
    )
    relation_to_parent: str | None = Field(
        default=None, description="Role this frame plays inside its parent (PURPOSE, CONDITION...)"
    )
    dangling_marker: str | None = Field(
        default=None,
        description=(
            "A trailing adposition or subordinator with nothing after it yet, as in "
            "'John will meet Sarah in'. It is evidence about what comes next, not a "
            "filled slot, so it is recorded here rather than as an element."
        ),
    )
    children: list["UniversalPhraseFrame"] = Field(
        default_factory=list, description="Nested frames not attached to a specific slot"
    )
    notes: list[str] = Field(default_factory=list)

    # -- slot access -------------------------------------------------------

    def slot(self, name: str) -> list[FrameElement]:
        """Elements in a named slot; empty list for the predicate slot."""
        value = getattr(self, name, None)
        return value if isinstance(value, list) else []

    def add(self, slot: str, element: FrameElement) -> None:
        """Append an element to a slot, creating nothing that is not in the schema."""
        if slot not in ELEMENT_SLOTS:
            raise KeyError(f"{slot!r} is not an element slot; known: {ELEMENT_SLOTS}")
        getattr(self, slot).append(element)

    def filled_slots(self) -> list[str]:
        """Slots that have content, in presentation order."""
        filled = [slot for slot in ELEMENT_SLOTS if self.slot(slot)]
        if self.predicate is not None:
            filled.insert(min(1, len(filled)), "predicate")
        return filled

    def is_filled(self, slot: str) -> bool:
        if slot == "predicate":
            return self.predicate is not None
        return bool(self.slot(slot))

    def empty_slots(self) -> list[str]:
        return [slot for slot in ALL_SLOTS if not self.is_filled(slot)]

    def elements(self) -> Iterator[tuple[str, FrameElement]]:
        """Every element in this frame, paired with its slot name."""
        for slot in ELEMENT_SLOTS:
            for element in self.slot(slot):
                yield slot, element

    def all_elements(self) -> list[FrameElement]:
        return [element for _, element in self.elements()]

    def find_role(self, role: str) -> list[FrameElement]:
        """Every element carrying a given semantic role, at this level."""
        return [element for _, element in self.elements() if element.semantic_role == role]

    # -- recursion ---------------------------------------------------------

    def subframes(self) -> Iterator["UniversalPhraseFrame"]:
        """Directly nested frames, whether slot-attached or free-standing."""
        for _, element in self.elements():
            if element.frame is not None:
                yield element.frame
        yield from self.children

    def walk(self) -> Iterator["UniversalPhraseFrame"]:
        """This frame and every frame beneath it, depth first."""
        yield self
        for child in self.subframes():
            yield from child.walk()

    @property
    def depth(self) -> int:
        """Nesting depth; 1 for a simple clause."""
        nested = list(self.subframes())
        return 1 if not nested else 1 + max(child.depth for child in nested)

    # -- comparison --------------------------------------------------------

    def structural_signature(self) -> dict[str, Any]:
        """A language-independent fingerprint of the frame.

        Used to measure cross-language semantic consistency (spec section 38):
        English, French and Vietnamese renderings of the same meaning should give
        the same signature.

        Deliberately excludes lemmas, which are language-specific. It keeps
        predicate *type* and *sense*, grammatical meaning, which slots are filled,
        and named entities - proper nouns survive translation, so they are the one
        piece of lexical content that is safe to compare. Comparing content words
        properly needs a cross-lingual concept inventory, which the POC does not
        have; that limitation is recorded in the README rather than papered over.
        """
        return {
            "predicate_type": self.predicate.type.value if self.predicate else None,
            "predicate_sense": self.predicate.sense if self.predicate else None,
            "slots": sorted(
                slot for slot in ELEMENT_SLOTS if self.slot(slot)
            ),
            "roles": sorted(
                {element.semantic_role for _, element in self.elements()}
            ),
            "entities": sorted(
                {
                    element.text
                    for _, element in self.elements()
                    if element.entity_type in {"PERSON", "LOCATION", "ORG", "FACILITY"}
                }
            ),
            "tense": self.tense.value if self.tense else None,
            "aspect": self.aspect.value if self.aspect else None,
            "modality": self.modality,
            "negation": self.negation,
            "depth": self.depth,
            "children": [child.structural_signature() for child in self.subframes()],
        }

    def agreement_with(self, other: "UniversalPhraseFrame") -> float:
        """Fraction of signature facts shared with another frame, in ``[0, 1]``."""
        mine, theirs = self.structural_signature(), other.structural_signature()
        keys = [
            "predicate_type",
            "predicate_sense",
            "tense",
            "aspect",
            "modality",
            "negation",
            "depth",
        ]
        matches = sum(1 for key in keys if mine[key] == theirs[key])
        total = len(keys)

        for key in ("slots", "roles", "entities"):
            left, right = set(mine[key]), set(theirs[key])
            union = left | right
            matches += (len(left & right) / len(union)) if union else 1.0
            total += 1

        return round(matches / total, 4)

    # -- rendering ---------------------------------------------------------

    def to_compact_dict(self) -> dict[str, Any]:
        """A small dict with only what was actually found - good for logs and tests."""
        data: dict[str, Any] = {"language": self.language}
        if self.style:
            data["style"] = self.style
        if self.predicate:
            predicate: dict[str, Any] = {
                "type": self.predicate.type.value,
                "lemma": self.predicate.lemma,
            }
            if self.predicate.sense:
                predicate["sense"] = self.predicate.sense
            data["predicate"] = predicate

        for slot in ELEMENT_SLOTS:
            elements = self.slot(slot)
            if not elements:
                continue
            data[slot] = [
                (
                    {"text": e.text, "role": e.semantic_role, "frame": e.frame.to_compact_dict()}
                    if e.frame is not None
                    else {"text": e.text, "role": e.semantic_role}
                )
                for e in elements
            ]

        for key in ("tense", "aspect", "modality", "voice"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value.value if isinstance(value, Enum) else value

        data["negation"] = self.negation
        if self.certainty is not None:
            data["certainty"] = self.certainty
        if self.unresolved_slots:
            data["unresolved_slots"] = self.unresolved_slots
        if self.children:
            data["children"] = [child.to_compact_dict() for child in self.children]
        return data

    def __str__(self) -> str:
        parts = [f"{self.predicate}" if self.predicate else "?"]
        for slot, element in self.elements():
            parts.append(f"{slot}={element.text!r}")
        return "Frame(" + ", ".join(parts) + ")"


# Resolve the forward references used for recursion.
FrameElement.model_rebuild()
UniversalPhraseFrame.model_rebuild()
