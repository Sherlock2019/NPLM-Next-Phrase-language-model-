"""Text -> MLM meaning, through the existing parser. Nothing about the text path changes.

Each parsed clause keeps its full :class:`UniversalPhraseFrame`. A clause in the
past or present becomes a stated event; a future or intention clause ("I plan to
push...", "I will push...") is a *stated plan*, kept as a goal-bearing frame,
never as an observed event.

Grounding a mention to a scene entity ("the blue cup" -> blue_cup_01) only
happens when exactly one entity matches; an ambiguous mention stays unresolved.
"""

from __future__ import annotations

from typing import Any

from splm.meaning.schema import (
    BackendInfo,
    EvidenceReference,
    Goal,
    MeaningDocument,
    MeaningEvent,
    RoleFiller,
    SceneState,
    SourceType,
    Status,
)
from splm.phrase.schema import FrameElement, UniversalPhraseFrame

PLAN_MODALITIES = {"intention", "plan", "proposal", "desire"}
FRAME_ROLE_SLOTS = ("subject", "objects", "recipients", "participants", "location", "destination",
                    "source", "time", "manner", "instrument", "cause", "goal", "condition")


def ground(element: FrameElement, scene: SceneState | None) -> str | None:
    """The one scene entity a mention can only mean, or None."""
    if scene is None:
        return None
    words = {w.lower().strip(".,") for w in element.text.split()}
    head = (element.head_lemma or element.text.split()[-1]).lower()
    candidates = [
        e for e in scene.entities
        if e.cls == head and all(str(v).lower() in words for v in e.attributes.values() if isinstance(v, str))
    ]
    return candidates[0].id if len(candidates) == 1 else None


class TextAdapter:
    def __init__(self, pipeline: Any | None = None) -> None:
        self._pipeline = pipeline
        self.info = BackendInfo(name="splm-pipeline", kind="parser", live=True)

    @property
    def pipeline(self):
        if self._pipeline is None:
            from splm.pipeline import SPLMPipeline

            self._pipeline = SPLMPipeline()
        return self._pipeline

    def analyze(self, text: str, *, language: str | None = None, scene: SceneState | None = None) -> MeaningDocument:
        analysis = self.pipeline.analyze(text, language=language, detect_style=False)
        return self.from_frames(analysis.frames, text=text, scene=scene, info=self.info)

    def from_frames(
        self,
        frames: list[UniversalPhraseFrame],
        *,
        text: str,
        scene: SceneState | None = None,
        info: BackendInfo | None = None,
    ) -> MeaningDocument:
        info = info or self.info
        source = EvidenceReference(source_type=SourceType.TEXT, uri="inline-text", text_span=text, backend=info)
        doc = MeaningDocument(source=source, states=[scene] if scene is not None else [])
        for number, frame in enumerate(frames, start=1):
            if frame.predicate is None:
                continue
            evidence = [source.model_copy(update={"text_span": frame.text})]
            for nested in frame.walk():  # ground mentions in nested frames too ("plan to push the blue cup")
                if nested is frame:
                    continue
                for _, element in nested.elements():
                    if element.frame is None and "entity_id" not in element.annotations:
                        grounded = ground(element, scene)
                        if grounded:
                            element.annotations["entity_id"] = grounded
            roles: dict[str, list[RoleFiller]] = {}
            for slot in FRAME_ROLE_SLOTS:
                for element in frame.slot(slot):
                    if element.frame is not None:
                        continue
                    entity_id = "self" if element.features.get("person") == 1 else ground(element, scene)
                    if entity_id:
                        element.annotations.setdefault("entity_id", entity_id)
                    roles.setdefault(element.semantic_role, []).append(
                        RoleFiller(entity_id=entity_id, text=element.text, status=Status.OBSERVED)
                    )
            is_plan = (frame.modality in PLAN_MODALITIES) or frame.tense is not None and frame.tense.value == "future"
            if is_plan or any(e.frame is not None for e in frame.goal):
                owner = roles.get("AGENT", roles.get("EXPERIENCER", [RoleFiller(text="?")]))[0]
                doc.goals.append(Goal(owner=owner.entity_id or owner.text, text=frame.text, source="stated",
                                      frame=frame, evidence=evidence))
                continue
            doc.events.append(MeaningEvent(
                id=f"tx_{number:02d}", predicate=frame.predicate.lemma, roles=roles,
                tense="present" if frame.tense and frame.tense.value == "present" else "past",
                negation=frame.negation, conditions=[c.text for c in frame.condition],
                status=Status.OBSERVED, causal_attribution="stated" if frame.cause else "not_applicable",
                evidence=evidence, frame=frame,
            ))
        return doc
