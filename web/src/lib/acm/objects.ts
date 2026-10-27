/**
 * Mockups for image/video inference, as the pipeline would run with real models:
 *   detect objects (YOLO-style detector; a tracker for video)  ->  look up each class in the
 *   behaviour library  ->  simulate the proposed action  ->  answer questions per object.
 *
 * The detector is a MOCK: boxes and confidences come from the fixture scene, not from a
 * model. Questions are read by a keyword parser (a live version would use MLM's parser).
 * Answers come only from the simulation's events and the library's rules.
 */

import type { SceneData } from "@/lib/multimodal/types";
import { behaviourFor, RULES, type RuleId } from "./behaviours";
import { simulateLab, type LabAction, type LabEvent, type LabResult, type LabScene } from "./physics";

export interface Detection {
  id: string;
  cls: string;
  label: string; // detector label
  conf: number;
  box: [number, number, number, number]; // top-down metres
  track: number | null;
}

/** Deterministic pseudo-confidence per id, so the mock reads like a detector without changing. */
function conf(id: string, cls: string): number {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const base = cls === "table" ? 0.95 : cls === "pusher" ? 0.86 : 0.9;
  return Math.round((base + (h % 40) / 1000) * 100) / 100;
}

export function detect(scene: SceneData, video: boolean): Detection[] {
  return scene.entities.map((e, i) => {
    const box: Detection["box"] = e.extent
      ? [e.extent[0], e.extent[1], e.extent[2], e.extent[3]]
      : [e.position![0] - (e.radius_m ?? 0.04), e.position![1] - (e.radius_m ?? 0.04), e.position![0] + (e.radius_m ?? 0.04), e.position![1] + (e.radius_m ?? 0.04)];
    return { id: e.id, cls: e.class, label: behaviourFor(e.class).detectorLabel, conf: conf(e.id, e.class), box, track: video ? i + 1 : null };
  });
}

export function toLabScene(scene: SceneData): LabScene {
  const table = scene.entities.find((e) => e.class === "table")?.extent ?? [0, 0, 1.2, 0.8];
  return {
    table: [table[0], table[1], table[2], table[3]],
    objects: scene.entities.filter((e) => e.position).map((e) => ({
      id: e.id, cls: e.class, x: e.position![0], y: e.position![1], r: e.radius_m ?? 0.04,
      color: typeof e.attributes.color === "string" ? e.attributes.color : undefined,
    })),
  };
}

// -- describing an action and its events as Phrase DNA ----------------------------------------

export interface ObjChain {
  who: string;
  does: string;
  what: string | null;
  where: string | null;
  when: string;
  with_whom: string | null;
  why: string;
  rule: RuleId;
  basis: "simulation" | "rule" | "assumed";
}

const VERB: Record<LabEvent["kind"], string> = {
  starts_moving: "starts moving", pushed: "is pushed", collides: "collides", crosses_edge: "crosses the edge",
  tips: "tips over", falls: "falls", lands: "lands", may_break: "may break", survives_impact: "probably survives",
  would_spill: "would spill (if filled)", comes_to_rest: "comes to rest", stays_supported: "stays put",
};

export function describeAction(a: LabAction, actor: string): [string, string | null][] {
  switch (a.kind) {
    case "push":
      return [["WHO", actor], ["DOES", "push"], ["WHAT", a.target], ["HOW", `${a.distanceM.toFixed(2)} m ${a.dir > 0 ? "+x (toward the edge)" : "−x (toward the centre)"} at ${(a.speedMps ?? 0.5).toFixed(1)} m/s`], ["WHERE", "table_01"], ["WHEN", "t = 0"]];
    case "flick":
      return [["WHO", actor], ["DOES", "flick"], ["WHAT", a.target], ["HOW", `${a.speedMps.toFixed(1)} m/s ${a.dir > 0 ? "+x" : "−x"}`], ["WHERE", "table_01"], ["WHEN", "t = 0"]];
    case "drop":
      return [["WHO", actor], ["DOES", "lift and drop"], ["WHAT", a.target], ["HOW", `from ${a.heightM.toFixed(2)} m above the table`], ["WHEN", "t = 0"]];
    case "remove_support":
      return [["WHO", actor], ["DOES", "remove"], ["WHAT", "table_01 (the support)"], ["WHEN", "t = 0"]];
    default:
      return [["WHO", actor], ["DOES", "nothing (no action)"]];
  }
}

export function eventChain(e: LabEvent): ObjChain {
  const where = e.kind === "lands" ? e.other ?? null : e.x !== undefined ? `x = ${e.x.toFixed(2)} m` : null;
  return {
    who: e.id, does: VERB[e.kind], what: e.detail, where, when: `t = ${e.t.toFixed(2)} s`, with_whom: e.other ?? null,
    why: `${RULES[e.rule].name}: ${RULES[e.rule].law}`, rule: e.rule,
    basis: e.kind === "may_break" || e.kind === "survives_impact" || e.kind === "would_spill" ? "rule" : "simulation",
  };
}

