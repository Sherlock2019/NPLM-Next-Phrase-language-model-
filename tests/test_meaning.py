"""The shared meaning layer: schemas, coordinate frames, identity, adapters, leakage."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from splm.meaning import (
    BackendInfo,
    CoordinateFrame,
    EvidenceReference,
    GeometryError,
    MeaningEvent,
    Observation,
    Point,
    RoleFiller,
    SceneEntity,
    SceneState,
    SourceType,
    Status,
    distance_m,
)
from splm.meaning import demo
from splm.meaning.adapters import (
    AdapterError,
    BackendUnavailable,
    FixtureReplay,
    ImageAdapter,
    VideoAdapter,
    reconcile_ids,
)
from splm.meaning.adapters.image import ImageExtraction
from splm.meaning.adapters.models import OpenAICompatibleVLM, YoloTracker
from splm.meaning.frames import action_to_frame

REPLAY = BackendInfo(name="test", kind="fixture_replay", live=False)
IMAGE_EVIDENCE = EvidenceReference(source_type=SourceType.IMAGE, uri="x.png", backend=REPLAY)


# -- coordinate frames ---------------------------------------------------------------

def test_pixels_are_not_metres():
    pixel = Point(frame=CoordinateFrame.IMAGE_PIXEL, unit="px", x=320, y=240)
    with pytest.raises(GeometryError):
        pixel.in_metres()
    with pytest.raises(ValidationError):
        Point(frame=CoordinateFrame.WORLD, unit="px", x=1, y=1, calibration_id="c")
    with pytest.raises(ValidationError, match="calibration_id"):
        Point(frame=CoordinateFrame.WORLD, unit="m", x=1, y=1)
    with pytest.raises(ValidationError, match="\\[0, 1\\]"):
        Point(frame=CoordinateFrame.IMAGE_NORMALIZED, unit="normalized", x=1.5, y=0.2)


def test_distance_only_within_one_calibration():
    a = Point(frame=CoordinateFrame.WORLD, unit="m", x=0, y=0, calibration_id="c1")
    b = Point(frame=CoordinateFrame.WORLD, unit="cm", x=300, y=400, calibration_id="c1")
    assert distance_m(a, b) == pytest.approx(5.0)
    with pytest.raises(GeometryError, match="different calibrations"):
        distance_m(a, Point(frame=CoordinateFrame.WORLD, unit="m", x=1, y=1, calibration_id="c2"))


def test_calibration_maps_image_plane_to_world():
    point = Point(frame=CoordinateFrame.IMAGE_NORMALIZED, unit="normalized", x=625 / 800, y=300 / 500)
    world = demo.CALIBRATION.to_world(point)
    assert (world.x, world.y, world.unit, world.calibration_id) == (1.05, 0.4, "m", demo.CALIBRATION.id)


# -- schemas -------------------------------------------------------------------------------

def test_two_objects_of_one_class_stay_distinct():
    raw = ImageExtraction.model_validate({
        "image_size": {"width": 100, "height": 100},
        "entities": [{"class": "cup", "box_px": [60, 0, 70, 10]}, {"class": "cup", "box_px": [10, 0, 20, 10]}],
    })
    assert reconcile_ids(raw.entities) == {1: "cup_01", 0: "cup_02"}  # left to right, never merged
    with pytest.raises(ValidationError, match="duplicate entity ids"):
        SceneState(entities=[SceneEntity(id="cup_01", cls="cup"), SceneEntity(id="cup_01", cls="cup")])
    with pytest.raises(ValidationError, match="cup_01"):
        SceneEntity(id="cup", cls="cup")


def test_observed_needs_evidence_and_purpose_needs_a_statement():
    with pytest.raises(ValidationError, match="needs evidence"):
        Observation(subject="cup_01", property="color", value="blue", status=Status.OBSERVED)
    with pytest.raises(ValidationError, match="purpose or cause"):
        MeaningEvent(id="e1", predicate="push", roles={"PURPOSE": [RoleFiller(text="to break it")]},
                     evidence=[IMAGE_EVIDENCE])
    with pytest.raises(ValidationError, match="not events"):
        MeaningEvent(id="e2", predicate="fall", status=Status.PREDICTED, evidence=[IMAGE_EVIDENCE])
    with pytest.raises(ValidationError, match="timestamp"):
        EvidenceReference(source_type=SourceType.VIDEO, uri="v.mp4", backend=REPLAY)


# -- image adapter --------------------------------------------------------------------------

def test_image_shows_a_scene_not_an_action():
    doc = demo.image_document()
    state = doc.states[0]
    assert doc.source.backend.live is False  # replay, labelled as such
    assert {e.id for e in state.entities} == {"table_01", "blue_cup_01", "red_cup_01"}
    relations = {(o.subject, o.relation) for o in state.observations if o.relation}
    assert ("blue_cup_01", "near_edge") in relations
    assert doc.events == []  # nothing happened in a still image
    rejected = {c["type"] for c in doc.rejected_claims}
    assert rejected == {"past_action", "ownership", "intent"}
    assert any("treated as data" in n for n in doc.notes)


def test_replay_is_not_analysis_of_other_media():
    with pytest.raises(AdapterError, match="not an analysis of other media"):
        ImageAdapter(FixtureReplay(demo.IMAGE_FIXTURE)).analyze("holiday.png")
    with pytest.raises(AdapterError, match="unsupported image type"):
        ImageAdapter(FixtureReplay(demo.IMAGE_FIXTURE)).analyze("notes.txt")


def test_malformed_model_response_is_an_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"media": "x.png", "image_size": {"width": 10, "height": 10},
                               "entities": [{"class": "cup"}]}))
    with pytest.raises(AdapterError, match="no box"):
        ImageAdapter(FixtureReplay(bad)).analyze("x.png")
    bad.write_text("{not json")
    with pytest.raises(AdapterError, match="not valid JSON"):
        FixtureReplay(bad)


# -- video adapter --------------------------------------------------------------------------

def test_video_timeline_events_and_identity():
    doc = demo.video_document()
    assert [s.timestamp_s for s in doc.states] == sorted(s.timestamp_s for s in doc.states)
    push, fall = doc.events
    assert (push.predicate, push.interval.start_s, push.interval.end_s) == ("push", 2.0, 3.0)  # two segments merged
    assert len(push.evidence) == 2
    assert push.entity_ids("AGENT") == ["pusher_01"] and push.entity_ids("PATIENT") == ["blue_cup_01"]
    assert fall.causal_attribution == "uncertain"  # order is visible, cause is not
    assert "PURPOSE" not in push.roles
    tracks = {e.id: e.tracks[0] for e in doc.states[0].entities if e.tracks}
    assert all(t.session_id == "synthetic_session_01" for t in tracks.values())


def test_prediction_input_never_contains_future_frames():
    doc = demo.video_document()
    at_t = doc.available_at(demo.VIDEO_CHECKPOINT_S)
    assert max(s.timestamp_s for s in at_t.states) == 2.0
    assert at_t.events == []  # the push starts at 2.0 and ends at 3.0: not known at T
    assert at_t.state_at(2.0).timestamp_s == 2.0


def test_video_errors_are_clear(tmp_path):
    raw = json.loads(demo.VIDEO_FIXTURE.read_text())
    for mutate, message in (
        (lambda d: d.update(frames=[]), "no sampled frames"),
        (lambda d: d["frames"].reverse(), "strictly increasing"),
    ):
        data = json.loads(json.dumps(raw))
        mutate(data)
        path = tmp_path / "v.json"
        path.write_text(json.dumps(data))
        with pytest.raises(AdapterError, match=message):
            VideoAdapter(FixtureReplay(path)).analyze("tabletop_push_synthetic.json")


# -- text adapter and semantic consistency --------------------------------------------------------

def test_text_states_a_plan_and_leaves_purpose_unknown():
    doc = demo.text_document()
    assert len(doc.goals) == 1 and doc.goals[0].owner == "self"
    plan = doc.goals[0].frame
    push = next(e.frame for _, e in plan.elements() if e.frame is not None)
    assert push.predicate.lemma == "push"
    assert push.objects[0].annotations["entity_id"] == "blue_cup_01"  # the one blue cup
    assert push.goal == []  # no purpose stated, none invented
    assert all(e.status == Status.OBSERVED for e in doc.events)  # stated states, not seen ones


def test_text_and_video_agree_on_core_roles_but_not_on_evidence():
    text_push = next(e.frame for _, e in demo.text_document().goals[0].frame.elements() if e.frame is not None)
    video_push = demo.video_document().events[0]
    assert text_push.predicate.lemma == video_push.predicate == "push"
    assert text_push.objects[0].annotations["entity_id"] == video_push.entity_ids("PATIENT")[0]
    # Different evidence: the text plans it (future), the video shows it (past, observed, with an agent).
    assert video_push.status == Status.OBSERVED and video_push.entity_ids("AGENT") == ["pusher_01"]
    assert demo.text_document().goals[0].source == "stated"


def test_proposed_action_frame_has_no_invented_roles():
    action = demo.proposed_actions(actor="self")["push_edge"]
    frame = action_to_frame(action)
    assert frame.modality == "proposal" and frame.tense.value == "future"
    assert frame.goal == [] and frame.cause == []
    assert frame.subject[0].annotations["entity_id"] == "self"


# -- optional backends -------------------------------------------------------------------------------

def test_live_backends_fail_clearly(tmp_path, monkeypatch):
    monkeypatch.delenv("SPLM_VLM_ENDPOINT", raising=False)
    image = tmp_path / "x.png"
    image.write_bytes(b"\x89PNG")
    with pytest.raises(BackendUnavailable, match="SPLM_VLM_ENDPOINT"):
        OpenAICompatibleVLM().extract(image)
    vlm = OpenAICompatibleVLM("http://vlm.invalid", transport=lambda payload: {"choices": [{"message": {"content": "sure!"}}]})
    with pytest.raises(AdapterError, match="not valid JSON"):
        vlm.extract(image)
    with pytest.raises(BackendUnavailable, match="never fetched automatically"):
        YoloTracker(tmp_path / "missing.pt").track(None)
