/**
 * Side-view rigid-body simulation of the tabletop with matter.js (mockup of a game
 * physics engine). The top-down scene from the image/video gives x (along the push)
 * and y (depth); the side view keeps x and adds height z, which the image cannot give:
 * table height, object size, mass and material come from the behaviour library and
 * are ASSUMED. Objects only collide when their footprints overlap in depth.
 *
 * Runs headless and deterministically: the same scene and action give the same frames,
 * so the chat can re-run "what if" questions and the canvas can replay them.
 */

import Matter from "matter-js";
import { behaviourFor, type RuleId } from "./behaviours";

export interface LabObject {
  id: string;
  cls: string;
  x: number; // m, along the push
  y: number; // m, depth (top-down)
  r: number; // footprint radius, m
  color?: string;
}

export interface LabScene {
  table: [number, number, number, number]; // x0, y0, x1, y1 (m, top-down)
  objects: LabObject[];
}

export type LabAction =
  | { kind: "none" }
  | { kind: "push"; target: string; dir: 1 | -1; distanceM: number; speedMps?: number }
  | { kind: "flick"; target: string; dir: 1 | -1; speedMps: number }
  | { kind: "drop"; target: string; heightM: number }
  | { kind: "remove_support" };

export interface Pose { x: number; z: number; angle: number }
export interface LabFrame { t: number; poses: Record<string, Pose>; hand: Pose | null }

export type EventKind =
  | "starts_moving" | "pushed" | "collides" | "crosses_edge" | "tips" | "falls" | "lands"
  | "may_break" | "survives_impact" | "would_spill" | "comes_to_rest" | "stays_supported";

export interface LabEvent {
  t: number;
  id: string;
  kind: EventKind;
  other?: string;
  rule: RuleId;
  detail: string;
  speed?: number; // m/s
  x?: number;
}

export interface LabFinal { x: number; z: number; angle: number; on: string | null; moved: number; maxSpeed: number }

export interface LabResult {
  frames: LabFrame[];
  events: LabEvent[];
  final: Record<string, LabFinal>;
  tableTop: number;
  tableX: [number, number];
  supportRemoved: boolean;
  seconds: number;
}

export const TABLE_TOP = 0.75; // m, assumed (behaviour library)
const S = 200; // px per metre inside the engine
const STEP_MS = 1000 / 240;
const OX = 0.4; // m of floor left of the table
const WORLD_H = 1.6; // m

const px = (x: number) => (x + OX) * S;
const py = (z: number) => (WORLD_H - z) * S;
const mx = (p: number) => p / S - OX;
const mz = (p: number) => WORLD_H - p / S;
const toPx = (mps: number) => (mps * S) / 60; // matter velocities are px per 16.67 ms
const toMps = (v: number) => (v * 60) / S;
const r3 = (v: number) => Math.round(v * 1000) / 1000;