export function actionLabel(a: LabAction): string {
  return describeAction(a, "").filter(([k]) => k === "DOES" || k === "WHAT" || k === "HOW").map(([, v]) => v).join(" ");
}

// -- the question engine --------------------------------------------------------------------

export interface ObjAnswer {
  reading: [string, string | null][];
  parser: string;
  answer: string;
  action: LabAction | null;
  actionDna: [string, string | null][] | null;
  chains: ObjChain[];
  props: { label: string; value: string }[] | null;
  result: LabResult | null;
}

const COLOURS = ["blue", "red", "green", "yellow", "white", "black"];

function findTarget(q: string, scene: LabScene, fallback: string): string {
  const words = q.toLowerCase();
  const byColour = scene.objects.find((o) => o.color && words.includes(o.color));
  if (byColour) return byColour.id;
  if (/\btable\b/.test(words) && !/\b(remove|without|take away|no)\b.*\btable\b/.test(words)) return "table_01";
  if (/\b(hand|pusher)\b/.test(words)) return scene.objects.find((o) => o.cls === "pusher")?.id ?? fallback;
  const byId = scene.objects.find((o) => words.includes(o.id.toLowerCase()));
  return byId?.id ?? fallback;
}

function parseAction(q: string, target: string): LabAction | null {
  const s = q.toLowerCase();
  const num = s.match(/(\d+(?:\.\d+)?)\s*(cm|mm|m\/s|m)\b/);
  const metres = num && num[2] !== "m/s" ? Number(num[1]) / (num[2] === "cm" ? 100 : num[2] === "mm" ? 1000 : 1) : null;
  const dir: 1 | -1 = /\b(cent(er|re)|middle|left|back|away from the edge|-x|−x)\b/.test(s) ? -1 : 1;
  if (/\b(remove|without|take away|no)\b.*\b(table|support)\b/.test(s)) return { kind: "remove_support" };
  if (/\b(flick|hit|knock|kick|slam|throw|hard|harder|fast|faster)\b/.test(s))
    return { kind: "flick", target, dir, speedMps: num && num[2] === "m/s" ? Number(num[1]) : 2 };
  if (/\b(drop|lift|raise|let go)\b/.test(s)) return { kind: "drop", target, heightM: metres ?? 0.3 };
  if (/\b(push|shove|nudge|slide|move)\b/.test(s)) return { kind: "push", target, dir, distanceM: metres ?? 0.2 };
  return null;
}

function sentence(events: LabEvent[], id: string): string {
  const own = events.filter((e) => e.id === id && e.kind !== "pushed" && e.kind !== "starts_moving");
  if (!own.length) return `${id} is not reached by this action: nothing acts on it, so it stays where it is (rule: Rest).`;
  return `${id} ${own.map((e) => {
    if (e.kind === "lands") return `lands on ${e.other === "floor_01" ? "the floor" : "the table"} at ${e.speed?.toFixed(2)} m/s (t = ${e.t.toFixed(2)} s)`;
    if (e.kind === "collides") return `hits ${e.other} at ${e.speed?.toFixed(2)} m/s`;
    if (e.kind === "comes_to_rest") return `comes to rest at x = ${e.x?.toFixed(2)} m`;
    if (e.kind === "crosses_edge") return `crosses the table edge at t = ${e.t.toFixed(2)} s`;
    return VERB[e.kind];
  }).join(", ")}.`;
}

