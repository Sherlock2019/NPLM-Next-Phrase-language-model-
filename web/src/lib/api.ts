/**
 * Typed client for the MLM API.
 *
 * Requests go to a relative /api path, which next.config.mjs proxies to the Python
 * service. Errors carry the backend's own detail message: a research tool must say
 * what actually failed rather than showing a generic message over stale numbers.
 */

import type {
  AblationRun,
  AnalyzeResponse,
  BenchmarkReport,
  BenchmarkSummary,
  ComparisonResponse,
  ContextResponse,
  MultilingualResponse,
  Preset,
  SystemResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (cause) {
    throw new ApiError(
      "Cannot reach the MLM API. Start it with `python -m splm.api.main`.",
      0,
    );
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // Response body was not JSON; the status text stands.
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export interface PredictOptions {
  prompt: string;
  language?: string | null;
  style?: string | null;
  top_k?: number | null;
  display_k?: number;
  target?: string | null;
}

export interface GenerateOptions {
  prompt: string;
  language?: string | null;
  max_new_tokens?: number;
  temperature?: number | null;
  top_p?: number | null;
  top_k?: number | null;
  seed?: number | null;
}

export interface GenerateComparison {
  prompt: string;
  base: GenerateArm;
  splm: GenerateArm;
  identical: boolean;
  settings: Record<string, unknown>;
}

export interface GenerateArm {
  system: "base" | "splm";
  continuation: string;
  full_text: string;
  latency_ms: number;
  tokens_generated: number;
  tokens_per_second: number | null;
}

export const api = {
  system: () => request<SystemResponse>("/api/system"),

  presets: () => request<{ presets: Preset[] }>("/api/presets"),

  analyze: (body: {
    text: string;
    language?: string | null;
    style?: string | null;
    update_context?: boolean;
  }) => post<AnalyzeResponse>("/api/analyze", body),

  compare: (body: PredictOptions) => post<ComparisonResponse>("/api/compare", body),

  predictSplm: (body: PredictOptions) =>
    post<ComparisonResponse>("/api/predict/splm", body),

  generateCompare: (body: GenerateOptions) =>
    post<GenerateComparison>("/api/generate/compare", body),

  ablation: (body: PredictOptions & { preset?: string; cumulative?: boolean; features?: Record<string, boolean> }) =>
    post<{ prompt: string; runs: AblationRun[] }>("/api/ablation", body),

  multilingual: (texts: Record<string, string>) =>
    post<MultilingualResponse>("/api/multilingual", { texts }),

  context: (body: { text: string; language?: string | null }) =>
    post<ContextResponse>("/api/context", body),

  benchmarkResults: () =>
    request<{ results: BenchmarkSummary[] }>("/api/benchmark/results"),

  benchmarkResult: (runId: string) =>
    request<BenchmarkReport>(`/api/benchmark/results/${encodeURIComponent(runId)}`),

  runBenchmark: (params: { suite?: string; limit?: number; languages?: string[] } = {}) => {
    const query = new URLSearchParams();
    if (params.suite) query.set("suite", params.suite);
    if (params.limit) query.set("limit", String(params.limit));
    (params.languages ?? []).forEach((language) => query.append("languages", language));
    const suffix = query.toString() ? `?${query}` : "";
    return post<BenchmarkReport>(`/api/benchmark${suffix}`, {});
  },
};

/** Percentage with a fixed number of decimals, or a dash when unavailable. */
export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function signedPp(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)} pp`;
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(value < 10 ? 1 : 0)} ms`;
}

export function compactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 })
    .format(value)
    .toLowerCase();
}

export function fullNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en").format(value);
}

/** Human label for a frame slot, matching the conceptual questions in the spec. */
export const SLOT_QUESTIONS: Record<string, string> = {
  subject: "WHO",
  predicate: "DOES WHAT",
  objects: "WHAT",
  recipients: "TO WHOM",
  participants: "WITH WHOM",
  location: "WHERE",
  destination: "WHERE TO",
  source: "FROM WHERE",
  time: "WHEN",
  manner: "HOW",
  instrument: "USING WHAT",
  cause: "WHY",
  goal: "FOR WHAT GOAL",
  condition: "UNDER WHAT CONDITIONS",
  OTHER: "SOMETHING ELSE",
};

export const SLOT_ORDER: string[] = [
  "subject",
  "predicate",
  "objects",
  "recipients",
  "participants",
  "location",
  "destination",
  "source",
  "time",
  "manner",
  "instrument",
  "cause",
  "goal",
  "condition",
];

export function slotLabel(slot: string): string {
  return SLOT_QUESTIONS[slot] ?? slot.toUpperCase();
}

export const FEATURE_LABELS: Record<string, string> = {
  llm: "Base Transformer",
  phrase_slot: "Phrase slot",
  grammar: "Grammar",
  syntax: "Syntax",
  morphology: "Morphology",
  semantic: "Semantic role",
  lexicon: "Lexicon",
  style: "Style",
  context: "Context",
};
