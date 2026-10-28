/**
 * Browser port of ARM's constrained tabletop simulator (acm/world/tabletop.py).
 *
 * Same declared rules, same numbers: a pushed disc slides in a straight line and
 * stops at contact; an object whose centre ends beyond the support boundary
 * crosses the edge and falls; where it lands is unknown. It exists so the demo
 * can re-run alternatives and manually supplied scene facts without a server.
 * `web/scripts/check-tabletop.mts` checks it against the Python output.
 *
 * No imports on purpose: Node can run this file directly for that check.
 */

export type Vec = [number, number];

export interface SimObject {
  id: string;
  x: number;
  y: number;
  r: number; // footprint radius, metres
}

export interface SimScene {
  table: [number, number, number, number]; // x_min, y_min, x_max, y_max (m)
  objects: SimObject[];
}

export type SimAction =
  | { kind: "none" }
  | { kind: "push"; target: string; directionDeg: number; distanceM: number }
  | { kind: "move"; target: string; to: Vec };

export interface SimEvent {
  kind: "remains_supported" | "crosses_edge" | "falls" | "collides" | "overhangs_edge";
  entity_id: string;
  other_id?: string | null;
}

export interface SimResult {
  events: SimEvent[];
  final: Record<string, Vec | null>; // null: fell, landing position unknown
  path: Record<string, Vec[]>; // straight-line trajectory of moved objects
}

const round4 = (v: number) => Math.round(v * 1e4) / 1e4;

function inside([x, y]: Vec, t: SimScene["table"]): boolean {
  return t[0] <= x && x <= t[2] && t[1] <= y && y <= t[3];
}

function overhangs([x, y]: Vec, r: number, t: SimScene["table"]): boolean {
  return x - r < t[0] || x + r > t[2] || y - r < t[1] || y + r > t[3];
}

function sweep(scene: SimScene, target: SimObject, deg: number, dist: number): { end: Vec; hit: string | null } {
  const dx = Math.cos((deg * Math.PI) / 180);
  const dy = Math.sin((deg * Math.PI) / 180);
  let best = dist;
  let hit: string | null = null;
  for (const other of scene.objects) {
    if (other.id === target.id) continue;
    const reach = target.r + other.r;
    const fx = target.x - other.x;
    const fy = target.y - other.y;
    const b = fx * dx + fy * dy;
    const c = fx * fx + fy * fy - reach * reach;
    const disc = b * b - c;
    if (disc < 0) continue;
    const s = -b - Math.sqrt(disc);
    if (s >= 0 && s < best) {
      best = s;
      hit = other.id;
    }
  }
  return { end: [round4(target.x + best * dx), round4(target.y + best * dy)], hit };
}

export function simulate(scene: SimScene, action: SimAction): SimResult {
  const events: SimEvent[] = [];
  const final: Record<string, Vec | null> = {};
  const path: Record<string, Vec[]> = {};
  const moved: Record<string, Vec> = {};

  if (action.kind !== "none") {
    const target = scene.objects.find((o) => o.id === action.target);
    if (!target) throw new Error(`${action.target} is not a movable object in the scene`);
    if (action.kind === "push") {
      const { end, hit } = sweep(scene, target, action.directionDeg, action.distanceM);
      if (hit) events.push({ kind: "collides", entity_id: target.id, other_id: hit });
      moved[target.id] = end;
    } else {
      moved[target.id] = [action.to[0], action.to[1]];
    }
  }

  for (const obj of scene.objects) {
    const before: Vec = [obj.x, obj.y];
    const after = moved[obj.id] ?? before;
    const wasOn = inside(before, scene.table);
    const isOn = inside(after, scene.table);
    if (after !== before) path[obj.id] = [before, after];
    if (wasOn && !isOn) {
      events.push({ kind: "crosses_edge", entity_id: obj.id }, { kind: "falls", entity_id: obj.id });
      final[obj.id] = null;
    } else {
      if (isOn && overhangs(after, obj.r, scene.table)) events.push({ kind: "overhangs_edge", entity_id: obj.id });
      if (isOn) events.push({ kind: "remains_supported", entity_id: obj.id });
      final[obj.id] = after;
    }
  }
  return { events, final, path };
}

/** Validate manually supplied numbers before simulating: metres, inside sane bounds. */
export function validateScene(scene: SimScene): string[] {
  const errors: string[] = [];
  const [x0, y0, x1, y1] = scene.table;
  if (!(x1 > x0 && y1 > y0)) errors.push("table extent must have positive width and depth (m)");
  for (const o of scene.objects) {
    if (![o.x, o.y, o.r].every(Number.isFinite)) errors.push(`${o.id}: coordinates must be numbers (m)`);
    if (o.r <= 0 || o.r > 0.5) errors.push(`${o.id}: footprint radius must be in (0, 0.5] m`);
    if (!inside([o.x, o.y], scene.table)) errors.push(`${o.id}: must start on table_01 (inside the support boundary)`);
  }
  for (let i = 0; i < scene.objects.length; i++)
    for (let j = i + 1; j < scene.objects.length; j++) {
      const a = scene.objects[i];
      const b = scene.objects[j];
      if (Math.hypot(a.x - b.x, a.y - b.y) < a.r + b.r) errors.push(`${a.id} and ${b.id} overlap`);
    }
  return errors;
}
