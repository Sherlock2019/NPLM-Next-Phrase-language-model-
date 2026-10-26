/**
 * Parity check: the browser simulator must reproduce the Python simulator's
 * results recorded in public/demo/demo_results.json, for every flow and branch.
 *
 *   node scripts/check-tabletop.mts
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { simulate, type SimAction, type SimScene } from "../src/lib/multimodal/tabletop.ts";

const root = fileURLToPath(new URL("..", import.meta.url));
const demo = JSON.parse(readFileSync(`${root}/public/demo/demo_results.json`, "utf8"));

let failures = 0;
let checks = 0;
for (const [flow, data] of Object.entries<any>(demo.flows)) {
  if (!data.scene) continue;
  const table = data.scene.entities.find((e: any) => e.class === "table").extent;
  const scene: SimScene = {
    table,
    objects: data.scene.entities
      .filter((e: any) => e.class === "cup")
      .map((e: any) => ({ id: e.id, x: e.position[0], y: e.position[1], r: e.radius_m })),
  };
  for (const [key, sc] of Object.entries<any>(data.scenarios)) {
    const a = sc.action;
    const action: SimAction = !a
      ? { kind: "none" }
      : a.predicate === "push"
        ? { kind: "push", target: a.target, directionDeg: a.parameters.direction_deg.value, distanceM: a.parameters.distance.value }
        : { kind: "move", target: a.target, to: [a.destination.x, a.destination.y] };
    const result = simulate(scene, action);
    const pyEvents = sc.events.map((e: any) => `${e.kind}:${e.entity_id}`).sort();
    const tsEvents = result.events.map((e) => `${e.kind}:${e.entity_id}`).sort();
    const pyFinal = Object.fromEntries(Object.entries<any>(sc.final_positions).filter(([id]) => id in result.final));
    checks++;
    const same = JSON.stringify(pyEvents) === JSON.stringify(tsEvents) && JSON.stringify(pyFinal) === JSON.stringify(result.final);
    if (!same) {
      failures++;
      console.error(`MISMATCH ${flow}/${key}`, { pyEvents, tsEvents, pyFinal, tsFinal: result.final });
    }
  }
}
console.log(`${checks - failures}/${checks} branches match the Python simulator`);
process.exit(failures ? 1 : 0);
