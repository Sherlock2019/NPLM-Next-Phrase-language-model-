/**
 * Object behaviour library (mockup): what each detected object class is made of and
 * which physical rules govern it. It stands in for the asset/physics-material layer of
 * a game engine (Unreal's physical materials + Chaos). Every property here is an
 * ASSUMPTION about a typical object of the class, never something read from the image.
 */

export type RuleId = "GRAVITY" | "SUPPORT" | "FRICTION" | "PUSH" | "COLLISION" | "FRACTURE" | "SPILL" | "STATIC" | "REST";

export interface PhysicsRule {
  id: RuleId;
  name: string;
  law: string;
}

export const RULES: Record<RuleId, PhysicsRule> = {
  GRAVITY: { id: "GRAVITY", name: "Gravity", law: "an unsupported object accelerates downward at g = 9.81 m/s²" },
  SUPPORT: { id: "SUPPORT", name: "Support", law: "an object stays up while its centre of mass is over its support surface; past the edge it tips and falls" },
  FRICTION: { id: "FRICTION", name: "Sliding friction", law: "a sliding object decelerates at μ·g until it stops" },
  PUSH: { id: "PUSH", name: "Contact push", law: "while a pusher is in contact, the pushed object moves with it" },
  COLLISION: { id: "COLLISION", name: "Collision", law: "objects that touch exchange momentum; restitution e sets how much they bounce" },
  FRACTURE: { id: "FRACTURE", name: "Fracture", law: "a fragile object that hits a hard surface faster than its break speed may break" },
  SPILL: { id: "SPILL", name: "Spill", law: "an open container tilted past ~45° spills its contents, if it has any" },
  STATIC: { id: "STATIC", name: "Static furniture", law: "at this scale, furniture and the floor do not move (their mass ≫ the pushed object)" },
  REST: { id: "REST", name: "Rest", law: "with no net force, an object at rest stays at rest" },
};

export interface Behaviour {
  cls: string;
  label: string;
  detectorLabel: string; // what a COCO-style detector would call it
  material: string;
  massKg: number | null; // null: static
  sizeM: { w: number; h: number }; // side-view footprint
  friction: number;
  restitution: number;
  fragile: boolean;
  breakSpeed: number | null; // m/s onto a hard floor
  container: boolean;
  contents: string;
  movable: "dynamic" | "static" | "agent";
  rules: RuleId[];
  notes: string;
}

export const LIBRARY: Record<string, Behaviour> = {
  cup: {
    cls: "cup", label: "cup / mug", detectorLabel: "cup", material: "ceramic (assumed)", massKg: 0.3,
    sizeM: { w: 0.08, h: 0.1 }, friction: 0.35, restitution: 0.15, fragile: true, breakSpeed: 2.5,
    container: true, contents: "unknown (empty or filled cannot be seen)", movable: "dynamic",
    rules: ["REST", "GRAVITY", "SUPPORT", "FRICTION", "PUSH", "COLLISION", "FRACTURE", "SPILL"],
    notes: "μ ceramic-on-wood ≈ 0.35; a ceramic mug dropped onto a hard floor from table height (≈3.8 m/s) often chips or breaks",
  },
  table: {
    cls: "table", label: "table", detectorLabel: "dining table", material: "wood (assumed)", massKg: null,
    sizeM: { w: 1.2, h: 0.75 }, friction: 0.5, restitution: 0.1, fragile: false, breakSpeed: null,
    container: false, contents: "—", movable: "static", rules: ["STATIC", "SUPPORT"],
    notes: "top at 0.75 m (assumed standard height): the image gives no height",
  },
  floor: {
    cls: "floor", label: "floor", detectorLabel: "floor", material: "hard floor (assumed tile/wood)", massKg: null,
    sizeM: { w: 3, h: 0 }, friction: 0.6, restitution: 0.2, fragile: false, breakSpeed: null,
    container: false, contents: "—", movable: "static", rules: ["STATIC", "SUPPORT"],
    notes: "assumed: the floor is outside the frame",
  },
  pusher: {
    cls: "pusher", label: "hand / pusher", detectorLabel: "hand", material: "—", massKg: null,
    sizeM: { w: 0.06, h: 0.08 }, friction: 0.8, restitution: 0, fragile: false, breakSpeed: null,
    container: false, contents: "—", movable: "agent", rules: ["PUSH"],
    notes: "an agent: it moves as the action says, not by physics",
  },
};

export const behaviourFor = (cls: string): Behaviour => LIBRARY[cls] ?? {
  ...LIBRARY.cup, cls, label: cls, detectorLabel: cls, material: "unknown", fragile: false, breakSpeed: null,
  container: false, contents: "unknown", notes: "not in the library: generic rigid body, no fracture or spill rules",
  rules: ["REST", "GRAVITY", "SUPPORT", "FRICTION", "PUSH", "COLLISION"],
};

export const ENGINE_NAME = "matter.js 0.20 rigid-body engine (stands in for a game engine: Unreal Chaos / PhysX)";
