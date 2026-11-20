"""Paired benchmark of the three speech modes.

Every item is recognised once and the same audio, ASR result, hardware and greedy
decoding settings feed all three modes, so differences are attributable to the mode.

Measured per item and mode:
    WER, CER                     transcript vs reference
    semantic-slot accuracy       transcript's Phrase DNA vs the reference's Phrase DNA
                                 (same parser on both; plus gold slots if the manifest has them)
    entity / number preservation critical items of the reference found in the transcript
    generation latency, time to first audio, end-to-end latency, RTF, memory

Verdicts reuse :class:`splm.evaluation.metrics.Comparison`: fewer than 20 paired
items gives "insufficient_data", and an improvement is only stated when the paired
McNemar test supports it. Two comparisons are made, because the modes differ in two
places:

* transcript quality: Whisper top-1 (modes A and B) vs validated transcript (mode C);
* answer generation: base model (A) vs NPLM (B), same transcript.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from splm.evaluation.metrics import Comparison, Continuous, Proportion
from splm.speech import MODES
from splm.speech.audio import encode_wav
from splm.speech.metrics import cer, edit_distance, normalize, preserved, wer

logger = logging.getLogger(__name__)

BUILTIN = Path(__file__).with_name("eval_utterances.json")


def load_items(manifest: str | Path | None = None, languages: Iterable[str] | None = None,
               limit: int | None = None) -> tuple[list[dict[str, Any]], str]:
    """Items from a JSONL manifest (real audio) or the built-in text set (synthetic)."""
    if manifest:
        path = Path(manifest)
        items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for item in items:
            if item.get("audio") and not Path(item["audio"]).is_absolute():
                item["audio"] = str((path.parent / item["audio"]).resolve())
        source = f"manifest:{path.name}"
    else:
        items = json.loads(BUILTIN.read_text(encoding="utf-8"))["items"]
        source = "builtin-synthetic-tts"
    wanted = set(languages or [])
    if wanted:
        items = [item for item in items if item.get("language") in wanted]
    if limit:
        per_language: dict[str, int] = {}
        kept = []
        for item in items:
            count = per_language.get(item["language"], 0)
            if count < limit:
                kept.append(item)
                per_language[item["language"]] = count + 1
        items = kept
    return items, source


def slot_matches(reference: dict[str, list[str]], hypothesis: dict[str, list[str]]) -> tuple[int, int]:
    """Categories of the reference DNA whose content the hypothesis DNA reproduces."""
    total = matched = 0
    for key, texts in reference.items():
        for text in texts:
            total += 1
            if normalize(text) in {normalize(t) for t in hypothesis.get(key, [])}:
                matched += 1
    return matched, total


class SpeechBenchmark:
    def __init__(self, pipeline: Any, config: Any) -> None:
        self.pipeline = pipeline
        self.config = config

    def _audio_for(self, item: dict[str, Any]) -> bytes:
        if item.get("audio"):
            return Path(item["audio"]).read_bytes()
        samples, info = self.pipeline.tts.synthesize(item["reference"], item["language"])
        return encode_wav(samples, info.sample_rate)

    def run(self, items: list[dict[str, Any]], *, source: str, speak: bool = True) -> dict[str, Any]:
        warmup = self.pipeline.warmup(sorted({i["language"] for i in items}))
        rows: list[dict[str, Any]] = []
        started = time.perf_counter()
        for index, item in enumerate(items, start=1):
            language = item["language"]
            audio = self._audio_for(item)
            reference_dna, _ = self.pipeline.analyse(item["reference"], language)
            gold = item.get("slots") or reference_dna.as_slots()
            result = self.pipeline.compare(audio=audio, language=language, speak=speak)
            for mode in MODES:
                turn = result["turns"][mode]
                transcript = turn["transcript"]
                hyp_slots = {
                    c["key"]: [i["text"] for i in c["items"]]
                    for c in (turn["dna"] or {}).get("categories", []) if c["items"]
                }
                s_ok, s_total = slot_matches(gold, hyp_slots)
                e_ok, e_total = preserved(item.get("entities", []), transcript)
                n_ok, n_total = preserved(item.get("numbers", []), transcript, numbers=True, language=language)
                ref_words = normalize(item["reference"]).split()
                t = turn["timings_ms"]
                rows.append({
                    "id": item.get("id", str(index)), "language": language, "mode": mode,
                    "reference": item["reference"], "transcript": transcript,
                    "wer": round(wer(item["reference"], transcript), 4),
                    "cer": round(cer(item["reference"], transcript), 4),
                    "word_errors": edit_distance(ref_words, normalize(transcript).split()),
                    "reference_words": len(ref_words),
                    "slots_matched": s_ok, "slots_total": s_total,
                    "entities_kept": e_ok, "entities_total": e_total,
                    "numbers_kept": n_ok, "numbers_total": n_total,
                    "response": turn["response_text"], "response_source": turn["response_source"],
                    "validation_changed": bool((turn.get("validation") or {}).get("changed")),
                    "generation_ms": t.get("generation"), "time_to_first_audio_ms": t.get("time_to_first_audio"),
                    "end_to_end_ms": t.get("end_to_end"), "asr_ms": t.get("asr"),
                    "rtf_end_to_end": turn["rtf"].get("end_to_end"), "rtf_asr": turn["rtf"].get("asr"),
                    "peak_rss_mb": turn["memory"].get("peak_rss_mb"), "tokens_generated": turn["tokens_generated"],
                })
            logger.info("[%d/%d] %s", index, len(items), item.get("id"))

        report = self.summarise(rows)
        now = datetime.now(timezone.utc)
        return {
            "run_id": f"speech-{now.strftime('%Y%m%d-%H%M%S')}",
            "timestamp": now.isoformat(),
            "kind": "speech",
            "dataset": source,
            "synthetic": source.startswith("builtin"),
            "languages": sorted({r["language"] for r in rows}),
            "samples": len(items),
            "model": {"model_id": self.pipeline.describe().get("answer_model")},
            "system": self.pipeline.describe(),
            "warmup_ms": warmup,
            "wall_time_s": round(time.perf_counter() - started, 1),
            "hardware": _hardware(),
            **report,
            "items": rows,
            "caveats": _caveats(source),
        }

    @staticmethod
    def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
        by_mode = {mode: [r for r in rows if r["mode"] == mode] for mode in MODES}

        def mean(values: list[Any]) -> float | None:
            values = [v for v in values if v is not None]
            return round(sum(values) / len(values), 4) if values else None

        per_mode: dict[str, Any] = {}
        for mode, items in by_mode.items():
            words = sum(r["reference_words"] for r in items)
            per_mode[mode] = {
                "items": len(items),
                "corpus_wer": round(sum(r["word_errors"] for r in items) / words, 4) if words else None,
                "mean_cer": mean([r["cer"] for r in items]),
                "slot_accuracy": Proportion(successes=sum(r["slots_matched"] for r in items),
                                            total=sum(r["slots_total"] for r in items)).summary(),
                "entity_preservation": Proportion(successes=sum(r["entities_kept"] for r in items),
                                                  total=sum(r["entities_total"] for r in items)).summary(),
                "number_preservation": Proportion(successes=sum(r["numbers_kept"] for r in items),
                                                  total=sum(r["numbers_total"] for r in items)).summary(),
                "generation_ms": mean([r["generation_ms"] for r in items]),
                "time_to_first_audio_ms": mean([r["time_to_first_audio_ms"] for r in items]),
                "end_to_end_ms": mean([r["end_to_end_ms"] for r in items]),
                "rtf_end_to_end": mean([r["rtf_end_to_end"] for r in items]),
                "rtf_asr": mean([r["rtf_asr"] for r in items]),
                "peak_rss_mb": max((r["peak_rss_mb"] or 0 for r in items), default=None),
                "clarifications": sum(1 for r in items if r["response_source"] == "clarification"),
                "validation_changed": sum(1 for r in items if r["validation_changed"]),
            }

        def paired(metric: str, left: str, right: str, ok: str, total: str) -> dict[str, Any]:
            """Per-item all-or-nothing correctness, over items where the metric applies."""
            a = {r["id"]: r for r in by_mode[left] if r[total]}
            b = {r["id"]: r for r in by_mode[right] if r[total]}
            ids = sorted(set(a) & set(b))
            a_ok = [a[i][ok] == a[i][total] for i in ids]
            b_ok = [b[i][ok] == b[i][total] for i in ids]
            return Comparison(
                metric=metric,
                base=Proportion(successes=sum(a_ok), total=len(ids)),
                splm=Proportion(successes=sum(b_ok), total=len(ids)),
                base_only_correct=sum(1 for x, y in zip(a_ok, b_ok) if x and not y),
                splm_only_correct=sum(1 for x, y in zip(a_ok, b_ok) if y and not x),
                note=f"'base' = {left}, 'splm' = {right}; an item counts when every expected item is kept",
            ).summary()

        def continuous(metric: str, key: str, left: str, right: str, unit: str, lower: bool = True) -> dict[str, Any]:
            return Continuous(
                metric=metric,
                base_values=[r[key] for r in by_mode[left] if r[key] is not None],
                splm_values=[r[key] for r in by_mode[right] if r[key] is not None],
                lower_is_better=lower, unit=unit,
            ).summary() | {"base": left, "splm": right}

        comparisons = {
            "transcript": {
                "entity_preservation": paired("Critical entity preservation (item)", "nplm", "nplm_validated", "entities_kept", "entities_total"),
                "number_preservation": paired("Critical number preservation (item)", "nplm", "nplm_validated", "numbers_kept", "numbers_total"),
                "slot_accuracy": paired("Semantic-slot accuracy (item)", "nplm", "nplm_validated", "slots_matched", "slots_total"),
                "wer": continuous("WER", "wer", "nplm", "nplm_validated", "ratio"),
                "cer": continuous("CER", "cer", "nplm", "nplm_validated", "ratio"),
            },
            "generation": {
                "generation_ms": continuous("Generation latency", "generation_ms", "base", "nplm", "ms"),
                "time_to_first_audio_ms": continuous("Time to first audio", "time_to_first_audio_ms", "base", "nplm", "ms"),
                "end_to_end_ms": continuous("End-to-end latency", "end_to_end_ms", "base", "nplm", "ms"),
                "rtf_end_to_end": continuous("End-to-end RTF", "rtf_end_to_end", "base", "nplm", "x"),
            },
        }
        headline = [
            comparisons["transcript"][k]["statement"]
            for k in ("entity_preservation", "number_preservation", "slot_accuracy")
        ]
        gen = comparisons["generation"]["generation_ms"]
        headline.append(
            f"Generation latency: base {gen['base_mean']} ms vs NPLM {gen['splm_mean']} ms "
            f"over {gen['samples']} paired items (NPLM overhead {gen['difference']:+.0f} ms)."
        )
        return {"per_mode": per_mode, "comparisons": comparisons, "headline": headline}


def _hardware() -> dict[str, Any]:
    try:
        from splm.device import device_report

        return device_report()
    except Exception:  # noqa: BLE001
        return {}


def _caveats(source: str) -> list[str]:
    caveats = [
        "Response quality (helpfulness, correctness of answers) is not scored: no reference answers exist.",
        "Latency is CPU wall-clock in one process; the first item after warmup may still be slower.",
        "Peak RSS is for the whole process (all models loaded), not per mode.",
        "Mode C's latency excludes generation when it asks a clarifying question instead.",
    ]
    if source.startswith("builtin"):
        caveats.insert(0, "Synthetic speech: audio was produced by the TTS voice, not recorded from people. "
                          "WER and preservation figures describe TTS->ASR round trips only.")
    return caveats
