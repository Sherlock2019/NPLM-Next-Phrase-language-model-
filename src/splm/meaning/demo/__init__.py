"""The bundled tabletop demo: one scenario, three kinds of evidence.

A blue cup sits near the right edge of a table, a red cup farther from it, and
the proposed action is to push the blue cup toward the edge.

    text   demo_text.conllu             - states a plan ("I plan to push...")
    image  tabletop_image_extraction    - shows a scene (cup near the edge)
    video  tabletop_video_extraction    - shows an event (pusher_01 pushes, cup falls)

Each one supports something different, and they are not forced to agree: the
image shows no action, the text shows no geometry, the video shows no purpose.
The extractions are hand-authored replays matched to the synthetic media
(``scripts/make_tabletop_demo.py``), not live model output.
"""

from __future__ import annotations

from pathlib import Path

from splm.meaning.adapters import FixtureReplay, ImageAdapter, TextAdapter, VideoAdapter
from splm.meaning.geometry import BoundingBox, Calibration, CoordinateFrame, Length, Point
from splm.meaning.schema import (
    BackendInfo,
    EvidenceReference,
    Geometry,
    MeaningDocument,
    Observation,
    ProposedAction,
    Quantity,
    SceneEntity,
    SceneState,
    SourceType,
    Status,
)

DEMO_DIR = Path(__file__).resolve().parent
TEXT_CONLLU = DEMO_DIR / "demo_text.conllu"
IMAGE_FIXTURE = DEMO_DIR / "tabletop_image_extraction.json"
VIDEO_FIXTURE = DEMO_DIR / "tabletop_video_extraction.json"

TABLETOP_TEXT = (
    "A blue cup is near the right edge of a table. A red cup is farther from the edge. "
    "I plan to push the blue cup toward the right edge."
)
SALE_TEXT = "I will sell my car to Sarah to pay my debt."
SALE_CONTEXT = ["Mark wants to buy my car.", "Sarah needs a car."]
VIDEO_CHECKPOINT_S = 2.0

CALIBRATION = Calibration(
    id="synthetic_topdown_01",
    homography=[[1.6, 0, -0.2], [0, 1.0, -0.2], [0, 0, 1]],
    plane="table_01 top surface",
    source="known by construction of the synthetic image (500 px per metre, origin at 100 px)",
    reference_point="centre",
)


def proposed_actions(*, actor: str | None = "self", issued_at_s: float | None = None) -> dict[str, ProposedAction | None]:
    """The three alternatives, all branching from the same initial state."""
    return {
        "none": None,
        "push_edge": ProposedAction(
            id="act_push_edge", predicate="push", actor=actor, target="blue_cup_01",
            parameters={"direction_deg": Quantity(value=0, unit="deg"), "distance": Quantity(value=0.20, unit="m")},
            preconditions=["blue_cup_01 is on table_01", "the pusher can reach blue_cup_01"],
            issued_at_s=issued_at_s,
        ),
        "move_center": ProposedAction(
            id="act_move_center", predicate="move", actor=actor, target="blue_cup_01",
            destination=Point(frame=CoordinateFrame.WORLD, unit="m", x=0.80, y=0.40, calibration_id=CALIBRATION.id),
            preconditions=["blue_cup_01 is on table_01"],
            issued_at_s=issued_at_s,
        ),
    }


ACTION_LABELS = {
    "none": "Do nothing",
    "push_edge": "Push the blue cup toward the edge (0.20 m, +x)",
    "move_center": "Move the blue cup toward the center (to x=0.80 m)",
}


def text_frames():
    """MLM frames for the demo sentences, built by MLM's real phrase builder from hand-written trees."""
    from splm.config import Config
    from splm.language.packs import LanguagePackRegistry
    from splm.linguistic.conllu import parse_conllu
    from splm.linguistic.morphology import MorphologyEngine
    from splm.linguistic.semantic_roles import SemanticRoleEngine
    from splm.phrase.builder import PhraseFrameBuilder

    config = Config.load(apply_env=False, overrides={"app.lexicon.auto_download": False})
    registry = LanguagePackRegistry(config.language_packs_dir)
    builder = PhraseFrameBuilder(registry, morphology=MorphologyEngine(registry),
                                 semantic_roles=SemanticRoleEngine(registry))
    document = parse_conllu(TEXT_CONLLU.read_text(encoding="utf-8"), "en")
    return {s.text.strip(): builder.build(s) for s in document.sentences}


def assumed_text_scene() -> SceneState:
    """Geometry for the text example. Text gives none, so every number here is ASSUMED.

    "Near the right edge" and "farther from the edge" are what the text says; the
    positions below are supplied scenario values that agree with it, labelled assumed.
    """
    supplied = EvidenceReference(
        source_type=SourceType.SUPPLIED, uri="demo:tabletop-scenario-defaults",
        backend=BackendInfo(name="scenario-defaults", kind="manual", live=False),
        extraction="positions supplied for the text example; the text states no coordinates",
    )

    def cup(entity_id: str, color: str, x: float, y: float) -> SceneEntity:
        return SceneEntity(
            id=entity_id, cls="cup", attributes={"color": color}, status=Status.ASSUMED, evidence=[supplied],
            geometry=Geometry(position=Point(frame=CoordinateFrame.WORLD, unit="m", x=x, y=y, calibration_id=CALIBRATION.id),
                              footprint_radius=Length(value=0.04)),
        )

    table = SceneEntity(
        id="table_01", cls="table", status=Status.ASSUMED, evidence=[supplied],
        geometry=Geometry(extent=BoundingBox(frame=CoordinateFrame.WORLD, unit="m", calibration_id=CALIBRATION.id,
                                             x_min=0.0, y_min=0.0, x_max=1.2, y_max=0.8)),
    )
    return SceneState(
        timestamp_s=None,
        entities=[table, cup("blue_cup_01", "blue", 1.05, 0.40), cup("red_cup_01", "red", 0.55, 0.45)],
        observations=[
            Observation(subject="blue_cup_01", relation="near_edge", object="table_01", value="right",
                        status=Status.OBSERVED, evidence=[EvidenceReference(
                            source_type=SourceType.TEXT, uri="inline-text", backend=BackendInfo(name="splm-pipeline", kind="parser", live=False),
                            text_span="A blue cup is near the right edge of a table.")],
                        note="stated by the text"),
            Observation(subject="red_cup_01", relation="far_from_edge", object="table_01",
                        status=Status.OBSERVED, evidence=[EvidenceReference(
                            source_type=SourceType.TEXT, uri="inline-text", backend=BackendInfo(name="splm-pipeline", kind="parser", live=False),
                            text_span="A red cup is farther from the edge.")],
                        note="stated by the text"),
        ],
        coordinate_frames=[CoordinateFrame.WORLD],
        calibration=CALIBRATION,
    )


def text_document() -> MeaningDocument:
    frames = text_frames()
    sentences = [s for s in frames if s in TABLETOP_TEXT]
    info = BackendInfo(name="splm-phrase-builder", version="hand-annotated-trees", kind="parser", live=False,
                       config={"parse": "hand-written UD trees (demo_text.conllu); frames built by MLM"})
    doc = TextAdapter().from_frames([frames[s] for s in sentences], text=TABLETOP_TEXT,
                                    scene=assumed_text_scene(), info=info)
    return doc


def image_document() -> MeaningDocument:
    return ImageAdapter(FixtureReplay(IMAGE_FIXTURE)).analyze("tabletop_scene.svg")


def video_document() -> MeaningDocument:
    return VideoAdapter(FixtureReplay(VIDEO_FIXTURE)).analyze("tabletop_push_synthetic.json")
