/**
 * Object libraries (mockup) for image and video input.
 *
 * Step 1 of image/video → prediction: an AI vision model recognises each object on screen
 * and classifies it against a LIBRARY OF OBJECTS PER ENVIRONMENT — kitchen, house, garden,
 * street, mountain. The environment is recognised first (a table with mugs → kitchen), and
 * it narrows what an object can be (a cylinder on a kitchen table is a mug, on a mountain
 * path a log). Every library object carries its properties: mass, shape, texture, material.
 *
 * Step 2: the class's behaviour profile (LIBRARY below) adds what the physics engine needs —
 * friction, restitution, fragility, container — and the rules that govern it. This stands in
 * for the asset/physics-material layer of a game engine (Unreal's physical materials + Chaos).
 *
 * Every property is an ASSUMPTION about a typical object of the class, never measured from
 * the pixels; in the demo the recognition itself is a mock (classes come from the fixture).
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
  shape: string;
  texture: string;
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
    shape: "cylinder, open top, side handle", texture: "smooth glaze",
    sizeM: { w: 0.08, h: 0.1 }, friction: 0.35, restitution: 0.15, fragile: true, breakSpeed: 2.5,
    container: true, contents: "unknown (empty or filled cannot be seen)", movable: "dynamic",
    rules: ["REST", "GRAVITY", "SUPPORT", "FRICTION", "PUSH", "COLLISION", "FRACTURE", "SPILL"],
    notes: "μ ceramic-on-wood ≈ 0.35; a ceramic mug dropped onto a hard floor from table height (≈3.8 m/s) often chips or breaks",
  },
  table: {
    cls: "table", label: "table", detectorLabel: "dining table", material: "wood (assumed)", massKg: null,
    shape: "flat rectangular top on four legs", texture: "varnished wood grain",
    sizeM: { w: 1.2, h: 0.75 }, friction: 0.5, restitution: 0.1, fragile: false, breakSpeed: null,
    container: false, contents: "—", movable: "static", rules: ["STATIC", "SUPPORT"],
    notes: "top at 0.75 m (assumed standard height): the image gives no height",
  },
  floor: {
    cls: "floor", label: "floor", detectorLabel: "floor", material: "hard floor (assumed tile/wood)", massKg: null,
    shape: "flat plane", texture: "hard, smooth",
    sizeM: { w: 3, h: 0 }, friction: 0.6, restitution: 0.2, fragile: false, breakSpeed: null,
    container: false, contents: "—", movable: "static", rules: ["STATIC", "SUPPORT"],
    notes: "assumed: the floor is outside the frame",
  },
  pusher: {
    cls: "pusher", label: "hand / pusher", detectorLabel: "hand", material: "—", massKg: null,
    shape: "hand", texture: "skin",
    sizeM: { w: 0.06, h: 0.08 }, friction: 0.8, restitution: 0, fragile: false, breakSpeed: null,
    container: false, contents: "—", movable: "agent", rules: ["PUSH"],
    notes: "an agent: it moves as the action says, not by physics",
  },
};

export const behaviourFor = (cls: string): Behaviour => LIBRARY[cls] ?? {
  ...LIBRARY.cup, cls, label: cls, detectorLabel: cls, material: "unknown", shape: "unknown", texture: "unknown", fragile: false, breakSpeed: null,
  container: false, contents: "unknown", notes: "not in the library: generic rigid body, no fracture or spill rules",
  rules: ["REST", "GRAVITY", "SUPPORT", "FRICTION", "PUSH", "COLLISION"],
};

// -- object libraries per environment (what the recognition model classifies against) ---------

export type Environment = "kitchen" | "house" | "garden" | "street" | "mountain";

export interface LibraryObject {
  cls: string; // links to a behaviour profile in LIBRARY when the engine has one
  label: string;
  massKg: number | null; // null: static or fixed
  shape: string;
  texture: string;
  material: string;
}

export const ENVIRONMENTS: Record<Environment, { label: string; cues: string; objects: LibraryObject[] }> = {
  kitchen: {
    label: "Kitchen", cues: "counters or a table with tableware, appliances",
    objects: [
      { cls: "cup", label: "cup / mug", massKg: 0.3, shape: "cylinder, open top, handle", texture: "smooth glaze", material: "ceramic" },
      { cls: "plate", label: "plate", massKg: 0.5, shape: "flat disc", texture: "smooth glaze", material: "ceramic" },
      { cls: "glass", label: "drinking glass", massKg: 0.25, shape: "cylinder, open top", texture: "smooth, transparent", material: "glass" },
      { cls: "pan", label: "frying pan", massKg: 1.2, shape: "shallow cylinder + long handle", texture: "smooth metal / non-stick", material: "aluminium" },
      { cls: "knife", label: "knife", massKg: 0.1, shape: "thin blade + handle", texture: "polished steel", material: "steel" },
      { cls: "table", label: "dining table", massKg: null, shape: "flat rectangular top on four legs", texture: "varnished wood grain", material: "wood" },
    ],
  },
  house: {
    label: "House", cues: "furniture, walls, doors, soft furnishings",
    objects: [
      { cls: "chair", label: "chair", massKg: 5, shape: "seat + back on four legs", texture: "wood or fabric", material: "wood" },
      { cls: "book", label: "book", massKg: 0.6, shape: "rectangular block", texture: "paper, card cover", material: "paper" },
      { cls: "vase", label: "vase", massKg: 1.0, shape: "tall narrow cylinder", texture: "smooth glaze", material: "ceramic" },
      { cls: "lamp", label: "table lamp", massKg: 2, shape: "base + stem + shade", texture: "metal and fabric", material: "metal" },
      { cls: "sofa", label: "sofa", massKg: 40, shape: "long padded box", texture: "soft upholstery", material: "fabric" },
    ],
  },
  garden: {
    label: "Garden", cues: "grass, plants, soil, fences",
    objects: [
      { cls: "pot", label: "flower pot", massKg: 3, shape: "truncated cone", texture: "rough, porous", material: "terracotta" },
      { cls: "ball", label: "ball", massKg: 0.4, shape: "sphere", texture: "smooth rubber", material: "rubber" },
      { cls: "watering_can", label: "watering can", massKg: 1.5, shape: "body + spout + handle", texture: "smooth plastic", material: "plastic" },
      { cls: "stone", label: "garden stone", massKg: 2, shape: "irregular", texture: "rough", material: "stone" },
      { cls: "wheelbarrow", label: "wheelbarrow", massKg: 15, shape: "tray on one wheel", texture: "painted metal", material: "steel" },
    ],
  },
  street: {
    label: "Street", cues: "road markings, pavement, vehicles, signs",
    objects: [
      { cls: "car", label: "car", massKg: 1300, shape: "long box on four wheels", texture: "painted metal, glass", material: "steel" },
      { cls: "bicycle", label: "bicycle", massKg: 12, shape: "two wheels + frame", texture: "metal tubes, rubber tyres", material: "aluminium" },
      { cls: "person", label: "person", massKg: 70, shape: "upright body", texture: "clothing", material: "—" },
      { cls: "cone", label: "traffic cone", massKg: 2, shape: "cone on square base", texture: "flexible plastic", material: "PVC" },
      { cls: "bin", label: "rubbish bin", massKg: 10, shape: "box on wheels", texture: "hard plastic", material: "plastic" },
    ],
  },
  mountain: {
    label: "Mountain", cues: "slopes, rock, snow, trees",
    objects: [
      { cls: "rock", label: "rock", massKg: 50, shape: "irregular", texture: "rough granite", material: "granite" },
      { cls: "log", label: "fallen log", massKg: 30, shape: "long cylinder", texture: "bark, rough", material: "wood" },
      { cls: "backpack", label: "backpack", massKg: 8, shape: "soft box", texture: "fabric", material: "nylon" },
      { cls: "snowball", label: "snowball", massKg: 0.2, shape: "sphere", texture: "granular, wet", material: "snow" },
      { cls: "tree", label: "tree", massKg: null, shape: "trunk + crown", texture: "bark, leaves", material: "wood" },
    ],
  },
};

/**
 * The environment a scene is classified into: the one whose library holds most of the
 * recognised classes (the demo's cups on a table → kitchen). A real model would also use
 * scene cues (ENVIRONMENTS[env].cues); the demo has none to read, so this is a mock.
 */
export function environmentFor(classes: string[]): Environment {
  let best: Environment = "kitchen";
  let hits = -1;
  for (const [env, lib] of Object.entries(ENVIRONMENTS) as [Environment, (typeof ENVIRONMENTS)[Environment]][]) {
    const n = classes.filter((c) => lib.objects.some((o) => o.cls === c)).length;
    if (n > hits) [best, hits] = [env, n];
  }
  return best;
}

export const ENGINE_NAME = "matter.js 0.20 rigid-body engine (stands in for a game engine: Unreal Chaos / PhysX)";
