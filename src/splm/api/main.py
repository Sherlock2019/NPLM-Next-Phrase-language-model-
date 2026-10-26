"""FastAPI service backing the SPLM dashboard (UI spec sections 40-43).

Every response is computed from the running system. There is no mock data and no
generated prose: explanations are assembled from the scorer's own feature values, so
the UI cannot show a reason the engine did not actually use.

Run with::

    python -m splm.api.main
    # or: uvicorn splm.api.main:app --reload
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from splm.config import Config
from splm.logging_utils import setup_logging

logger = logging.getLogger(__name__)

API_PREFIX = "/api"


# ---------------------------------------------------------------------------
# request models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1)
    language: str | None = None
    locale: str | None = None
    style: str | None = None
    update_context: bool = False


class PredictRequest(BaseModel):
    prompt: str = Field(min_length=1)
    language: str | None = None
    style: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=1000)
    display_k: int = Field(default=15, ge=1, le=200)
    target: str | None = Field(
        default=None, description="Known correct continuation, for rank metrics"
    )


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    language: str | None = None
    max_new_tokens: int = Field(default=24, ge=1, le=512)
    temperature: float | None = Field(default=None, ge=0.0, le=4.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=1000)
    seed: int | None = None


class AblationRequest(PredictRequest):
    features: dict[str, bool] | None = Field(
        default=None, description="Per-feature switches; omitted features keep config values"
    )
    preset: str | None = Field(default=None, description="Named preset from scoring.yaml")
    cumulative: bool = Field(
        default=False,
        description="Run the standard LLM-only -> everything ladder instead of one setting",
    )


class MultilingualRequest(BaseModel):
    texts: dict[str, str] = Field(description="language code -> sentence")


class ContextRequest(BaseModel):
    text: str = Field(min_length=1)
    language: str | None = None


# ---------------------------------------------------------------------------
# application
# ---------------------------------------------------------------------------

def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.load()
    setup_logging(config)

    app = FastAPI(
        title="Meaning Language Model",
        version="0.1.0",
        description=(
            "Explicit linguistic structure over a pretrained Transformer. "
            "All figures are measured at request time; none are precomputed or illustrative."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        # The dashboard is served from a separate dev server during development.
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    state: dict[str, Any] = {"config": config, "engine": None}

    def engine() -> Any:
        """The shared engine, warmed on first use."""
        if state["engine"] is None:
            from splm.model.engine import SPLMEngine

            instance = SPLMEngine(state["config"])
            try:
                instance.warmup()
            except Exception as exc:
                logger.warning("warmup incomplete: %s", exc)
            state["engine"] = instance
        return state["engine"]

    def engine_with(overrides: Config) -> Any:
        """A throwaway engine for an ablation run, reusing loaded components.

        The parser and the weights differ, but the Transformer and its weights are
        shared, so an ablation comparison is never confounded by a different model.
        """
        from splm.model.engine import SPLMEngine

        base = engine()
        return SPLMEngine(
            overrides,
            pipeline=base.pipeline,
            llm=base.llm,
            lexicon=base.lexicon,
        )

    # -- system ------------------------------------------------------------

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "engine_loaded": state["engine"] is not None}

    @app.get(f"{API_PREFIX}/system")
    def system() -> dict[str, Any]:
        """Model, device, versions and knowledge-base status (UI spec section 32)."""
        from splm.device import device_report

        cfg: Config = state["config"]
        info = engine().describe()
        info["hardware"] = device_report()
        info["supported_languages"] = cfg.supported_languages
        info["ablation_presets"] = sorted(
            (cfg.get("scoring.ablations", {}) or {}).keys()
        )
        return info

    @app.get(f"{API_PREFIX}/lexicon")
    def lexicon() -> dict[str, Any]:
        """Which languages have a dictionary loaded, and which are still loading."""
        from splm.linguistic.lexicon_builder import lexicon_status

        return lexicon_status(state["config"])

    @app.post(f"{API_PREFIX}/lexicon/{{language}}")
    def load_lexicon(language: str) -> dict[str, Any]:
        """Load the dictionary for a chosen language, without waiting for a prompt."""
        from splm.linguistic.lexicon_builder import ensure_lexicon

        cfg: Config = state["config"]
        if language not in cfg.supported_languages:
            raise HTTPException(status_code=404, detail=f"unsupported language {language!r}")
        return ensure_lexicon(cfg, language)

    @app.get(f"{API_PREFIX}/models")
    def models() -> dict[str, Any]:
        cfg: Config = state["config"]
        return {
            "active": cfg.model,
            "profiles": cfg.get("model.profiles", {}) or {},
            "note": (
                "Switching model requires a restart with SPLM_MODEL_ID or a changed "
                "config/model.yaml; weights are not hot-swapped."
            ),
        }

    @app.get(f"{API_PREFIX}/presets")
    def presets() -> dict[str, Any]:
        """Example prompts for the UI's preset buttons (UI spec section 34)."""
        return {"presets": PRESETS}

    # -- analysis ----------------------------------------------------------

    @app.post(f"{API_PREFIX}/analyze")
    def analyze(request: AnalyzeRequest) -> dict[str, Any]:
        """Language, style, dependencies, morphology, Phrase DNA, expected slots."""
        from splm.phrase.slot_predictor import SlotContext

        instance = engine()
        analysis = instance.pipeline.analyze(
            request.text,
            language=request.language,
            locale=request.locale,
            style=request.style,
            update_context=request.update_context,
        )
        slots = instance.slot_predictor.predict(
            SlotContext(
                text=request.text,
                language=analysis.language,
                frame=analysis.frame,
                sentence=analysis.sentence,
                style=analysis.style,
            )
        )

        sentence = analysis.sentence
        morphology = analysis.morphology[-1] if analysis.morphology else {}

        return {
            "language": {
                "code": analysis.detection.language,
                "confidence": analysis.detection.confidence,
                "backend": analysis.detection.backend,
                "script": analysis.detection.script,
                "locale": analysis.detection.locale,
                "scores": analysis.detection.scores,
            },
            "style": analysis.style,
            "style_confidence": analysis.style_confidence,
            "phrase_frame": (
                analysis.frame.model_dump(mode="json") if analysis.frame else None
            ),
            "phrase_frame_compact": (
                analysis.frame.to_compact_dict() if analysis.frame else None
            ),
            "frames": [f.model_dump(mode="json") for f in analysis.frames],
            "dependencies": (
                [t.model_dump() for t in sentence.tokens] if sentence else []
            ),
            "conllu": sentence.to_conllu() if sentence else None,
            "morphology": {
                str(index): value.model_dump(exclude_none=True)
                for index, value in morphology.items()
            },
            "entities": (
                [
                    {"text": t.text, "type": t.entity_type, "raw": t.ner, "index": t.index}
                    for t in sentence.tokens
                    if t.entity_type
                ]
                if sentence
                else []
            ),
            "unresolved_slots": (
                analysis.frame.unresolved_slots if analysis.frame else []
            ),
            "dangling_marker": (
                analysis.frame.dangling_marker if analysis.frame else None
            ),
            "expected_slots": slots.model_dump(),
            "timings_ms": analysis.timings_ms,
            "warnings": analysis.warnings,
        }

    # -- prediction --------------------------------------------------------

    @app.post(f"{API_PREFIX}/predict/base")
    def predict_base(request: PredictRequest) -> dict[str, Any]:
        """Base-model candidates only - no structural layer involved."""
        instance = engine()
        candidates = instance.llm.get_top_candidates(
            request.prompt, k=request.top_k or instance.llm.top_k_candidates
        )
        return {
            "prompt": request.prompt,
            "model": instance.llm.model_id,
            "candidates": [
                {
                    "token": c.token,
                    "word": c.stripped,
                    "token_id": c.token_id,
                    "rank": c.rank,
                    "logit": round(c.logit, 4),
                    "probability": round(c.probability, 6),
                }
                for c in candidates[: request.display_k]
            ],
            "total_candidates": len(candidates),
            "vocabulary_size": instance.llm.vocab_size,
        }

    @app.post(f"{API_PREFIX}/predict/splm")
    def predict_splm(request: PredictRequest) -> dict[str, Any]:
        result = engine().predict(
            request.prompt,
            language=request.language,
            style=request.style,
            top_k=request.top_k,
            target=request.target,
        )
        return _serialise_prediction(result, request.display_k)

    @app.post(f"{API_PREFIX}/compare")
    def compare(request: PredictRequest) -> dict[str, Any]:
        """Base and SPLM from one forward pass (UI spec section 42).

        Both columns come from the same logits, so the only difference between them is
        the re-scoring layer - not sampling, not a second inference call.
        """
        result = engine().predict(
            request.prompt,
            language=request.language,
            style=request.style,
            top_k=request.top_k,
            target=request.target,
        )
        payload = _serialise_prediction(result, request.display_k)
        payload["ranking_changes"] = [
            {
                "token": score.token,
                "word": score.word,
                "base_rank": score.base_rank,
                "splm_rank": score.splm_rank,
                "change": score.rank_change,
                "direction": score.direction,
                "delta_logit": score.delta_logit,
            }
            for score in result.rank_changes(limit=request.display_k)
        ]
        return payload

    # -- generation --------------------------------------------------------

    @app.post(f"{API_PREFIX}/generate/base")
    def generate_base(request: GenerateRequest) -> dict[str, Any]:
        return _generate(engine(), request, use_splm=False)

    @app.post(f"{API_PREFIX}/generate/splm")
    def generate_splm(request: GenerateRequest) -> dict[str, Any]:
        return _generate(engine(), request, use_splm=True)

    @app.post(f"{API_PREFIX}/generate/compare")
    def generate_compare(request: GenerateRequest) -> dict[str, Any]:
        """Two continuations, identical settings, only the SPLM layer differing."""
        instance = engine()
        base = _generate(instance, request, use_splm=False)
        splm = _generate(instance, request, use_splm=True)
        return {
            "prompt": request.prompt,
            "base": base,
            "splm": splm,
            "identical": base["continuation"] == splm["continuation"],
            "settings": {
                "model": instance.llm.model_id,
                "max_new_tokens": request.max_new_tokens,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "seed": request.seed,
            },
        }

    # -- ablation ----------------------------------------------------------

    @app.post(f"{API_PREFIX}/ablation")
    def ablation(request: AblationRequest) -> dict[str, Any]:
        """Run the same prompt under different feature switches (spec section 39)."""
        cfg: Config = state["config"]

        if request.cumulative:
            ladder = [
                ("LLM only", "base_only"),
                ("+ grammar", "grammar_only"),
                ("+ syntax", "syntax_only"),
                ("+ Phrase DNA", "phrase_only"),
                ("+ Phrase DNA + grammar", "phrase_grammar"),
                ("everything", "everything"),
            ]
            runs = []
            for label, preset in ladder:
                try:
                    variant = cfg.ablation(preset)
                except KeyError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                runs.append((label, variant))
        elif request.preset:
            try:
                runs = [(request.preset, cfg.ablation(request.preset))]
            except KeyError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        elif request.features is not None:
            runs = [("custom", cfg.with_features(request.features))]
        else:
            runs = [("configured", cfg)]

        results = []
        for label, variant in runs:
            result = engine_with(variant).predict(
                request.prompt,
                language=request.language,
                top_k=request.top_k,
                target=request.target,
            )
            top = result.top_splm(1)
            results.append(
                {
                    "label": label,
                    "features": variant.features,
                    "top_token": top[0].word if top else None,
                    "top_probability": round(top[0].splm_probability, 6) if top else None,
                    "target": result.target.model_dump() if result.target else None,
                    "semantic_focus": (
                        result.semantic_focus.model_dump()
                        if result.semantic_focus
                        else None
                    ),
                    "candidates": [
                        {
                            "word": s.word,
                            "token": s.token,
                            "splm_rank": s.splm_rank,
                            "base_rank": s.base_rank,
                            "probability": round(s.splm_probability, 6),
                            "delta_logit": s.delta_logit,
                        }
                        for s in result.top_splm(request.display_k)
                    ],
                    "latency_ms": result.total_latency_ms,
                }
            )

        return {"prompt": request.prompt, "runs": results}

    # -- multilingual ------------------------------------------------------

    @app.post(f"{API_PREFIX}/multilingual")
    def multilingual(request: MultilingualRequest) -> dict[str, Any]:
        """Frames for the same meaning in several languages, plus their agreement."""
        instance = engine()
        frames: dict[str, Any] = {}
        payload: dict[str, Any] = {"languages": {}}

        for language, text in request.texts.items():
            analysis = instance.pipeline.analyze(text, language=language)
            frame = analysis.frame
            entry: dict[str, Any] = {
                "text": text,
                "parsed": analysis.parsed,
                "warnings": analysis.warnings,
                "token_count": None,
            }
            try:
                entry["token_count"] = instance.llm.token_count(text)
            except Exception:
                pass

            if frame is not None:
                frames[language] = frame
                entry["frame"] = frame.to_compact_dict()
                entry["signature"] = frame.structural_signature()
            payload["languages"][language] = entry

        agreement: dict[str, float] = {}
        codes = sorted(frames)
        for index, left in enumerate(codes):
            for right in codes[index + 1 :]:
                agreement[f"{left}-{right}"] = frames[left].agreement_with(frames[right])
        payload["agreement"] = agreement
        payload["metric"] = (
            "Structural agreement over predicate type and sense, grammatical meaning, "
            "filled slots, roles, named entities and nesting depth. Content lemmas are "
            "excluded because they are language-specific; comparing them needs a "
            "cross-lingual concept inventory the POC does not have."
        )
        return payload

    # -- context graph -----------------------------------------------------

    @app.post(f"{API_PREFIX}/context")
    def context(request: ContextRequest) -> dict[str, Any]:
        """Build a context graph over multi-sentence text and resolve pronouns."""
        from splm.graph.context_graph import ContextGraph

        instance = engine()
        analysis = instance.pipeline.analyze(request.text, language=request.language)
        graph = ContextGraph()
        graph.add_frames(analysis.frames)

        payload = graph.to_dict()
        payload["sentences"] = [f.text for f in analysis.frames]
        payload["frames"] = [f.to_compact_dict() for f in analysis.frames]
        try:
            payload["raw_token_count"] = instance.llm.token_count(request.text)
            payload["graph_token_count"] = graph.serialized_token_estimate(
                instance.llm.tokenizer
            )
        except Exception:
            payload["raw_token_count"] = None
            payload["graph_token_count"] = graph.serialized_token_estimate()
            payload["token_count_note"] = "approximate: tokenizer unavailable"
        return payload

    # -- benchmark ---------------------------------------------------------

    @app.get(f"{API_PREFIX}/benchmark/results")
    def benchmark_results() -> dict[str, Any]:
        """Previously written benchmark runs, newest first. Never fabricated."""
        from splm.evaluation.store import list_results

        cfg: Config = state["config"]
        return {"results": list_results(cfg.results_dir)}

    @app.get(f"{API_PREFIX}/benchmark/results/{{run_id}}")
    def benchmark_result(run_id: str) -> dict[str, Any]:
        from splm.evaluation.store import load_result

        cfg: Config = state["config"]
        payload = load_result(cfg.results_dir, run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"no benchmark run {run_id!r}")
        return payload

    @app.post(f"{API_PREFIX}/benchmark")
    def run_benchmark(
        languages: list[str] | None = None,
        limit: int | None = None,
        suite: Literal["slots", "next_word", "all"] = "all",
    ) -> dict[str, Any]:
        """Run the built-in benchmark suite and persist the result."""
        from splm.evaluation.benchmark import Benchmark

        cfg: Config = state["config"]
        benchmark = Benchmark(cfg, engine=engine())
        report = benchmark.run(languages=languages, limit=limit, suite=suite)
        return report.model_dump()

    return app


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _serialise_prediction(result: Any, display_k: int) -> dict[str, Any]:
    """Shape a PredictionResult for the dashboard (UI spec section 43)."""
    return {
        "prompt": result.text,
        "language": result.language,
        "style": result.style,
        "warm": result.warm,
        "fingerprint": result.fingerprint,
        "semantics_coverage": result.semantics_coverage,
        "phrase_frame": result.frame.model_dump(mode="json") if result.frame else None,
        "phrase_frame_compact": result.frame.to_compact_dict() if result.frame else None,
        "frame_completion": result.frame_completion,
        "expected_slots": result.expected_slots.model_dump(),
        "base": {
            "candidates": [
                _serialise_candidate(score, "base") for score in result.top_base(display_k)
            ],
            "top": result.base_choice.word if result.base_choice else None,
        },
        "splm": {
            "candidates": [
                _serialise_candidate(score, "splm") for score in result.top_splm(display_k)
            ],
            "top": result.splm_choice.word if result.splm_choice else None,
        },
        "changed_selection": result.changed_selection,
        "search_space": (
            {
                **result.search_space.model_dump(),
                "hard_reduction_percent": result.search_space.hard_reduction_percent,
            }
            if result.search_space
            else None
        ),
        "semantic_focus": (
            {
                **result.semantic_focus.model_dump(),
                "delta_percentage_points": result.semantic_focus.delta_percentage_points,
                "coverage": round(result.semantic_focus.coverage, 4),
                "reportable": result.semantic_focus.is_reportable,
            }
            if result.semantic_focus
            else None
        ),
        "relevance": (
            {
                **result.relevance.model_dump(),
                "base_ratio": round(result.relevance.base_ratio, 4),
                "splm_ratio": round(result.relevance.splm_ratio, 4),
                "base_noise": round(result.relevance.base_noise, 4),
                "splm_noise": round(result.relevance.splm_noise, 4),
            }
            if result.relevance
            else None
        ),
        "mass_by_category": (
            result.mass_by_category.model_dump() if result.mass_by_category else None
        ),
        "target": (
            {
                **result.target.model_dump(),
                "rank_improvement": result.target.rank_improvement,
                "verdict": result.target.verdict,
            }
            if result.target
            else None
        ),
        "timings_ms": result.timings_ms,
        "total_latency_ms": result.total_latency_ms,
        "splm_overhead_ms": result.splm_overhead_ms,
        "warnings": result.warnings,
    }


