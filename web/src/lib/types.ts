/**
 * Types mirroring the MLM API responses.
 *
 * Fields are optional wherever the backend can legitimately return nothing -
 * an unbuilt lexicon, an unparsed sentence, a metric with too little coverage
 * to report. The UI must render those as "not available", never as zero.
 */

export type SlotName =
  | "subject"
  | "predicate"
  | "objects"
  | "recipients"
  | "participants"
  | "location"
  | "destination"
  | "source"
  | "time"
  | "manner"
  | "instrument"
  | "cause"
  | "goal"
  | "condition";

export interface LanguageInfo {
  code: string;
  confidence: number;
  backend: string;
  script: string | null;
  locale: string | null;
  scores: Record<string, number>;
}

export interface RoleAlternative {
  role: string;
  probability: number;
}

export interface FrameElement {
  text: string;
  head_lemma: string;
  semantic_role: string;
  confidence: number;
  entity_type: string | null;
  token_indices: number[];
  features: Record<string, unknown>;
  annotations: Record<string, unknown>;
  alternatives: RoleAlternative[];
  deprel: string | null;
  frame: PhraseFrame | null;
}

export interface Predicate {
  type: string;
  lemma: string;
  text: string;
  sense: string | null;
  token_index: number | null;
  confidence: number;
}

export interface PhraseFrame {
  language: string;
  locale: string | null;
  style: string | null;
  text: string;
  predicate: Predicate | null;
  subject: FrameElement[];
  objects: FrameElement[];
  recipients: FrameElement[];
  participants: FrameElement[];
  location: FrameElement[];
  destination: FrameElement[];
  source: FrameElement[];
  time: FrameElement[];
  manner: FrameElement[];
  instrument: FrameElement[];
  cause: FrameElement[];
  goal: FrameElement[];
  condition: FrameElement[];
  tense: string | null;
  aspect: string | null;
  modality: string | null;
  voice: string | null;
  negation: boolean;
  certainty: number | null;
  intent: string | null;
  emotion: string | null;
  unresolved_slots: string[];
  dangling_marker: string | null;
  relation_to_parent: string | null;
  children: PhraseFrame[];
  notes: string[];
}

export interface SlotPrediction {
  distribution: Record<string, number>;
  top_slot: string;
  confidence: number;
  entropy: number;
  normalized_entropy: number;
  confidence_label: "high" | "medium" | "ambiguous";
  filled_slots: string[];
  missing_slots: string[];
  dangling_marker: string | null;
  evidence: string[];
  backend: string;
}

export interface DependencyToken {
  index: number;
  text: string;
  lemma: string;
  upos: string;
  xpos: string | null;
  feats: Record<string, string>;
  head: number;
  deprel: string;
  entity_type: string | null;
  ner: string | null;
}

export interface FeatureContribution {
  feature: string;
  value: number;
  weight: number;
  contribution: number;
  informative: boolean;
  enabled: boolean;
}

export interface PosEstimate {
  pos: string | null;
  confidence: number;
  basis: string | null;
}

export interface Candidate {
  token: string;
  word: string;
  token_id: number;
  base_rank: number;
  splm_rank: number;
  base_logit: number;
  splm_logit: number;
  base_probability: number;
  splm_probability: number;
  probability: number;
  delta_logit: number;
  rank_change: number;
  direction: "up" | "down" | "same";
  features: Record<string, number>;
  informative: Record<string, boolean>;
  contributions: FeatureContribution[];
  slot_compatibility: Record<string, number>;
  best_slot: string | null;
  pos_estimate: PosEstimate;
  lexical_status: string | null;
  reasons: string[];
}

export interface FunnelStage {
  name: string;
  count: number;
  hard: boolean;
  label: string;
  note: string;
}

export interface SearchSpace {
  vocabulary_size: number;
  candidates_considered: number;
  stages: FunnelStage[];
  hard_reduction_percent: number;
}

export interface SemanticFocus {
  slot: string;
  base_mass: number;
  splm_mass: number;
  evaluated: number;
  total: number;
  compatible_count: number;
  coverage_note: string;
  delta_percentage_points: number;
  coverage: number;
  reportable: boolean;
}

export interface Relevance {
  slot: string;
  top_k: number;
  base_compatible: number;
  splm_compatible: number;
  base_incompatible: number;
  splm_incompatible: number;
  evaluated: number;
  base_ratio: number;
  splm_ratio: number;
  base_noise: number;
  splm_noise: number;
}

export interface TargetOutcome {
  target: string;
  found: boolean;
  base_rank: number | null;
  splm_rank: number | null;
  base_probability: number | null;
  splm_probability: number | null;
  boost_logits: number | null;
  matched_token: string | null;
  rank_improvement: number | null;
  verdict: "win" | "loss" | "tie" | "not_found";
}

export interface MassByCategory {
  base: Record<string, number>;
  splm: Record<string, number>;
  unclassified_base: number;
  unclassified_splm: number;
}

export interface RankingChange {
  token: string;
  word: string;
  base_rank: number;
  splm_rank: number;
  change: number;
  direction: "up" | "down" | "same";
  delta_logit: number;
}