export function answerObjectQuestion(q: string, scene: LabScene, selected: string, current: LabAction, actor: string): ObjAnswer {
  const s = q.toLowerCase();
  const target = findTarget(q, scene, selected);
  const beh = behaviourFor(scene.objects.find((o) => o.id === target)?.cls ?? (target === "table_01" ? "table" : "cup"));
  // the table and the hand are not pushed themselves: an action on them acts on the current target
  const dynamic = (id: string) => scene.objects.some((o) => o.id === id && behaviourFor(o.cls).movable === "dynamic");
  const fallback = "target" in current ? current.target : scene.objects.find((o) => dynamic(o.id))?.id ?? selected;
  const parsed = parseAction(q, dynamic(target) ? target : fallback);
  const asksProps = /\b(weigh|weight|mass|heavy|material|made of|friction|fragile|propert|what is it|what kind)\b/.test(s);
  const intent = parsed ? "what-if (simulate)" : asksProps ? "properties" : /\bwhy\b/.test(s) ? "why" :
    /\b(break|shatter|damage|survive|crack)\b/.test(s) ? "fracture" : /\b(spill|liquid|contents|coffee|water)\b/.test(s) ? "spill" :
    /\b(fall|falls|drop off|tip|tips|topple)\b/.test(s) ? "fall?" : "what happens";
  const reading: ObjAnswer["reading"] = [["WHO", target], ["ASKS", intent], ["DOES", parsed ? parsed.kind.replace("_", " ") : null],
    ["HOW", parsed && parsed.kind === "push" ? `${parsed.distanceM} m ${parsed.dir > 0 ? "+x" : "−x"}` : null]];
  const parser = "keyword parser (mock — the live version would read the question with MLM)";

  if (asksProps && !parsed) {
    return {
      reading, parser, action: null, actionDna: null, chains: [], result: null,
      answer: `${target} is a ${beh.label}: ${beh.material}${beh.massKg ? `, about ${beh.massKg} kg` : ", static"}. ` +
        `These are library assumptions for the class '${beh.cls}', not measured from the pixels.`,
      props: [
        { label: "class (detector → library)", value: `${beh.detectorLabel} → ${beh.cls}` },
        { label: "material", value: beh.material },
        { label: "mass", value: beh.massKg ? `${beh.massKg} kg (assumed)` : "static" },
        { label: "friction μ", value: String(beh.friction) },
        { label: "restitution e", value: String(beh.restitution) },
        { label: "fragile", value: beh.fragile ? `yes · break speed ${beh.breakSpeed} m/s` : "no" },
        { label: "container", value: beh.container ? `yes · contents ${beh.contents}` : "no" },
        { label: "rules", value: beh.rules.map((r) => RULES[r].name).join(", ") },
        { label: "note", value: beh.notes },
      ],
    };
  }

  const action = parsed ?? current;
  const result = simulateLab(scene, action);
  const mine = result.events.filter((e) => e.id === target || e.other === target);
  const chains = (mine.length ? mine : result.events.filter((e) => e.id === target)).map(eventChain);
  let answer = `If ${actionLabel(action)}: ${sentence(result.events, target)}`;
  if (target === "table_01") answer = `table_01 is static furniture (rule: Static furniture): ${action.kind === "remove_support" ? "it is removed, so nothing is supported." : "it does not move; it supports what stands on it."}`;
  if (beh.movable === "agent") {
    // the hand is the actor: describe what it does, then what that does to the object it acts on
    const acted = "target" in action ? action.target : null;
    answer = `${target} is the actor (an agent: it moves as the action says, not by physics — rule: Contact push). ` +
      `It does: ${actionLabel(action)}.${acted ? ` Result: ${sentence(result.events, acted)}` : ""}`;
    chains.splice(0, chains.length, ...result.events.filter((e) => e.id === acted).map(eventChain));
  }
  const has = (k: LabEvent["kind"]) => mine.find((e) => e.id === target && e.kind === k);
  if (intent === "fall?") {
    const fell = has("falls") ?? has("crosses_edge");
    answer = `${fell ? "Yes" : "No"} — ${answer.replace(/^If /, "if ")}`;
  } else if (intent === "fracture") {
    const brk = has("may_break") ?? has("survives_impact");
    answer = brk ? `${brk.detail}. Material is assumed (${beh.material}); a real answer would need the material and the floor type.`
      : `Under '${actionLabel(action)}' ${target} never hits anything hard, so the fracture rule does not apply: it stays intact.`;
  } else if (intent === "spill") {
    answer = beh.container
      ? `${has("would_spill") ? `${target} tilts past 45°` : `${target} stays upright`}; whether anything spills is UNKNOWN — its contents cannot be seen (${beh.contents}).`
      : `${target} is not a container: nothing to spill.`;
  } else if (intent === "why") {
    const rules = [...new Set(mine.filter((e) => e.id === target).map((e) => e.rule))];
    answer = rules.length ? `Because of: ${rules.map((r) => `${RULES[r].name} (${RULES[r].law})`).join("; ")}.` : `Nothing acts on ${target}: Rest — ${RULES.REST.law}.`;
  }
  return { reading, parser, answer, action, actionDna: describeAction(action, actor), chains, props: null, result };
}

export function objectPresets(target: string, cls: string): string[] {
  if (cls === "table") return ["What is the table made of?", "What if we remove the table?"];
  if (cls === "pusher") return ["What does the hand do?", `What if the hand pushes harder?`];
  return [
    `What happens if I push the ${target.replace(/_\d+$/, "").replace("_", " ")} 30 cm toward the edge?`,
    "Will it fall?", "Can it break?", "Will it spill?", "What is it made of?",
    "What if I push it 10 cm toward the centre?", "What if I flick it hard toward the centre?", "What if I drop it?",
  ];
}
