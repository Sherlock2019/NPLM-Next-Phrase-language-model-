"""Meaning objects -> Universal Phrase DNA frames, without going through prose.

Downstream consumers (ACM) already read :class:`UniversalPhraseFrame`. Events
from images and video, and proposed actions, are converted straight into that
schema, keeping the entity id, status and evidence of every filler in
``FrameElement.annotations``. Nothing is rendered to text and parsed back.

Roles the meaning object does not have are not added: a push seen on video
gets no PURPOSE element, so the frame's goal slot stays empty.
"""

from __future__ import annotations

from splm.meaning.schema import MeaningEvent, ProposedAction, RoleFiller, SceneState, Status
from splm.phrase.schema import FrameElement, Predicate, PredicateType, Tense, UniversalPhraseFrame

#: MLM role -> frame slot (language_packs/universal/semantic_roles.yaml).
ROLE_SLOTS: dict[str, str] = {
    "AGENT": "subject",
    "EXPERIENCER": "subject",
    "PATIENT": "objects",
    "THEME": "objects",
    "OBJECT": "objects",
    "RECIPIENT": "recipients",
    "BENEFICIARY": "recipients",
    "PARTICIPANT": "participants",
    "DESTINATION": "destination",
    "SOURCE": "source",
    "LOCATION": "location",
    "TIME": "time",
    "MANNER": "manner",
    "INSTRUMENT": "instrument",
    "CAUSE": "cause",
    "PURPOSE": "goal",
    "CONDITION": "condition",
}
#: Predicates that describe something happening to its subject rather than an act.
EVENT_PREDICATES = frozenset({"fall", "slide", "tip", "roll"})
ANIMATE_CLASSES = frozenset({"person", "pusher", "robot", "hand"})
PLACE_CLASSES = frozenset({"table", "floor", "shelf", "counter", "desk"})


def _element(role: str, filler: RoleFiller, scene: SceneState | None, evidence: list[str]) -> FrameElement:
    entity = None
    if scene is not None and filler.entity_id:
        entity = next((e for e in scene.entities if e.id == filler.entity_id), None)
    cls = entity.cls if entity else None
    features: dict = {}
    entity_type = None
    if filler.entity_id == "self":
        features = {"person": 1, "pronoun_type": "prs"}
    elif cls in ANIMATE_CLASSES:
        features = {"animacy": "animate"}
    if cls in PLACE_CLASSES:
        entity_type = "FACILITY"
    annotations = {"status": filler.status.value, "evidence": evidence}
    if filler.entity_id:
        annotations["entity_id"] = filler.entity_id
    if entity is not None:
        annotations["class"] = entity.cls
    return FrameElement(
        text=filler.text,
        head_lemma=(cls or filler.text.split()[-1]).lower(),
        semantic_role=role,
        entity_type=entity_type,
        features=features,
        annotations=annotations,
    )


def _fill(frame: UniversalPhraseFrame, roles: dict[str, list[RoleFiller]], scene, evidence) -> None:
    for role, fillers in roles.items():
        for filler in fillers:
            frame.add(ROLE_SLOTS[role], _element(role, filler, scene, evidence))


def event_to_frame(event: MeaningEvent, scene: SceneState | None = None, language: str = "en") -> UniversalPhraseFrame:
    """An observed or hypothesised event as a past-tense MLM frame."""
    if event.frame is not None:
        return event.frame
    evidence = [f"{e.source_type.value}:{e.uri}@{e.time_end}" for e in event.evidence]
    frame = UniversalPhraseFrame(
        language=language,
        text=f"[{event.status.value} event {event.id}: {event.predicate}]",
        predicate=Predicate(
            type=PredicateType.EVENT if event.predicate in EVENT_PREDICATES else PredicateType.ACTION,
            lemma=event.predicate,
            text=event.predicate,
        ),
        tense=Tense(event.tense),
        negation=event.negation,
        certainty=None,
        notes=[f"event {event.id}", f"status={event.status.value}", f"hypothesis={event.hypothesis}",
               f"causal_attribution={event.causal_attribution}"],
    )
    _fill(frame, event.roles, scene, evidence)
    return frame


def action_to_frame(action: ProposedAction, scene: SceneState | None = None, language: str = "en") -> UniversalPhraseFrame:
    """A proposed action as a future-tense frame with modality 'proposal'.

    Parameters (distance, direction) stay structured in ``notes``/annotations; the
    frame carries roles only. No purpose is added.
    """
    roles: dict[str, list[RoleFiller]] = {}
    if action.actor:
        roles["AGENT"] = [RoleFiller(entity_id=action.actor, text="I" if action.actor == "self" else action.actor, status=Status.ASSUMED)]
    roles["PATIENT"] = [RoleFiller(entity_id=action.target, text=action.target, status=Status.ASSUMED)]
    frame = UniversalPhraseFrame(
        language=language,
        text=f"[proposed action {action.id}: {action.predicate} {action.target}]",
        predicate=Predicate(type=PredicateType.ACTION, lemma=action.predicate, text=action.predicate),
        tense=Tense.FUTURE,
        modality="proposal",
        notes=[f"proposed action {action.id}"]
        + [f"{name}={q.value}{q.unit}" for name, q in action.parameters.items()],
    )
    _fill(frame, roles, scene, [f"proposal:{action.id}"])
    if action.destination is not None:
        point = action.destination
        support = None
        if scene is not None:
            support = next((e.id for e in scene.entities if e.geometry.extent is not None
                            and e.geometry.extent.frame == point.frame and e.geometry.extent.contains(point)), None)
        where = f"x={point.x:.2f}, y={point.y:.2f} {point.unit}" + (f" on {support}" if support else "")
        frame.add("destination", FrameElement(
            text=f"the point ({where})", head_lemma=f"point_{point.x:.2f}_{point.y:.2f}", semantic_role="DESTINATION",
            entity_type="LOCATION",
            annotations={"status": Status.ASSUMED.value, "point": point.model_dump(mode="json"),
                         "evidence": [f"proposal:{action.id}"]},
        ))
    return frame
