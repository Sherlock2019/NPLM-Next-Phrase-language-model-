/**
 * Manually supplied scene facts: the browser simulator gives the outcome; ARM's
 * circles are taken from the Python engine's result for the same action and the
 * same outcome type - and labelled as such, never as an analysis of the upload.
 */

import { simulate, type SimScene } from "@/lib/multimodal/tabletop";
import type { ActionKey, Circle, Meaning, Scenario } from "@/lib/multimodal/types";
import { toSimAction } from "./Results";

const signature = (kinds: string[]) => kinds.filter((k) => k !== "remains_supported").sort().join(",");

export function manualCircles(
  scenarios: Record<string, Scenario>,
  sim: SimScene,
  action: ActionKey,
): { circles: Circle[] | null; note: string } {
  const built = scenarios[action];
  const result = simulate(sim, toSimAction(built));
  const mine = signature(result.events.map((e) => `${e.kind}:${e.entity_id}`));
  const theirs = signature(built.events.map((e) => `${e.kind}:${e.entity_id}`));
  if (mine === theirs)
    return {
      circles: built.circles,
      note:
        "ARM result computed by the Python engine for the built-in scene with the same action and the same outcome " +
        "type. Your manually supplied positions change the geometry, not which consequences follow.",
    };
  return {
    circles: null,
    note: `This outcome (${mine || "no change"}) differs from the built-in example's (${theirs || "no change"}). ARM consequences for it need the Python engine (Live mode).`,
  };
}

export function manualMeaning(action: ActionKey, kind: "image" | "video"): Meaning {
  const supplied = "manually supplied — not extracted from your upload";
  return {
    evidence_kind: `Your ${kind} was not analysed. These facts were typed in by hand.`,
    who: { value: "self (the proposer)", status: "assumed", source: "supplied with the proposed action" },
    action: {
      value: action === "none" ? "none" : action === "push_edge" ? "push (proposed)" : "move (proposed)",
      status: "assumed",
      source: "selected proposed action",
    },
    what: { value: "blue_cup_01", status: "assumed", source: supplied },
    to_whom: { value: null, status: "unknown", source: "not applicable" },
    where: { value: "table_01", status: "assumed", source: supplied },
    when: { value: null, status: "unknown", source: "no timestamp supplied" },
    how: { value: null, status: "unknown", source: "not supplied" },
    why: { value: null, status: "unknown", source: "not supplied" },
    observed_states: [
      { text: "blue_cup_01 and red_cup_01 positions", status: "assumed", source: supplied },
    ],
    unknowns: ["everything about your upload", "force", "friction", "mass", "material", "contents"],
    evidence: [{ type: "manual", ref: "form entry" }],
  };
}
