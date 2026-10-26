#!/usr/bin/env python3
"""Generate the tabletop demo materials from one scenario definition.

    python scripts/make_tabletop_demo.py            # add --no-video to skip encoding

Writes, from the constants below:

    web/public/demo/tabletop_push_synthetic.mp4 / .webm
        the synthetic animation, rendered frame by frame from KEYFRAMES with headless
        Chromium and encoded with ffmpeg (skipped, with a message, if either is missing)

    web/public/demo/tabletop_scene.svg            the image material (schematic top-down)
    web/public/demo/tabletop_scene_annotated.svg  boxes + relations, labelled "Demo fixture"
    web/public/demo/tabletop_video_script.json    keyframes for the synthetic animation
    src/splm/meaning/demo/tabletop_image_extraction.json
    src/splm/meaning/demo/tabletop_video_extraction.json
        hand-authored extractions in the exact schema a VLM must return. They are
        written to match the generated media - they are NOT output of a live model,
        and say so in "recorded_backend".

Everything is synthetic and deterministic: same scenario in, same files out.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "public" / "demo"
FIXTURES = ROOT / "src" / "splm" / "meaning" / "demo"

# -- the scenario (world frame, metres) --------------------------------------
TABLE = (0.0, 0.0, 1.2, 0.8)  # x_min, y_min, x_max, y_max: the support boundary
IMAGE_W, IMAGE_H = 800, 500
PX_PER_M, ORIGIN_PX = 500, 100  # synthetic camera: straight down, 500 px per metre
CUP_R = 0.04
BLUE = {"id": "blue_cup_01", "x": 1.05, "y": 0.40, "color": "blue", "fill": "#2563eb"}
RED = {"id": "red_cup_01", "x": 0.55, "y": 0.45, "color": "red", "fill": "#dc2626"}
PUSHER_HALF = (0.04, 0.05)
SESSION = "synthetic_session_01"
CALIBRATION = {
    "id": "synthetic_topdown_01",
    "homography": [[IMAGE_W / PX_PER_M, 0, -ORIGIN_PX / PX_PER_M], [0, IMAGE_H / PX_PER_M, -ORIGIN_PX / PX_PER_M], [0, 0, 1]],
    "plane": "table_01 top surface",
    "source": "known by construction of the synthetic image (500 px per metre, origin at 100 px)",
    "reference_point": "centre",
}
HAND_AUTHORED = {
    "name": "hand-authored fixture",
    "note": "Written to match the generated synthetic media. Not the output of a live model.",
}

# Video keyframes: (t, pusher_x, blue_x, blue_on_floor). Linear between keyframes.
DURATION = 6.0
CHECKPOINT_T = 2.0  # paused here: the prediction may use only t <= 2.0
KEYFRAMES = [
    (0.0, 0.85, 1.05, False),
    (1.0, 0.85, 1.05, False),
    (2.0, 0.97, 1.05, False),   # pusher touches the cup (cup left edge 1.01)
    (3.0, 1.17, 1.25, False),   # pushed 0.20 m; centre crosses the edge (1.20) at t=2.75
    (3.5, 1.10, 1.30, True),    # off the support: falls to the floor
    (4.0, 1.00, 1.32, True),
    (6.0, 0.90, 1.32, True),
]
EVENTS = [  # synchronized with the keyframes above
    {"start_s": 1.0, "end_s": 2.0, "label": "pusher approaches blue_cup_01"},
    {"start_s": 2.0, "end_s": 3.0, "label": "push: pusher_01 pushes blue_cup_01 toward the right edge"},
    {"start_s": 2.75, "end_s": 2.75, "label": "blue_cup_01 centre crosses the table edge"},
    {"start_s": 3.0, "end_s": 4.0, "label": "fall: blue_cup_01 falls off table_01"},
]


def px(x_m: float) -> float:
    return ORIGIN_PX + x_m * PX_PER_M


def at(t: float) -> tuple[float, float, bool]:
    for (t0, p0, b0, f0), (t1, p1, b1, f1) in zip(KEYFRAMES, KEYFRAMES[1:]):
        if t0 <= t <= t1:
            a = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            return round(p0 + a * (p1 - p0), 4), round(b0 + a * (b1 - b0), 4), f1 if a == 1 else f0
    return KEYFRAMES[-1][1], KEYFRAMES[-1][2], KEYFRAMES[-1][3]


def box(x: float, y: float, hx: float, hy: float) -> list[float]:
    return [round((px(x - hx)) / IMAGE_W, 5), round((px(y - hy)) / IMAGE_H, 5),
            round((px(x + hx)) / IMAGE_W, 5), round((px(y + hy)) / IMAGE_H, 5)]


# -- image material -------------------------------------------------------------

def scene_svg(annotated: bool) -> str:
    t0, t1, t2, t3 = (px(v) for v in TABLE)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {IMAGE_W} {IMAGE_H + 60}" role="img" '
        f'aria-label="Schematic top-down tabletop scene{" with demo-fixture annotations" if annotated else ""}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<rect x="{t2}" y="0" width="{IMAGE_W - t2}" height="{IMAGE_H}" fill="#e2e8f0"/>',
        f'<text x="{t2 + 8}" y="24" font-family="sans-serif" font-size="13" fill="#475569">floor</text>',
        f'<rect x="{t0}" y="{t1}" width="{t2 - t0}" height="{t3 - t1}" fill="#d6b88a" stroke="#7c5a2a" stroke-width="4"/>',
        f'<text x="{t0 + 10}" y="{t1 + 24}" font-family="sans-serif" font-size="15" fill="#5b3f17">table_01 (support boundary)</text>',
    ]
    for cup in (BLUE, RED):
        cx, cy, r = px(cup["x"]), px(cup["y"]), CUP_R * PX_PER_M
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{cup["fill"]}" stroke="#0f172a" stroke-width="2"/>')
        parts.append(f'<text x="{cx}" y="{cy + r + 18}" text-anchor="middle" font-family="sans-serif" '
                     f'font-size="14" fill="#0f172a">{cup["id"]}</text>')
    # schematic coordinates
    for x_m in (0.0, 0.3, 0.6, 0.9, 1.2):
        parts.append(f'<line x1="{px(x_m)}" y1="{t3}" x2="{px(x_m)}" y2="{t3 + 8}" stroke="#334155"/>')
        parts.append(f'<text x="{px(x_m)}" y="{t3 + 24}" text-anchor="middle" font-family="monospace" '
                     f'font-size="12" fill="#334155">x={x_m:.1f} m</text>')
    parts.append(f'<text x="12" y="{IMAGE_H + 50}" font-family="sans-serif" font-size="13" fill="#334155">'
                 'Schematic top-down view - synthetic illustration, 500 px = 1 m (schematic coordinates)</text>')
    if annotated:
        for cup in (BLUE, RED):
            b = box(cup["x"], cup["y"], CUP_R, CUP_R)
            x0, y0, x1, y1 = b[0] * IMAGE_W, b[1] * IMAGE_H, b[2] * IMAGE_W, b[3] * IMAGE_H
            parts.append(f'<rect x="{x0 - 4}" y="{y0 - 4}" width="{x1 - x0 + 8}" height="{y1 - y0 + 8}" fill="none" '
                         'stroke="#9333ea" stroke-width="2" stroke-dasharray="6 4"/>')
        parts += [
            f'<line x1="{px(BLUE["x"]) + 22}" y1="{px(BLUE["y"])}" x2="{t2}" y2="{px(BLUE["y"])}" stroke="#9333ea" '
            'stroke-width="2" marker-end="url(#a)"/>',
            '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
            '<path d="M0,0 L10,5 L0,10 z" fill="#9333ea"/></marker></defs>',
            f'<text x="{px(BLUE["x"]) - 130}" y="{px(BLUE["y"]) - 40}" font-family="sans-serif" font-size="13" '
            'fill="#6b21a8">near_edge(blue_cup_01, table_01, right)</text>',
            f'<text x="{px(RED["x"]) - 80}" y="{px(RED["y"]) - 36}" font-family="sans-serif" font-size="13" '
            'fill="#6b21a8">far_from_edge(red_cup_01)</text>',
            '<rect x="560" y="8" width="230" height="30" rx="6" fill="#6b21a8"/>',
            '<text x="675" y="28" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#fff">'
            'Demo fixture - not live detections</text>',
        ]
    parts.append("</svg>")
    return "\n".join(parts)


def image_extraction() -> dict:
    def ent(cup):
        b = box(cup["x"], cup["y"], CUP_R, CUP_R)
        return {"id": cup["id"], "class": "cup", "attributes": {"color": cup["color"]},
                "box_px": [round(b[0] * IMAGE_W, 1), round(b[1] * IMAGE_H, 1), round(b[2] * IMAGE_W, 1), round(b[3] * IMAGE_H, 1)],
                "detection_confidence": None}
    return {
        "version": 1,
        "media": "tabletop_scene.svg",
        "recorded_backend": HAND_AUTHORED,
        "image_size": {"width": IMAGE_W, "height": IMAGE_H},
        "calibration": CALIBRATION,
        "entities": [
            {"id": "table_01", "class": "table", "attributes": {}, "box_px": [px(TABLE[0]), px(TABLE[1]), px(TABLE[2]), px(TABLE[3])]},
            ent(BLUE), ent(RED),
        ],
        "relations": [
            {"subject": "blue_cup_01", "relation": "on", "object": "table_01"},
            {"subject": "blue_cup_01", "relation": "near_edge", "object": "table_01", "value": "right"},
            {"subject": "red_cup_01", "relation": "on", "object": "table_01"},
            {"subject": "red_cup_01", "relation": "far_from_edge", "object": "table_01"},
        ],
        "event_hypotheses": [],
        "claims": [
            {"type": "past_action", "text": "someone pushed the blue cup"},
            {"type": "ownership", "text": "the blue cup belongs to the person at the table"},
            {"type": "intent", "text": "someone intends to knock the cup over"},
        ],
        "text_in_image": ["Schematic top-down view - synthetic illustration"],
    }


# -- video material ---------------------------------------------------------------

def video_script() -> dict:
    return {
        "title": "Synthetic demonstration - scripted motion",
        "duration_s": DURATION,
        "checkpoint_s": CHECKPOINT_T,
        "world": {"table": TABLE, "px_per_m": PX_PER_M, "origin_px": ORIGIN_PX, "image": [IMAGE_W, IMAGE_H]},
        "objects": {"blue": BLUE, "red": RED, "cup_radius_m": CUP_R, "pusher_half_m": PUSHER_HALF},
        "keyframes": [{"t": t, "pusher_x": p, "blue_x": b, "blue_on_floor": f} for t, p, b, f in KEYFRAMES],
        "events": EVENTS,
    }


def video_extraction(step: float = 0.5) -> dict:
    frames = []
    n = int(DURATION / step) + 1
    for i in range(n):
        t = round(i * step, 3)
        pusher_x, blue_x, _ = at(t)
        frames.append({
            "t": t, "frame_index": int(round(t * 25)),  # the animation runs at a nominal 25 fps
            "detections": [
                {"track_id": 1, "class": "cup", "attributes": {"color": "blue"}, "box_normalized": box(blue_x, BLUE["y"], CUP_R, CUP_R)},
                {"track_id": 2, "class": "cup", "attributes": {"color": "red"}, "box_normalized": box(RED["x"], RED["y"], CUP_R, CUP_R)},
                {"track_id": 3, "class": "pusher", "attributes": {}, "box_normalized": box(pusher_x, BLUE["y"], *PUSHER_HALF)},
            ],
        })
    return {
        "version": 1,
        "media": "tabletop_push_synthetic.json",
        "recorded_backend": HAND_AUTHORED,
        "duration_s": DURATION,
        "tracking_session": SESSION,
        "track_ids": {"1": "blue_cup_01", "2": "red_cup_01", "3": "pusher_01"},
        "static_entities": [{"id": "table_01", "class": "table", "box_normalized": box(0.6, 0.4, 0.6, 0.4),
                             "extent_m": list(TABLE)}],
        "calibration": CALIBRATION,
        "frames": frames,
        "segments": [
            {"start_s": 2.0, "end_s": 2.5, "events": [{"predicate": "push", "roles": {"AGENT": "track:3", "PATIENT": "track:1", "DESTINATION": "right edge"}, "causal": "supported"}]},
            {"start_s": 2.5, "end_s": 3.0, "events": [{"predicate": "push", "roles": {"AGENT": "track:3", "PATIENT": "track:1", "DESTINATION": "right edge"}, "causal": "supported"}]},
            {"start_s": 3.0, "end_s": 4.0, "events": [{"predicate": "fall", "roles": {"THEME": "track:1", "SOURCE": "table_01"}, "causal": "uncertain"}]},
        ],
    }


# -- video material: frames rendered from the same keyframes, encoded with ffmpeg -------------

FPS = 25


def frame_svg(t: float) -> str:
    """One frame of the scripted animation. Drawn from KEYFRAMES, so it matches the fixtures."""
    pusher_x, blue_x, on_floor = at(t)
    t0, t1, t2, t3 = (px(v) for v in TABLE)
    r = CUP_R * PX_PER_M
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{IMAGE_W}" height="{IMAGE_H + 60}" viewBox="0 0 {IMAGE_W} {IMAGE_H + 60}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<rect x="{t2}" y="0" width="{IMAGE_W - t2}" height="{IMAGE_H}" fill="#e2e8f0"/>',
        f'<text x="{t2 + 8}" y="56" font-family="sans-serif" font-size="13" fill="#475569">floor</text>',
        f'<rect x="{t0}" y="{t1}" width="{t2 - t0}" height="{t3 - t1}" fill="#d6b88a" stroke="#7c5a2a" stroke-width="4"/>',
        f'<text x="{t0 + 10}" y="{t1 + 24}" font-family="sans-serif" font-size="15" fill="#5b3f17">table_01</text>',
        f'<circle cx="{px(RED["x"])}" cy="{px(RED["y"])}" r="{r}" fill="{RED["fill"]}" stroke="#0f172a" stroke-width="2"/>',
        f'<text x="{px(RED["x"])}" y="{px(RED["y"]) + r + 18}" text-anchor="middle" font-family="sans-serif" font-size="14">red_cup_01</text>',
    ]
    # The blue cup: on the table, then over the edge, then smaller as it drops away from a top-down camera.
    if blue_x <= TABLE[2]:
        scale, opacity = 1.0, 1.0
    else:
        drop = min(1.0, (t - 2.75) / 1.0) if t > 2.75 else 0.0
        scale, opacity = 1.0 - 0.35 * drop, 1.0 - 0.25 * drop
    parts.append(f'<circle cx="{px(blue_x)}" cy="{px(BLUE["y"])}" r="{r * scale:.2f}" fill="{BLUE["fill"]}" '
                 f'fill-opacity="{opacity:.2f}" stroke="#0f172a" stroke-width="2"/>')
    parts.append(f'<text x="{px(blue_x)}" y="{px(BLUE["y"]) + r + 18}" text-anchor="middle" font-family="sans-serif" '
                 f'font-size="14">blue_cup_01</text>')
    hx, hy = PUSHER_HALF[0] * PX_PER_M, PUSHER_HALF[1] * PX_PER_M
    parts.append(f'<rect x="{px(pusher_x) - hx:.1f}" y="{px(BLUE["y"]) - hy:.1f}" width="{2 * hx}" height="{2 * hy}" '
                 'rx="6" fill="#334155"/>')
    parts.append(f'<text x="{px(pusher_x):.1f}" y="{px(BLUE["y"]) - hy - 8:.1f}" text-anchor="middle" '
                 'font-family="sans-serif" font-size="13" fill="#334155">pusher_01</text>')
    active = [e["label"] for e in EVENTS if e["start_s"] <= t <= e["end_s"] + (0.25 if e["start_s"] == e["end_s"] else 0)]
    parts += [
        f'<rect x="0" y="0" width="{IMAGE_W}" height="34" fill="#0f172a"/>',
        '<text x="12" y="22" font-family="sans-serif" font-size="14" font-weight="600" fill="#fff">'
        'Synthetic demonstration — scripted motion</text>',
        f'<text x="{IMAGE_W - 12}" y="22" text-anchor="end" font-family="monospace" font-size="14" fill="#fff">t = {t:4.2f} s</text>',
        f'<text x="12" y="{IMAGE_H + 40}" font-family="sans-serif" font-size="13" fill="#334155">'
        f'{" · ".join(active) if active else ("checkpoint: before the push" if abs(t - CHECKPOINT_T) < 0.05 else "")}</text>',
        "</svg>",
    ]
    return "\n".join(parts)


def find_chrome() -> str | None:
    import glob
    import os
    import shutil

    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    for name in ("chromium", "chromium-browser", "google-chrome"):
        if shutil.which(name):
            return shutil.which(name)
    shells = sorted(glob.glob(str(Path.home() / ".cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")))
    return shells[-1] if shells else None


def render_video() -> list[Path]:
    """Screenshot every frame with headless Chromium, then encode MP4 (H.264) and WebM (VP9)."""
    import shutil
    import subprocess
    import tempfile

    chrome, ffmpeg = find_chrome(), shutil.which("ffmpeg")
    if not chrome or not ffmpeg:
        print("skipping video: needs headless Chromium (set CHROME) and ffmpeg; the page falls back to the SVG animation")
        return []
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for i in range(int(DURATION * FPS) + 1):
            svg = tmpdir / f"f{i:04d}.svg"
            svg.write_text(frame_svg(round(i / FPS, 3)), encoding="utf-8")
            subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                            f"--window-size={IMAGE_W},{IMAGE_H + 60}", f"--screenshot={tmpdir / f'f{i:04d}.png'}",
                            svg.as_uri()], check=True, capture_output=True, timeout=60)
        frames = str(tmpdir / "f%04d.png")
        mp4, webm = WEB / "tabletop_push_synthetic.mp4", WEB / "tabletop_push_synthetic.webm"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", frames, "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-crf", "23", str(mp4)], check=True)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", frames, "-c:v", "libvpx-vp9",
                        "-b:v", "0", "-crf", "36", str(webm)], check=True)
        out += [mp4, webm]
    return out


def main() -> int:
    import sys

    WEB.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (WEB / "tabletop_scene.svg").write_text(scene_svg(False), encoding="utf-8")
    (WEB / "tabletop_scene_annotated.svg").write_text(scene_svg(True), encoding="utf-8")
    outputs = {
        WEB / "tabletop_video_script.json": video_script(),
        FIXTURES / "tabletop_image_extraction.json": image_extraction(),
        FIXTURES / "tabletop_video_extraction.json": video_extraction(),
        # Same fixtures, published next to the media for "Download Example Material".
        WEB / "tabletop_image_extraction.json": image_extraction(),
        WEB / "tabletop_video_extraction.json": video_extraction(),
    }
    (WEB / "tabletop_text.txt").write_text(
        "A blue cup is near the right edge of a table. A red cup is farther from the edge. "
        "I plan to push the blue cup toward the right edge.\n\n"
        "Second example (context, then action):\nMark wants to buy my car.\nSarah needs a car.\n"
        "I will sell my car to Sarah to pay my debt.\n",
        encoding="utf-8",
    )
    for path, data in outputs.items():
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for path in [WEB / "tabletop_scene.svg", WEB / "tabletop_scene_annotated.svg", *outputs]:
        print(f"wrote {path.relative_to(ROOT)}")
    if "--no-video" not in sys.argv:
        for path in render_video():
            print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