export interface ComparisonResponse {
  prompt: string;
  language: string;
  style: string | null;
  warm: boolean;
  fingerprint: string;
  semantics_coverage: string;
  phrase_frame: PhraseFrame | null;
  phrase_frame_compact: Record<string, unknown> | null;
  frame_completion: number;
  expected_slots: SlotPrediction;
  base: { candidates: Candidate[]; top: string | null };
  splm: { candidates: Candidate[]; top: string | null };
  changed_selection: boolean;
  search_space: SearchSpace | null;
  semantic_focus: SemanticFocus | null;
  relevance: Relevance | null;
  mass_by_category: MassByCategory | null;
  target: TargetOutcome | null;
  timings_ms: Record<string, number>;
  total_latency_ms: number;
  splm_overhead_ms: number;
  warnings: string[];
  ranking_changes?: RankingChange[];
}

export interface AnalyzeResponse {
  language: LanguageInfo;
  style: string | null;
  style_confidence: number | null;
  phrase_frame: PhraseFrame | null;
  frames: PhraseFrame[];
  dependencies: DependencyToken[];
  conllu: string | null;
  morphology: Record<string, Record<string, unknown>>;
  entities: { text: string; type: string; raw: string; index: number }[];
  unresolved_slots: string[];
  dangling_marker: string | null;
  expected_slots: SlotPrediction;
  timings_ms: Record<string, number>;
  warnings: string[];
}

export interface SystemResponse {
  model: Record<string, unknown> & {
    model_id?: string;
    device?: string;
    dtype?: string;
    parameters?: number;
    vocab_size?: number;
    tokenizer?: string;
  };
  fingerprint: string;
  weights: Record<string, number>;
  features: Record<string, boolean>;
  scorer_backend: string;
  scorer_trained: boolean;
  slot_backend: string;
  slot_trained: boolean;
  language_packs: Record<string, { version: unknown; semantics_coverage: string }>;
  universal_pack_version: unknown;
  lexicon: {
    available: boolean;
    note?: string;
    tables?: Record<string, number>;
    loading?: {
      auto_download: boolean;
      languages: Record<string, { state: string; detail: string }>;
    };
  };
  hardware: Record<string, unknown>;
  supported_languages: string[];
  ablation_presets: string[];
}

export interface AblationRun {
  label: string;
  features: Record<string, boolean>;
  top_token: string | null;
  top_probability: number | null;
  target: TargetOutcome | null;
  semantic_focus: SemanticFocus | null;
  candidates: {
    word: string;
    token: string;
    splm_rank: number;
    base_rank: number;
    probability: number;
    delta_logit: number;
  }[];
  latency_ms: number;
}

export interface MultilingualResponse {
  languages: Record<
    string,
    {
      text: string;
      parsed: boolean;
      warnings: string[];
      token_count: number | null;
      frame?: Record<string, unknown>;
      signature?: Record<string, unknown>;
    }
  >;
  agreement: Record<string, number>;
  metric: string;
}

export interface GraphNode {
  id: string;
  kind: string;
  label: string;
  entity_type: string | null;
  lemma: string | null;
  sentence_index: number;
  features: Record<string, unknown>;
  mentions: string[];
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  confidence: number;
  sentence_index: number;
}

export interface ContextResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  coreferences: {
    mention: string;
    sentence_index: number;
    resolved_to: string | null;
    resolved_label: string | null;
    confidence: number;
    alternatives: string[];
  }[];
  summary: Record<string, unknown>;
  sentences: string[];
  raw_token_count: number | null;
  graph_token_count: number;
  token_count_note?: string;
}

export interface Preset {
  label: string;
  prompt: string;
  category: string;
  language: string;
}

export interface BenchmarkSummary {
  run_id: string;
  timestamp: string;
  model: string;
  fingerprint: string;
  languages: string[];
  samples: number;
  dataset: string;
  headline: string[];
  path: string;
}

export interface MetricSummary {
  metric: string;
  base: Record<string, number>;
  splm: Record<string, number>;
  difference_pp: number;
  relative_difference: number | null;
  p_value: number | null;
  base_only_correct: number;
  splm_only_correct: number;
  intervals_overlap: boolean;
  verdict:
    | "splm_improved"
    | "no_meaningful_difference"
    | "base_better"
    | "insufficient_data";
  statement: string;
  note: string;
}

export interface BenchmarkReport {
  run_id: string;
  timestamp: string;
  dataset: string;
  dataset_note: string;
  languages: string[];
  samples: number;
  skipped: number;
  model: Record<string, unknown>;
  fingerprint: string;
  features: Record<string, boolean>;
  weights: Record<string, number>;
  environment: Record<string, unknown>;
  semantics_coverage: Record<string, string>;
  slot_accuracy: (Record<string, number> & { note?: string }) | null;
  slot_accuracy_top3: Record<string, number> | null;
  slot_by_category: Record<string, Record<string, number>>;
  slot_confusion: {
    labels?: string[];
    counts?: Record<string, Record<string, number>>;
    per_slot?: Record<string, Record<string, unknown>>;
    common_errors?: { true: string; predicted: string; count: number }[];
  };
  comparisons: MetricSummary[];
  rank_metrics: Record<string, unknown>;
  win_loss: Record<string, number | string>;
  continuous: Record<string, unknown>[];
  multilingual: Record<string, unknown>;
  headline: string[];
  caveats: string[];
  items: Record<string, unknown>[];
}
