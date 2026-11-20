/**
 * Speech Lab client: types mirror src/splm/speech/pipeline.py and api/speech.py.
 */

import type { PhraseFrame } from "./types";
import { post, request } from "./api";

export type SpeechMode = "base" | "nplm" | "nplm_validated";
export type SpeechLanguage = "en" | "fr" | "vi";

export const MODE_LABELS: Record<SpeechMode, { short: string; name: string; pipeline: string }> = {
  base: { short: "A", name: "Base Transformer", pipeline: "Whisper → LLM → TTS" },
  nplm: { short: "B", name: "NPLM", pipeline: "Whisper → NPLM (LLM + Phrase DNA scoring) → TTS" },
  nplm_validated: {
    short: "C",
    name: "NPLM + validation",
    pipeline: "Whisper n-best → Phrase DNA checks → NPLM → TTS",
  },
};

export const LANGUAGE_LABELS: Record<SpeechLanguage, string> = {
  en: "English",
  fr: "Français",
  vi: "Tiếng Việt",
};

export interface DnaItem {
  text: string;
  slot: string;
  role: string | null;
  confidence: number;
  entity_type: string | null;
}

export interface DnaCategory {
  key: string;
  label: string;
  items: DnaItem[];
  missing: boolean;
}

export interface DnaSortData {
  text: string;
  language: string;
  categories: DnaCategory[];
  predicate_kind: "action" | "status" | null;
  tense: string | null;
  modality: string | null;
  negation: boolean;
  intent: string | null;
  unsorted: string[];
  clauses: DnaSortData[];
}

export interface Hypothesis {
  text: string;
  score: number;
  rank: number;
}

export interface ScoredHypothesis {
  text: string;
  rank: number;
  acoustic: number;
  has_predicate: boolean;
  completeness: number;
  unresolved: number;
  consensus: number;
  total: number;
  eligible: boolean;
  critical: string[];
}

export interface ValidationData {
  chosen: string;
  chosen_rank: number;
  changed: boolean;
  scored: ScoredHypothesis[];
  critical_items: { text: string; kind: string; agreement: number }[];
  warnings: string[];
  latency_ms: number;
}

export interface SpeechTurn {
  mode: SpeechMode;
  language: string | null;
  transcript: string;
  asr: {
    hypotheses: Hypothesis[];
    language: string | null;
    language_source: string;
    audio_seconds: number;
    latency_ms: number;
    model_id: string | null;
  } | null;
  validation: ValidationData | null;
  dna: DnaSortData | null;
  phrase_frame: PhraseFrame | null;
  clarification: { question: string; missing: string; reason: string } | null;
  response_text: string;
  response_source: "generation" | "clarification" | "none";
  response_dna: DnaSortData | null;
  audio_wav_base64: string | null;
  audio_seconds: number;
  timings_ms: Record<string, number>;
  rtf: Record<string, number | null>;
  tokens_generated: number;
  memory: Record<string, number | null>;
  settings: Record<string, unknown>;
  warnings: string[];
}

export interface TurnResponse {
  turns: Partial<Record<SpeechMode, SpeechTurn>>;
  shared_asr: boolean;
  note?: string;
}

export interface ProvenanceRow {
  role: string;
  language: string | null;
  model_id: string;
  source: string;
  licence: string;
  revision: string | null;
  verified: boolean;
  verified_at: string | null;
  verification: string | null;
}

export interface SpeechStatus {
  available: boolean;
  reason?: string;
  provenance: ProvenanceRow[];
  modes?: Record<SpeechMode, string>;
  asr?: { model_id: string; loaded: boolean; device: string; num_beams: number; n_best: number };
  tts?: { voices: Record<string, string>; loaded: string[] };
  answer_model?: string;
  generation?: Record<string, unknown>;
  languages?: string[];
  warm?: boolean;
  warming?: boolean;
  warmup_error?: string | null;
}

export interface SpeechBenchmarkSummary {
  run_id: string;
  timestamp: string | null;
  dataset: string | null;
  samples: number | null;
  languages: string[] | null;
  headline: string[] | null;
}

export interface ProportionSummary {
  successes: number;
  total: number;
  value: number;
  percent: number;
  ci_low: number;
  ci_high: number;
}

export interface SpeechBenchmarkReport {
  run_id: string;
  timestamp: string;
  dataset: string;
  synthetic: boolean;
  samples: number;
  languages: string[];
  hardware: Record<string, unknown>;
  per_mode: Record<
    SpeechMode,
    {
      items: number;
      corpus_wer: number | null;
      mean_cer: number | null;
      slot_accuracy: ProportionSummary;
      entity_preservation: ProportionSummary;
      number_preservation: ProportionSummary;
      generation_ms: number | null;
      time_to_first_audio_ms: number | null;
      end_to_end_ms: number | null;
      rtf_end_to_end: number | null;
      rtf_asr: number | null;
      peak_rss_mb: number | null;
      clarifications: number;
      validation_changed: number;
    }
  >;
  comparisons: {
    transcript: Record<string, { statement?: string; verdict?: string; metric: string }>;
    generation: Record<string, { metric: string; base_mean: number; splm_mean: number; difference: number; samples: number }>;
  };
  headline: string[];
  caveats: string[];
}

export const speechApi = {
  status: (warm = false) => request<SpeechStatus>(`/api/speech/status${warm ? "?warm=true" : ""}`),
  turn: (body: {
    audio_base64?: string | null;
    text?: string | null;
    mode: SpeechMode | "compare";
    language?: SpeechLanguage | null;
    speak?: boolean;
  }) => post<TurnResponse>("/api/speech/turn", body),
  benchmarks: () => request<{ results: SpeechBenchmarkSummary[] }>("/api/speech/benchmark/results"),
  benchmark: (runId: string) =>
    request<SpeechBenchmarkReport>(`/api/speech/benchmark/results/${encodeURIComponent(runId)}`),
};

/** Blob -> base64 (no data: prefix). */
export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
