/**
 * Shape of public/demo/demo_results.json, produced by `acm demo --json` from the
 * real pipeline (MLM schemas + adapters replaying fixtures, ACM's simulator and
 * engine). Only the fields the page reads are typed.
 */

export type Status = "observed" | "inferred" | "assumed" | "predicted" | "unknown";

export interface MeaningField {
  value: string | null;
  status: Status;
  source: string;
}

export interface Meaning {
  evidence_kind: string;
  who?: MeaningField;
  action?: MeaningField;
  what?: MeaningField;
  to_whom?: MeaningField;
  where?: MeaningField;
  direction?: MeaningField;
  when?: MeaningField;
  how?: MeaningField;
  why?: MeaningField;
  observed_states?: { text: string; status: Status; source: string }[];
  proposed_action?: unknown;
  unknowns?: string[];
  evidence?: { type: string; ref: string; backend?: string }[];
  rejected_claims?: { claim: string; type?: string; reason: string }[];
  notes?: string[];
  parse_note?: string;
}

export interface CircleRow {
  about: string;
  text: string;
  basis: string; // rule | simulation | observation | unknown
  source?: string;
  reason?: string;
  needs?: string[];
}

export interface Circle {
  key: string;
  title: string;
  rows: CircleRow[];
  empty: string | null;
}

export interface Scenario {
  key: string;
  label: string;
  action: {
    id: string;
    predicate: string;
    actor: string | null;
    target: string;
    parameters: Record<string, { value: number; unit: string }>;
    destination: { x: number; y: number; unit: string } | null;
  } | null;
  events: { kind: string; entity_id: string; other_id?: string | null }[];
  final_positions: Record<string, [number, number] | null>;
  assumptions: { name: string; value?: unknown; unit?: string | null; reason: string }[];
  unknowns: string[];
  uncertainty: Record<string, string | null>;
  backend: { name: string; version: string };
  circles: Circle[];
  report_text: string;
  acm_json: unknown;
  decision_time_s: number | null;
}

export interface SceneEntity {
  id: string;
  class: string;
  attributes: Record<string, unknown>;
  status: Status;
  position: [number, number] | null;
  radius_m: number | null;
  extent: [number, number, number, number] | null;
  evidence: string[];
}

export interface SceneData {
  timestamp_s: number | null;
  entities: SceneEntity[];
  relations: { subject: string; relation: string; object: string; value?: unknown; status: Status; note?: string }[];
}

export interface Flow {
  input: Record<string, unknown>;
  meaning: Meaning;
  meaning_json: unknown;
  scene: SceneData;
  scenarios: Record<string, Scenario>;
}

export interface VideoFlow extends Flow {
  timeline: {
    id: string;
    predicate: string;
    start_s: number;
    end_s: number;
    causal_attribution: string;
    roles: Record<string, string[]>;
  }[];
  scripted_outcome: { t: number; scene: SceneData; label: string };
  comparison: { metrics: Record<string, any>; notes: string[] };
}

export interface SaleFlow {
  input: { text: string; context: string[] };
  meaning: Meaning;
  meaning_json: unknown;
  circles: Circle[];
  report_text: string;
  acm_json: unknown;
  note: string;
}

export interface DemoBundle {
  mode: "demo";
  badge: string;
  action_labels: Record<string, string>;
  flows: { text: Flow; image: Flow; video: VideoFlow; sale: SaleFlow };
}

export interface VideoScript {
  title: string;
  duration_s: number;
  checkpoint_s: number;
  events: { start_s: number; end_s: number; label: string }[];
}

export interface LiveStatus {
  live: { text: boolean; image: boolean; video: boolean };
  reasons: { text: string; image: string; video: string };
}

export const ACTION_KEYS = ["none", "push_edge", "move_center"] as const;
export type ActionKey = (typeof ACTION_KEYS)[number];