export function simulateLab(scene: LabScene, action: LabAction, seconds = 3): LabResult {
  const engine = Matter.Engine.create({ positionIterations: 10, velocityIterations: 8 });
  engine.gravity.y = 1;
  engine.gravity.scale = (9.81 * S) / 1e6; // px/ms²: g in this world's units
  const world = engine.world;
  const [x0, , x1] = scene.table;
  const supportRemoved = action.kind === "remove_support";

  const floor = Matter.Bodies.rectangle(px(0.8), py(-0.05), 6 * S, 0.1 * S, {
    isStatic: true, label: "floor_01", friction: 0, frictionStatic: 0, restitution: behaviourFor("floor").restitution,
  });
  const statics: Matter.Body[] = [floor];
  if (!supportRemoved) {
    statics.push(Matter.Bodies.rectangle(px((x0 + x1) / 2), py(TABLE_TOP - 0.02), (x1 - x0) * S, 0.04 * S, {
      isStatic: true, label: "table_01", friction: 0, frictionStatic: 0, restitution: behaviourFor("table").restitution,
    }));
  }

  // Dynamic objects; each gets a category bit, and collides with others only when their
  // top-down footprints overlap in depth (the side view would otherwise merge them).
  const movers = scene.objects.filter((o) => behaviourFor(o.cls).movable === "dynamic");
  const bodies = new Map<string, Matter.Body>();
  const inertia = new Map<string, number>();
  movers.forEach((o, i) => {
    const b = behaviourFor(o.cls);
    const w = Math.max(b.sizeM.w, 2 * o.r);
    let mask = 1;
    movers.forEach((p, j) => {
      if (j !== i && Math.abs(p.y - o.y) < p.r + o.r) mask |= 1 << (j + 1);
    });
    const z0 = action.kind === "drop" && action.target === o.id ? TABLE_TOP + action.heightM : TABLE_TOP;
    const body = Matter.Bodies.rectangle(px(o.x), py(z0 + b.sizeM.h / 2), w * S, b.sizeM.h * S, {
      // matter's own friction is a game approximation (a fixed impulse per solver pass), so it is
      // off; sliding friction is applied below as Coulomb's law, μ·g, from the behaviour library.
      label: o.id, friction: 0, frictionStatic: 0, restitution: b.restitution, frictionAir: 0,
      collisionFilter: { category: 1 << (i + 1), mask },
    });
    Matter.Body.setMass(body, b.massKg ?? 1);
    inertia.set(o.id, body.inertia);
    bodies.set(o.id, body);
  });
  Matter.Composite.add(world, [...statics, ...bodies.values()]);

  const events: LabEvent[] = [];
  const once = new Set<string>();
  const emit = (e: LabEvent, key = `${e.id}:${e.kind}`) => {
    if (once.has(key)) return;
    once.add(key);
    events.push({ ...e, t: r3(e.t), speed: e.speed === undefined ? undefined : r3(e.speed), x: e.x === undefined ? undefined : r3(e.x) });
  };
  const contacts = new Map<string, Set<string>>([...bodies.keys()].map((k) => [k, new Set<string>()]));
  const maxSpeed = new Map<string, number>([...bodies.keys()].map((k) => [k, 0]));
  const lastSpeed = new Map<string, number>();
  let t = 0;

  Matter.Events.on(engine, "collisionStart", (ev) => {
    for (const pair of ev.pairs) {
      for (const [a, b] of [[pair.bodyA, pair.bodyB], [pair.bodyB, pair.bodyA]] as const) {
        if (!bodies.has(a.label)) continue;
        contacts.get(a.label)!.add(b.label);
        // matter has already started resolving the contact here: use the speed from the step before
        const speed = Math.max(lastSpeed.get(a.label) ?? 0, lastSpeed.get(b.label) ?? 0);
        const beh = behaviourFor(scene.objects.find((o) => o.id === a.label)!.cls);
        if (b.label === "floor_01" && speed > 0.3) {
          emit({ t, id: a.label, kind: "lands", other: "floor_01", rule: "GRAVITY", speed, x: mx(a.position.x),
            detail: `hits the floor at ${speed.toFixed(2)} m/s` });
          if (beh.fragile && beh.breakSpeed !== null) {
            // judged on the first impact only; bounces are slower
            emit(speed > beh.breakSpeed
              ? { t, id: a.label, kind: "may_break", rule: "FRACTURE", speed,
                  detail: `impact ${speed.toFixed(2)} m/s > break speed ${beh.breakSpeed} m/s of ${beh.material}: may break` }
              : { t, id: a.label, kind: "survives_impact", rule: "FRACTURE", speed,
                  detail: `impact ${speed.toFixed(2)} m/s ≤ break speed ${beh.breakSpeed} m/s: probably intact` },
              `${a.label}:fracture`);
          }
        } else if (bodies.has(b.label) && speed > 0.02) {
          emit({ t, id: a.label, kind: "collides", other: b.label, rule: "COLLISION", speed,
            detail: `hits ${b.label} at ${speed.toFixed(2)} m/s` }, `${a.label}:collides:${b.label}`);
        } else if (b.label === "table_01" && action.kind === "drop" && speed > 0.3) {
          emit({ t, id: a.label, kind: "lands", other: "table_01", rule: "GRAVITY", speed, x: mx(a.position.x),
            detail: `lands back on the table at ${speed.toFixed(2)} m/s` });
          if (beh.fragile && beh.breakSpeed !== null && speed > beh.breakSpeed)
            emit({ t, id: a.label, kind: "may_break", rule: "FRACTURE", speed, detail: `impact ${speed.toFixed(2)} m/s > break speed: may break` },
              `${a.label}:fracture`);
        }
      }
    }
  });
  Matter.Events.on(engine, "collisionEnd", (ev) => {
    for (const pair of ev.pairs) {
      contacts.get(pair.bodyA.label)?.delete(pair.bodyB.label);
      contacts.get(pair.bodyB.label)?.delete(pair.bodyA.label);
    }
  });

  const target = action.kind !== "none" && action.kind !== "remove_support" ? bodies.get(action.target) : undefined;
  if (action.kind !== "none" && action.kind !== "remove_support" && !target)
    throw new Error(`${action.target} is not a movable object in the scene`);
  const start = target ? { x: target.position.x } : null;
  const targetObj = target ? scene.objects.find((o) => o.id === target.label)! : null;
  let pushing = action.kind === "push";
  const ACT_STEP = 2; // let matter settle the resting contacts (and its time step) before acting
  if (target && action.kind !== "drop") {
    emit({ t: 0, id: target.label, kind: action.kind === "push" ? "pushed" : "starts_moving", rule: "PUSH", x: mx(target.position.x),
      detail: action.kind === "push" ? `pushed ${action.distanceM.toFixed(2)} m ${action.dir > 0 ? "toward +x (the right edge)" : "toward −x (the centre)"}`
        : `flicked at ${(action as { speedMps: number }).speedMps.toFixed(1)} m/s` });
  }
  if (action.kind === "drop" && target)
    emit({ t: 0, id: target.label, kind: "falls", rule: "GRAVITY", detail: `released ${action.heightM.toFixed(2)} m above the table` });
  if (supportRemoved) bodies.forEach((_, id) => emit({ t: 0, id, kind: "falls", rule: "SUPPORT", detail: "its support (table_01) is removed" }));

  const frames: LabFrame[] = [];
  const hand: { x: number; z: number } | null = action.kind === "push" && targetObj
    ? { x: targetObj.x - action.dir * (targetObj.r + 0.035), z: TABLE_TOP + 0.04 } : null;
  const steps = Math.round((seconds * 1000) / STEP_MS);
  const restFor = new Map<string, number>();
  const sideOf = (x: number) => (x < x0 ? -1 : x > x1 ? 1 : 0);
  const prevSide = new Map<string, number>([...bodies].map(([id, b]) => [id, sideOf(mx(b.position.x))]));

  for (let step = 0; step <= steps; step++) {
    t = (step * STEP_MS) / 1000;
    if (step === ACT_STEP && action.kind === "flick" && target)
      Matter.Body.setVelocity(target, { x: action.dir * toPx(action.speedMps), y: 0 });
    if (pushing && target && start && action.kind === "push" && step >= ACT_STEP) {
      const done = Math.abs(target.position.x - start.x) / S >= action.distanceM;
      // the hand stays on the table: it stops once the object's centre leaves the top
      if (done || sideOf(mx(target.position.x)) !== 0) pushing = false;
      else Matter.Body.setVelocity(target, { x: action.dir * toPx(action.speedMps ?? 0.5), y: target.velocity.y });
      if (hand && targetObj) hand.x = mx(target.position.x) - action.dir * (targetObj.r + 0.035);
    }
    for (const [id, b] of bodies) {
      const speed = toMps(b.speed);
      lastSpeed.set(id, speed);
      maxSpeed.set(id, Math.max(maxSpeed.get(id)!, speed));
      const x = mx(b.position.x);
      const side = sideOf(x);
      // A mug sliding on a flat top cannot tip from friction (μ < width/height), so rotation
      // is locked while its centre is over the table; past the edge gravity tips it freely.
      const overTable = !supportRemoved && side === 0 && mz(b.position.y) > TABLE_TOP - 0.02;
      const locked = b.inertia === Infinity;
      if (overTable && !locked) {
        Matter.Body.setAngle(b, 0);
        Matter.Body.setAngularVelocity(b, 0);
        Matter.Body.setInertia(b, Infinity);
      } else if (!overTable && locked) Matter.Body.setInertia(b, inertia.get(id)!);
      const sliding = [...contacts.get(id)!].some((c) => c === "table_01" || c === "floor_01");
      if (sliding && !(pushing && b === target) && b.velocity.x !== 0) {
        const mu = behaviourFor(scene.objects.find((o) => o.id === id)!.cls).friction;
        const vx = toMps(b.velocity.x);
        const slowed = Math.sign(vx) * Math.max(0, Math.abs(vx) - mu * 9.81 * (STEP_MS / 1000));
        Matter.Body.setVelocity(b, { x: toPx(slowed), y: b.velocity.y });
        if (slowed === 0 && overTable) Matter.Body.setAngularVelocity(b, 0);
      }
      if (!supportRemoved && side !== 0 && prevSide.get(id) === 0 && mz(b.position.y) > TABLE_TOP - 0.05)
        emit({ t, id, kind: "crosses_edge", rule: "SUPPORT", x, detail: `centre of mass passes the table edge (x = ${side > 0 ? x1 : x0} m): no support under it` });
      prevSide.set(id, side);
      if (Math.abs(b.angle) > 0.35) emit({ t, id, kind: "tips", rule: "SUPPORT", detail: `tilts ${Math.round((b.angle * 180) / Math.PI)}°` });
      if (b.velocity.y > toPx(0.6)) emit({ t, id, kind: "falls", rule: "GRAVITY", x, detail: "falls under gravity" });
      const beh = behaviourFor(scene.objects.find((o) => o.id === id)!.cls);
      if (beh.container && Math.abs(b.angle) > Math.PI / 4)
        emit({ t, id, kind: "would_spill", rule: "SPILL", detail: `tilted past 45°: would spill its contents — contents ${beh.contents}` });
      const resting = speed < 0.01 && !pushing;
      restFor.set(id, resting ? (restFor.get(id) ?? 0) + STEP_MS : 0);
      if (restFor.get(id)! > 300 && maxSpeed.get(id)! > 0.05) {
        const on = [...contacts.get(id)!].find((c) => c === "table_01" || c === "floor_01") ?? "another object";
        emit({ t, id, kind: "comes_to_rest", rule: "FRICTION", x, detail: `stops at x = ${x.toFixed(2)} m on ${on}` });
      }
    }
    if (step % 4 === 0) {
      const poses: Record<string, Pose> = {};
      for (const [id, b] of bodies) poses[id] = { x: mx(b.position.x), z: mz(b.position.y), angle: b.angle };
      frames.push({ t, poses, hand: hand ? { x: hand.x, z: hand.z, angle: 0 } : null });
    }
    Matter.Engine.update(engine, STEP_MS);
  }

  const final: Record<string, LabFinal> = {};
  for (const [id, b] of bodies) {
    const o = scene.objects.find((p) => p.id === id)!;
    const on = [...contacts.get(id)!].find((c) => c === "table_01" || c === "floor_01") ?? null;
    final[id] = { x: r3(mx(b.position.x)), z: r3(mz(b.position.y)), angle: b.angle, on, moved: r3(Math.abs(mx(b.position.x) - o.x)), maxSpeed: r3(maxSpeed.get(id)!) };
    if (maxSpeed.get(id)! <= 0.05 && on === "table_01")
      emit({ t: 0, id, kind: "stays_supported", rule: "REST", detail: "nothing acts on it: it stays where it is, supported by table_01" });
  }
  Matter.Engine.clear(engine);
  events.sort((a, b) => a.t - b.t);
  return { frames, events, final, tableTop: TABLE_TOP, tableX: [x0, x1], supportRemoved, seconds };
}
