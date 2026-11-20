"""Model provenance for the speech lab: what runs, from where, under which licence.

Licences below are what each model card states for the default checkpoints; a
checkpoint swapped in through config/speech.yaml shows "see the model card".
``verified`` comes from ``data/speech/verified.json``, written by
``scripts/download_resources.py --speech`` after it loads each checkpoint and runs
it (TTS speaks a sentence, Whisper transcribes it back). It is never assumed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

KNOWN_LICENCES = {
    "openai/whisper-tiny": "MIT",
    "openai/whisper-base": "MIT",
    "openai/whisper-small": "MIT",
    "openai/whisper-large-v3-turbo": "MIT",
    "facebook/mms-tts-eng": "CC-BY-NC 4.0 (non-commercial)",
    "facebook/mms-tts-fra": "CC-BY-NC 4.0 (non-commercial)",
    "facebook/mms-tts-vie": "CC-BY-NC 4.0 (non-commercial)",
    "Qwen/Qwen2.5-0.5B-Instruct": "Apache-2.0",
    "HuggingFaceTB/SmolLM2-135M": "Apache-2.0",
}


def verified_path(config: Any) -> Path:
    return config.data_dir / "speech" / "verified.json"


def load_verified(config: Any) -> dict[str, Any]:
    path = verified_path(config)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def cached_revision(model_id: str) -> str | None:
    """The snapshot hash in the local Hugging Face cache, if downloaded."""
    try:
        from huggingface_hub import scan_cache_dir

        for repo in scan_cache_dir().repos:
            if repo.repo_id == model_id:
                revisions = sorted(repo.revisions, key=lambda r: r.last_modified, reverse=True)
                return revisions[0].commit_hash if revisions else None
    except Exception:  # noqa: BLE001 - cache layout or library differences
        return None
    return None


def provenance(config: Any) -> list[dict[str, Any]]:
    verified = load_verified(config)
    entries: list[tuple[str, str, str | None]] = [("asr", str(config.get("speech.asr.model_id")), None)]
    for language, model_id in (config.get("speech.tts.voices", {}) or {}).items():
        entries.append(("tts", str(model_id), language))
    answer = config.get("speech.generation.model_id") or config.model.get("model_id")
    entries.append(("answer_model", str(answer), None))

    rows = []
    for role, model_id, language in entries:
        record = verified.get(model_id, {})
        rows.append({
            "role": role,
            "language": language,
            "model_id": model_id,
            "source": f"https://huggingface.co/{model_id}",
            "licence": KNOWN_LICENCES.get(model_id, "see the model card"),
            "revision": cached_revision(model_id),
            "verified": bool(record.get("ok")),
            "verified_at": record.get("at"),
            "verification": record.get("detail"),
        })
    return rows