def _serialise_candidate(score: Any, view: str) -> dict[str, Any]:
    features = score.features
    return {
        "token": score.token,
        "word": score.word,
        "token_id": score.token_id,
        "base_rank": score.base_rank,
        "splm_rank": score.splm_rank,
        "base_logit": round(score.base_logit, 4),
        "splm_logit": round(score.splm_logit, 4),
        "base_probability": round(score.base_probability, 6),
        "splm_probability": round(score.splm_probability, 6),
        "probability": round(
            score.base_probability if view == "base" else score.splm_probability, 6
        ),
        "delta_logit": score.delta_logit,
        "rank_change": score.rank_change,
        "direction": score.direction,
        "features": (
            {name: getattr(features, name) for name in _FEATURE_NAMES}
            if features
            else {}
        ),
        "informative": features.informative if features else {},
        "contributions": [c.model_dump() for c in score.contributions],
        "slot_compatibility": features.slot_compatibility if features else {},
        "best_slot": features.best_slot if features else None,
        "pos_estimate": features.pos_estimate.model_dump() if features else {},
        "lexical_status": features.lexical_status if features else None,
        # Reasons are assembled from the features above, never generated text.
        "reasons": score.reasons,
    }


_FEATURE_NAMES = (
    "llm",
    "phrase_slot",
    "grammar",
    "syntax",
    "morphology",
    "semantic",
    "lexicon",
    "style",
    "context",
)


