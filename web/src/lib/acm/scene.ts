/**
 * Types for the ACM scene engine's JSON (acm.scene/1, acm.directions/1), as written by
 * `acm scene bundle` / `acm demo --json` into public/demo/scene_<id>.json, and returned by
 * POST /api/acm/scene/branches. The engine (Python, ACM repo: src/acm/scene) is the source of
 * truth; the dashboard only renders it.
 */

export type Source = "scenario_fact" | "authored_demo" | "generated_inference" | "unknown";
export type Status = "stated" | "possible" | "unknown" | "not_identified";
export type Valence = "positive" | "negative" | "mixed" | "undetermined";
export type Horizon = "immediate" | "later" | "unknown";
export type EventType = "action" | "dialogue" | "observation" | "state_change";

export interface Mark { id: string; label: string; x: number | null; y: number | null }
export interface Location { name: string; city: string | null; marks: Mark[] }
export interface Inference { kind: "thought" | "feeling" | "behaviour" | "reaction"; text: string; status: Status; source: Source }

export interface Actor {
  id: string; name: string; role: string;
  relationships: Record<string, string>;
  goals: string[]; preferences: string[]; constraints: string[];
  position: string | null; knows: string[]; unknown: string[];
  inferences: Inference[];
}

export interface SceneObject {
  id: string; label: string; kind: "physical" | "obligation"; description: string;
  owner: string | null; holder: string | null; position: string | null;
  attributes: Record<string, unknown>;
}

export interface Change { subject: string; attribute: string; value: unknown }

export interface SceneEvent {
  id: string; order: number; actor: string | null; type: EventType;
  verb: string | null; target: string | null; object: string | null;
  description: string; dialogue: string | null; voice: string | null; animation: string | null;
  effects: Change[]; source: Source;
}

export interface Scope { n: number; id: string; title: string; short: string }

/** ACM's world-model layers, bottom-up (acm.scene.layers). 0 is the event, 3 the router. */
export type LayerId = "action" | "physical" | "perception" | "routing" | "human_social" | "digital" | "business" | "society" | "planetary";
export interface WorldLayer {
  level: number; id: LayerId; icon: string; name: string; examines: string;
  osi: string; osi_role: string; engine: string; status: "working" | "partial" | "planned";
}
export interface Route { layer: LayerId; actors: string[]; objects: string[]; reasons: string[] }
export interface RoutingRow { event: string; routes: Route[] }

export interface Consequence {
  id: string; scope: string; layer: LayerId; affected: string[]; description: string; goal: string | null;
  evidence: string[]; status: Status; effect: Record<string, Valence>; horizon: Horizon;
  assumptions: string[]; questions: string[]; source: Source;
}

export interface Conflict { between: string[]; description: string; evidence: string[]; status: Status }

export type State = Record<string, Record<string, unknown>>;
export interface Step { event: string | null; state: State; changed: string[] }

export interface DirectionAction {
  order: number; event: string; type: EventType; verb: string | null; actor: string | null;
  target: string | null; object: string | null; text: string; dialogue: string | null;
  voice: string | null; animation: string | null; source: Source; player_supported: boolean;
}
export interface Directions {
  schema: "acm.directions/1"; scene: string; branch: string | null; title: string;
  actions: DirectionAction[]; assumptions: string[]; source: Source;
  unsupported: { event: string; verb: string | null; reason: string }[];
  [key: string]: unknown;
}

export interface Branch {
  id: string; title: string; parent: string; assumptions: string[]; summary: string;
  events: SceneEvent[];
  goal_changes: { actor: string; change: string; effect: Valence }[];
  inferences: Record<string, Inference[]>;
  consequences: Consequence[]; unknowns: string[]; plausibility: string; source: Source;
  /** Present in the bundle (authored branches); absent for model-generated ones. */
  timeline?: Step[];
  directions?: Directions;
}

export interface Scene {
  schema: "acm.scene/1"; id: string; title: string; description: string;
  /** The central action, drawn at the centre of the consequence radius. */
  action: string | null;
  location: Location; time: string; context: string[]; status: string;
  initial: Record<string, unknown>;
  actors: Actor[]; objects: SceneObject[]; events: SceneEvent[]; scopes: Scope[];
  unknowns: string[]; caveats: string[];
}

export interface SceneBundle {
  schema: "acm.scene/1";
  generated_by: string;
  scene: Scene;
  timeline: Step[];
  analysis: { scene: string; provider: string; source: Source; conflicts: Conflict[]; consequences: Consequence[] };
  branches: Branch[];
  directions: Directions;
  vocabulary: Record<string, string>;
  layers: WorldLayer[];
  /** For each scene event: which world layers, actors and objects examine it, and why. */
  routing: RoutingRow[];
  branch_routing: Record<string, RoutingRow[]>;
}

/** Display colours per actor (presentation only; not part of the scene data). */
const PALETTE = ["#3b82f6", "#a855f7", "#f59e0b", "#10b981", "#ef4444", "#06b6d4"];
export function actorColors(scene: Scene): Record<string, string> {
  return Object.fromEntries(scene.actors.map((a, i) => [a.id, PALETTE[i % PALETTE.length]]));
}

/** A name for any id in the scene: actor, object or stage mark. */
export function nameOf(scene: Scene, id: string | null | undefined): string {
  if (!id) return "";
  return scene.actors.find((a) => a.id === id)?.name
    ?? scene.objects.find((o) => o.id === id)?.label
    ?? scene.location.marks.find((m) => m.id === id)?.label
    ?? id;
}
