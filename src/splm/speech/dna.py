"""Sort an utterance into Phrase DNA categories, and ask about what is missing.

The speech lab's main output. After the user speaks, every content word or phrase
of the transcript is placed in one of eight questions:

    WHO · ACTION / STATUS · ON WHAT · FOR WHAT · WHERE · WHEN · WITH WHOM · HOW

This is a *view* over :class:`UniversalPhraseFrame` - it adds no parsing of its
own, so it can never disagree with the frame the rest of the system uses. Words the
frame did not place anywhere are listed as ``unsorted`` rather than forced into a
category: a gap must look like a gap.

The slot -> category mapping (one place, so the UI and the tests share it)::

    WHO            subject
    ACTION/STATUS  predicate (ACTION, EVENT, CHANGE = action; the rest = status)
    ON WHAT        objects, recipients
    FOR WHAT       goal, cause
    WHERE          location, destination, source
    WHEN           time
    WITH WHOM      participants
    HOW            manner, instrument
    (CONDITION     condition - shown only when filled)
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from splm.phrase.schema import PredicateType, UniversalPhraseFrame

#: (key, label, frame slots) in display order.
DNA_CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("who", "WHO", ("subject",)),
    ("action", "ACTION / STATUS", ()),
    ("on_what", "ON WHAT", ("objects", "recipients")),
    ("for_what", "FOR WHAT", ("goal", "cause")),
    ("where", "WHERE", ("location", "destination", "source")),
    ("when", "WHEN", ("time",)),
    ("with_whom", "WITH WHOM", ("participants",)),
    ("how", "HOW", ("manner", "instrument")),
    ("condition", "UNDER WHAT CONDITION", ("condition",)),
)

_ACTION_TYPES = {PredicateType.ACTION, PredicateType.EVENT, PredicateType.CHANGE}
#: Parts of speech that carry no content of their own; never reported as unsorted.
_FUNCTION_POS = {"PUNCT", "DET", "ADP", "AUX", "CCONJ", "SCONJ", "PART", "SYM", "INTJ"}


class DnaItem(BaseModel):
    text: str
    slot: str
    role: str | None = None
    confidence: float = 1.0
    entity_type: str | None = None


class DnaCategory(BaseModel):
    key: str
    label: str
    items: list[DnaItem] = Field(default_factory=list)
    #: The predicate expects this slot but the utterance did not fill it.
    missing: bool = False


class DnaSort(BaseModel):
    """One utterance sorted into Phrase DNA categories."""

    text: str
    language: str
    categories: list[DnaCategory] = Field(default_factory=list)
    predicate_kind: str | None = Field(default=None, description="action | status")
    tense: str | None = None
    modality: str | None = None
    negation: bool = False
    intent: str | None = None
    unsorted: list[str] = Field(default_factory=list)
    clauses: list["DnaSort"] = Field(default_factory=list)

    def category(self, key: str) -> DnaCategory | None:
        return next((c for c in self.categories if c.key == key), None)

    def texts(self, key: str) -> list[str]:
        found = self.category(key)
        return [item.text for item in found.items] if found else []

    @property
    def filled_keys(self) -> list[str]:
        return [c.key for c in self.categories if c.items]

    @property
    def completeness(self) -> float:
        """Share of the eight core categories that are filled (condition excluded)."""
        core = [c for c in self.categories if c.key != "condition"]
        return round(sum(1 for c in core if c.items) / len(core), 4) if core else 0.0

    def as_slots(self) -> dict[str, list[str]]:
        """Category -> normalised texts; what semantic-slot accuracy compares."""
        return {c.key: [item.text.lower().strip() for item in c.items] for c in self.categories if c.items}


def sort_frame(
    frame: UniversalPhraseFrame | None,
    sentence: Any | None = None,
    *,
    text: str | None = None,
    language: str | None = None,
    _depth: int = 0,
) -> DnaSort:
    """Sort a frame (and its sentence's leftover words) into DNA categories."""
    if frame is None:
        words = (text or "").split()
        return DnaSort(text=text or "", language=language or "", unsorted=words,
                       categories=[DnaCategory(key=k, label=l) for k, l, _ in DNA_CATEGORIES])

    unresolved = set(frame.unresolved_slots)
    categories: list[DnaCategory] = []
    for key, label, slots in DNA_CATEGORIES:
        category = DnaCategory(key=key, label=label)
        if key == "action":
            if frame.predicate is not None:
                predicate = frame.predicate
                category.items.append(DnaItem(
                    text=predicate.text or predicate.lemma,
                    slot="predicate",
                    role=predicate.type.value,
                    confidence=predicate.confidence,
                ))
            else:
                category.missing = True
        else:
            for slot in slots:
                for element in frame.slot(slot):
                    category.items.append(DnaItem(
                        text=element.text,
                        slot=slot,
                        role=element.semantic_role,
                        confidence=element.confidence,
                        entity_type=element.entity_type,
                    ))
            category.missing = not category.items and any(slot in unresolved for slot in slots)
        categories.append(category)

    kind = None
    if frame.predicate is not None:
        kind = "action" if frame.predicate.type in _ACTION_TYPES else "status"

    result = DnaSort(
        text=frame.text or text or "",
        language=frame.language,
        categories=categories,
        predicate_kind=kind,
        tense=frame.tense.value if frame.tense else None,
        modality=frame.modality,
        negation=frame.negation,
        intent=frame.intent,
    )

    if sentence is not None and _depth == 0:
        covered: set[int] = set()
        for sub in frame.walk():
            if sub.predicate is not None:
                covered.update(sub.predicate.token_indices or [])
                if sub.predicate.token_index is not None:
                    covered.add(sub.predicate.token_index)
            for _, element in sub.elements():
                covered.update(element.token_indices)
        result.unsorted = [
            token.text for token in getattr(sentence, "tokens", [])
            if token.index not in covered and token.upos not in _FUNCTION_POS
        ]

    if _depth < 2:
        result.clauses = [
            sort_frame(child, None, language=frame.language, _depth=_depth + 1)
            for child in frame.subframes()
        ]
    return result


DnaSort.model_rebuild()


# -- dialogue policy ----------------------------------------------------------

_CLOCK = re.compile(r"\d|\b(?:noon|midnight|o'clock|am|pm|heures?|giờ|h\d)\b", re.IGNORECASE)

#: Missing-information questions, per language. {action} is the verb phrase.
_QUESTIONS: dict[str, dict[str, str]] = {
    "en": {
        "clock": "What time would you like to {action}?",
        "when": "When would you like to {action}?",
        "where": "Where would you like to {action}?",
        "with_whom": "Who would you like to {action} with?",
        "on_what": "What would you like to {action}?",
    },
    "fr": {
        "clock": "À quelle heure voulez-vous {action} ?",
        "when": "Quand voulez-vous {action} ?",
        "where": "Où voulez-vous {action} ?",
        "with_whom": "Avec qui voulez-vous {action} ?",
        "on_what": "Que voulez-vous {action} ?",
    },
    "vi": {
        "clock": "Bạn muốn {action} lúc mấy giờ?",
        "when": "Bạn muốn {action} khi nào?",
        "where": "Bạn muốn {action} ở đâu?",
        "with_whom": "Bạn muốn {action} với ai?",
        "on_what": "Bạn muốn {action} gì?",
    },
}

_WITH = {"en": "with", "fr": "avec", "vi": "với"}

#: Verbs that schedule something: for these a day without a clock time is incomplete.
_SCHEDULING = {
    "book", "schedule", "meet", "call", "reserve", "arrange", "plan", "set",
    "réserver", "planifier", "rencontrer", "appeler", "organiser",
    "đặt", "hẹn", "gặp", "gọi",
}


class Clarification(BaseModel):
    question: str
    missing: str = Field(description="DNA category the question asks about")
    reason: str


def clarify(sort: DnaSort) -> Clarification | None:
    """A question about the most important missing piece of a request, or None.

    Deliberately narrow and rule-based: it only fires for commands (an imperative
    with an action predicate) and only asks about WHEN / WHERE / WITH WHOM / ON WHAT.
    It is a demonstration of a dialogue policy driven by Phrase DNA, not a general
    dialogue manager.
    """
    if sort.intent != "command" or sort.predicate_kind != "action":
        return None
    language = sort.language if sort.language in _QUESTIONS else "en"
    templates = _QUESTIONS[language]
    action_items = sort.texts("action")
    if not action_items:
        return None
    verb = action_items[0].lower()  # sentence-initial imperatives are capitalised
    lemma = verb

    objects = sort.texts("on_what")
    participants = sort.texts("with_whom")
    phrase = " ".join([verb, *objects[:1]])
    if participants and participants[0] not in phrase:
        phrase += f" {_WITH[language]} {participants[0]}"

    when = sort.category("when")
    if lemma in _SCHEDULING:
        if when is not None and not when.items:
            return Clarification(question=templates["when"].format(action=phrase), missing="when",
                                 reason="scheduling request without a time")
        if when is not None and when.items and not any(_CLOCK.search(t) for t in sort.texts("when")):
            return Clarification(question=templates["clock"].format(action=phrase), missing="when",
                                 reason=f"day given ({', '.join(sort.texts('when'))}) but no clock time")

    for key in ("on_what", "with_whom", "where", "when"):
        category = sort.category(key)
        if category is not None and category.missing:
            return Clarification(question=templates[key].format(action=phrase), missing=key,
                                 reason=f"the predicate expects {category.label} and it is not filled")
    return None