def _generate(instance: Any, request: GenerateRequest, *, use_splm: bool) -> dict[str, Any]:
    import time

    options: dict[str, Any] = {"max_new_tokens": request.max_new_tokens}
    if request.temperature is not None:
        options["temperature"] = request.temperature
        options["do_sample"] = request.temperature > 0
    if request.top_p is not None:
        options["top_p"] = request.top_p
    if request.top_k is not None:
        options["top_k"] = request.top_k

    if request.seed is not None:
        try:
            import torch

            torch.manual_seed(request.seed)
        except ImportError:
            pass

    started = time.perf_counter()
    continuation = instance.generate(
        request.prompt,
        language=request.language,
        use_splm=use_splm,
        **options,
    )
    elapsed = (time.perf_counter() - started) * 1000

    tokens = 0
    try:
        tokens = instance.llm.token_count(continuation)
    except Exception:
        pass

    return {
        "system": "splm" if use_splm else "base",
        "continuation": continuation,
        "full_text": request.prompt + continuation,
        "latency_ms": round(elapsed, 1),
        "tokens_generated": tokens,
        "tokens_per_second": round(tokens / (elapsed / 1000), 2) if elapsed > 0 and tokens else None,
    }


#: Preset prompts for the UI (UI spec section 34). Each names the structure it probes.
PRESETS: list[dict[str, str]] = [
    {"label": "Simple action", "prompt": "John works at", "category": "action", "language": "en"},
    {"label": "Location", "prompt": "John will meet Sarah in", "category": "where", "language": "en"},
    {"label": "Time", "prompt": "The meeting will start", "category": "when", "language": "en"},
    {
        "label": "Instrument",
        "prompt": "The engineer deployed the application to AWS yesterday using",
        "category": "how",
        "language": "en",
    },
    {
        "label": "Purpose",
        "prompt": "Sarah traveled to Paris to",
        "category": "goal",
        "language": "en",
    },
    {
        "label": "Cause",
        "prompt": "She traveled to Paris because",
        "category": "why",
        "language": "en",
    },
    {
        "label": "Conditional",
        "prompt": "If Sarah arrives tomorrow,",
        "category": "condition",
        "language": "en",
    },
    {
        "label": "Negation",
        "prompt": "John did not meet Sarah in",
        "category": "negation",
        "language": "en",
    },
    {
        "label": "Ambiguous",
        "prompt": "John completed the job with",
        "category": "ambiguous",
        "language": "en",
    },
    {
        "label": "Business style",
        "prompt": "Sarah has requested the quarterly sales report for",
        "category": "style",
        "language": "en",
    },
    {"label": "French", "prompt": "Jean rencontrera Sarah à", "category": "where", "language": "fr"},
    {
        "label": "Vietnamese",
        "prompt": "Ngày mai John sẽ gặp Sarah ở",
        "category": "where",
        "language": "vi",
    },
]


app = create_app()


def main() -> None:
    import uvicorn

    config = Config.load()
    uvicorn.run(
        app,
        host=str(config.get("app.api.host", "127.0.0.1")),
        port=int(config.get("app.api.port", 8000)),
    )


if __name__ == "__main__":
    main()
