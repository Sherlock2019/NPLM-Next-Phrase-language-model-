#!/usr/bin/env python
"""A minimal Gradio Speech Lab over the same SpeechPipeline as the dashboard.

    pip install -e '.[ui]'          # gradio
    python scripts/speech_lab_gradio.py            # http://127.0.0.1:7861

Speak into the microphone, pick a language and a mode; get the transcript, its
Phrase DNA sort, the answer as text and as speech, and the timings. The Next.js
dashboard's /speech page is the full version (comparison, benchmark, provenance).
"""

from __future__ import annotations

import base64
import io
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from splm.config import Config  # noqa: E402
from splm.speech.audio import encode_wav  # noqa: E402
from splm.speech.pipeline import SpeechPipeline  # noqa: E402

MODES = {
    "A · Base Transformer": "base",
    "B · NPLM": "nplm",
    "C · NPLM + semantic validation": "nplm_validated",
}
LANGUAGES = {"Auto": None, "English": "en", "Français": "fr", "Tiếng Việt": "vi"}


def dna_markdown(dna: dict | None) -> str:
    if not dna:
        return "_nothing recognised_"
    lines = ["| Phrase DNA | words |", "|---|---|"]
    for category in dna["categories"]:
        if category["key"] == "condition" and not category["items"]:
            continue
        label = category["label"]
        if category["key"] == "action" and dna.get("predicate_kind"):
            label = dna["predicate_kind"].upper()
        words = ", ".join(item["text"] for item in category["items"]) or ("**?**" if category["missing"] else "—")
        lines.append(f"| **{label}** | {words} |")
    if dna.get("unsorted"):
        lines.append(f"| unsorted | {' · '.join(dna['unsorted'])} |")
    return "\n".join(lines)


def build(pipeline: SpeechPipeline):
    import gradio as gr

    def run(audio, typed, language_label, mode_label):
        language, mode = LANGUAGES[language_label], MODES[mode_label]
        if audio is not None:
            rate, samples = audio
            samples = np.asarray(samples, dtype=np.float32)
            if samples.ndim > 1:
                samples = samples.mean(axis=1)
            if np.abs(samples).max(initial=0) > 1.0:
                samples = samples / 32768.0
            turn = pipeline.run_audio(encode_wav(samples, rate), mode, language)
        elif typed and typed.strip():
            turn = pipeline.run_text(typed, mode, language)
        else:
            return "", "_say or type something_", "", None, {}
        data = turn.model_dump(mode="json")
        spoken = None
        if turn.audio_wav_base64:
            with wave.open(io.BytesIO(base64.b64decode(turn.audio_wav_base64))) as handle:
                pcm = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
                spoken = (handle.getframerate(), pcm)
        answer = turn.response_text
        if turn.clarification:
            answer += f"\n\n_(dialogue policy: {turn.clarification.reason})_"
        return turn.transcript, dna_markdown(data["dna"]), answer, spoken, {
            "timings_ms": turn.timings_ms, "rtf": turn.rtf, "memory": turn.memory, "warnings": turn.warnings,
        }

    with gr.Blocks(title="NPLM Speech Lab") as demo:
        gr.Markdown("# NPLM Speech Lab\nMicrophone → Whisper → NPLM → MMS-TTS, all local Hugging Face models.")
        with gr.Row():
            with gr.Column():
                mic = gr.Audio(sources=["microphone", "upload"], type="numpy", label="Talk")
                typed = gr.Textbox(label="…or type", placeholder="Book a meeting with Sarah tomorrow.")
                language = gr.Dropdown(list(LANGUAGES), value="English", label="Language")
                mode = gr.Radio(list(MODES), value="C · NPLM + semantic validation", label="Mode")
                go = gr.Button("Send", variant="primary")
            with gr.Column():
                transcript = gr.Textbox(label="You said")
                dna = gr.Markdown()
                answer = gr.Markdown()
                voice = gr.Audio(label="Answer (speech)", autoplay=True)
                metrics = gr.JSON(label="Timings")
        go.click(run, [mic, typed, language, mode], [transcript, dna, answer, voice, metrics])
    return demo


def main() -> int:
    pipeline = SpeechPipeline(Config.load())
    print("loading models…", pipeline.warmup())
    build(pipeline).launch(server_name="127.0.0.1", server_port=7861)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
