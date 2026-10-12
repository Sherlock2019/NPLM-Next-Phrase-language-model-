#!/usr/bin/env python3
"""Download every external resource SPLM uses, and record where it came from.

    python scripts/download_resources.py                  # parser models for configured languages
    python scripts/download_resources.py --languages vi    # one language
    python scripts/download_resources.py --model           # the base Transformer too
    python scripts/download_resources.py --all             # everything in data_sources.yaml
    python scripts/download_resources.py --list            # show what is configured

Spec section 33: SPLM never downloads data silently at runtime. This script is the
only sanctioned downloader, and for every artefact it fetches it writes the source
URL, dataset version, licence, download date and language into data/MANIFEST.json.
Anything not recorded there did not come from here.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from splm.config import Config  # noqa: E402
from splm.logging_utils import setup_logging  # noqa: E402


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"artefacts": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"artefacts": []}


def record(manifest: dict[str, Any], entry: dict[str, Any]) -> None:
    """Add or replace a provenance entry, keyed by name plus language."""
    artefacts: list[dict[str, Any]] = manifest.setdefault("artefacts", [])
    key = (entry["name"], entry.get("language"))
    for index, existing in enumerate(artefacts):
        if (existing.get("name"), existing.get("language")) == key:
            artefacts[index] = entry
            return
    artefacts.append(entry)


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["note"] = (
        "Provenance for every externally downloaded artefact. Each resource remains "
        "under its own licence; see config/data_sources.yaml."
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"provenance written to {path}")


def download_parser_models(
    config: Config, languages: list[str], manifest: dict[str, Any]
) -> int:
    """Fetch Stanza pipelines for each language, with their dependencies."""
    try:
        import stanza
    except ImportError:
        print("stanza is not installed; `pip install -e '.[parse]'`", file=sys.stderr)
        return 1

    source = config.get("data_sources.sources.stanza_models", {}) or {}
    target = config.stanza_dir
    target.mkdir(parents=True, exist_ok=True)

    failures = 0
    for language in languages:
        print(f"\n=== Stanza models for {language!r} -> {target}")
        try:
            # Two passes, because `package="default"` alone is not reliable: it can
            # report success while leaving out a model the pipeline needs at load time.
            # Vietnamese is the case in point - its dependency parser requires
            # pretrained embeddings and two character language models that the bundled
            # package did not bring, so the download "succeeded" and the pipeline then
            # refused to load. Naming the processors explicitly makes Stanza resolve
            # each one's declared dependencies.
            stanza.download(
                language, model_dir=str(target), package="default", verbose=True
            )
            processors = _processor_packages(config, target, language)
            if processors:
                print(f"  resolving dependencies for {sorted(processors)}")
                try:
                    stanza.download(
                        language,
                        model_dir=str(target),
                        processors=processors,
                        package=None,
                        verbose=True,
                    )
                except Exception as exc:
                    # Best-effort top-up. The package download above is the primary
                    # route; verification below is what decides whether this language
                    # actually works, so a failure here is informational.
                    print(f"  dependency pass skipped: {exc}")
        except Exception as exc:
            print(f"  failed: {exc}", file=sys.stderr)
            failures += 1
            continue

        present = sorted(
            str(path.relative_to(target))
            for path in (target / language).rglob("*")
            if path.is_file()
        )
        record(
            manifest,
            {
                "name": "stanza_models",
                "language": language,
                "provider": source.get("provider", "Stanford NLP"),
                "homepage": source.get("homepage"),
                "version": source.get("version"),
                "license": source.get("license"),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "destination": str(target / language),
                "files": present,
            },
        )
        print(f"  {len(present)} files present")

    return failures


def _processor_packages(
    config: Config, target: Path, language: str
) -> dict[str, str]:
    """Map each processor SPLM needs to the package name Stanza should fetch.

    Read from Stanza's own resource index so the package names stay correct as models
    are revised, and restricted to the processors ``config/app.yaml`` asks for.
    """
    index_path = target / "resources.json"
    if not index_path.is_file():
        return {}
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

    entry = index.get(language, {})
    defaults = entry.get("default_processors", {}) or {}
    wanted = str(
        (config.get("app.parser.processors", {}) or {}).get(language, "tokenize,pos,lemma,depparse")
    ).split(",")

    return {
        processor: defaults[processor]
        for processor in (name.strip() for name in wanted)
        if processor in defaults
    }


def verify_parser_models(config: Config, languages: list[str]) -> int:
    """Load each pipeline and parse one sentence.

    A download that leaves a pipeline unloadable is a failed download, so this is part
    of the job rather than a separate check.
    """
    from splm.linguistic.factory import build_parser

    parser = build_parser(config)
    probes = {
        "en": "John met Sarah in Paris yesterday.",
        "fr": "Jean a rencontré Sarah à Paris hier.",
        "vi": "Hôm qua John đã gặp Sarah ở Paris.",
    }

    failures = 0
    for language in languages:
        text = probes.get(language, "Test.")
        try:
            document = parser.parse(text, language)
            sentence = document.sentences[0] if document.sentences else None
            if sentence is None or not sentence.tokens:
                raise RuntimeError("pipeline returned no tokens")
            print(f"  {language}: OK ({len(sentence.tokens)} words parsed)")
        except Exception as exc:
            print(f"  {language}: UNUSABLE - {str(exc).splitlines()[0]}", file=sys.stderr)
            failures += 1
    return failures


def download_base_model(config: Config, manifest: dict[str, Any]) -> int:
    """Fetch the configured Transformer weights into the local cache."""
    model_cfg = config.model
    model_id = model_cfg.get("model_id")
    if not model_id:
        print("no model.model_id configured", file=sys.stderr)
        return 1

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        print("transformers is not installed; `pip install -e '.[llm]'`", file=sys.stderr)
        return 1

    print(f"\n=== base model {model_id}")
    kwargs: dict[str, Any] = {}
    if model_cfg.get("cache_dir"):
        kwargs["cache_dir"] = model_cfg["cache_dir"]

    try:
        AutoTokenizer.from_pretrained(model_id, **kwargs)
        AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    except Exception as exc:
        print(f"  failed: {exc}", file=sys.stderr)
        return 1

    record(
        manifest,
        {
            "name": "base_model",
            "language": None,
            "provider": "Hugging Face Hub",
            "homepage": f"https://huggingface.co/{model_id}",
            "version": model_id,
            "license": "see the model card on the Hub",
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "destination": model_cfg.get("cache_dir") or "Hugging Face default cache",
        },
    )
    print("  cached")
    return 0


def report_pending(config: Config) -> None:
    """List resources SPLM would use but which have no automated fetch yet."""
    sources = config.get("data_sources.sources", {}) or {}
    pending = {
        name: spec
        for name, spec in sources.items()
        if name not in {"stanza_models"} and spec.get("fetch") in {"http", "git"}
    }
    if not pending:
        return

    print("\n=== not fetched by this script")
    for name, spec in pending.items():
        print(f"  {name}")
        print(f"    {spec.get('url', spec.get('homepage', ''))}")
        print(f"    licence: {spec.get('license')}   needed for: {spec.get('required_for')}")
    print(
        "\n  These are large and licence-varied, so they are fetched by their own\n"
        "  builders (scripts/build_lexicon.py, scripts/build_database.py) once you\n"
        "  have reviewed the licences. Until then the lexicon stays empty and every\n"
        "  lexical feature reports 'no evidence' rather than guessing."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", nargs="*", default=None)
    parser.add_argument("--model", action="store_true", help="also fetch the base LLM")
    parser.add_argument("--all", action="store_true", help="parser models and base LLM")
    parser.add_argument("--list", action="store_true", help="show configured sources and exit")
    parser.add_argument("--verify-only", action="store_true", help="check existing models")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    setup_logging(level=args.log_level)
    config = Config.load()
    languages = args.languages or config.supported_languages

    if args.list:
        sources = config.get("data_sources.sources", {}) or {}
        for name, spec in sources.items():
            print(f"{name}")
            print(f"  provider : {spec.get('provider')}")
            print(f"  version  : {spec.get('version')}")
            print(f"  licence  : {spec.get('license')}")
            print(f"  fetch    : {spec.get('fetch')}")
            print(f"  needed   : {spec.get('required_for')}")
        return 0

    manifest_path = ROOT / str(config.get("data_sources.manifest", "data/MANIFEST.json"))
    manifest = load_manifest(manifest_path)
    failures = 0

    if not args.verify_only:
        failures += download_parser_models(config, languages, manifest)

    print("\n=== verifying pipelines load and parse")
    failures += verify_parser_models(config, languages)

    if (args.model or args.all) and not args.verify_only:
        failures += download_base_model(config, manifest)

    if not args.verify_only:
        save_manifest(manifest_path, manifest)

    report_pending(config)

    if failures:
        print(f"\n{failures} problem(s); see messages above", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
