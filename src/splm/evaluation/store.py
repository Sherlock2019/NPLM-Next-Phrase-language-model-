"""Reading and writing benchmark results (spec section 38).

Results go to ``results/*.json`` plus a flat ``results/*.csv`` for spreadsheets.
Nothing is ever synthesised on read: if a file is not there, the dashboard shows
"no runs yet" rather than an example.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_result(results_dir: Path | str, payload: dict[str, Any]) -> Path:
    """Persist one benchmark run and return the JSON path."""
    directory = Path(results_dir)
    directory.mkdir(parents=True, exist_ok=True)

    run_id = str(payload.get("run_id") or "run")
    json_path = directory / f"{run_id}.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    items = payload.get("items") or []
    if items:
        csv_path = directory / f"{run_id}.csv"
        fieldnames = sorted({key for item in items for key in item})
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for item in items:
                writer.writerow(item)
        logger.info("wrote %s and %s", json_path.name, csv_path.name)
    else:
        logger.info("wrote %s", json_path.name)

    return json_path


def list_results(results_dir: Path | str) -> list[dict[str, Any]]:
    """Summaries of stored runs, newest first."""
    directory = Path(results_dir)
    if not directory.is_dir():
        return []

    summaries: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("could not read %s: %s", path, exc)
            continue
        summaries.append(
            {
                "run_id": payload.get("run_id", path.stem),
                "timestamp": payload.get("timestamp"),
                "model": payload.get("model", {}).get("model_id"),
                "fingerprint": payload.get("fingerprint"),
                "languages": payload.get("languages"),
                "samples": payload.get("samples"),
                "dataset": payload.get("dataset"),
                "headline": payload.get("headline"),
                "path": str(path),
            }
        )

    summaries.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return summaries


def load_result(results_dir: Path | str, run_id: str) -> dict[str, Any] | None:
    """Load one stored run, or ``None``."""
    path = Path(results_dir) / f"{run_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("could not read %s: %s", path, exc)
        return None
