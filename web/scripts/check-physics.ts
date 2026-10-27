/**
 * Sanity check: the physics lab's matter.js simulation against closed-form physics
 * on the demo scene (fall speed √(2gh), slide distance v²/2μg) and its rule events.
 *
 *   npx tsx scripts/check-physics.ts
 */

import { behaviourFor } from "../src/lib/acm/behaviours";
import { simulateLab, TABLE_TOP, type LabScene } from "../src/lib/acm/physics";

const scene: LabScene = {
  table: [0, 0, 1.2, 0.8],
  objects: [
    { id: "blue_cup_01", cls: "cup", x: 1.05, y: 0.4, r: 0.04 },
    { id: "red_cup_01", cls: "cup", x: 0.55, y: 0.45, r: 0.04 },
  ],
};
const g = 9.81;
const cup = behaviourFor("cup");
let failures = 0;
const check = (name: string, ok: boolean, detail: unknown) => {
  if (!ok) failures++;
  console.log(`${ok ? "ok  " : "FAIL"} ${name}`, ok ? "" : detail);
};
const near = (a: number, b: number, tol: number) => Math.abs(a - b) <= tol * Math.abs(b);

const still = simulateLab(scene, { kind: "none" });
check("no action: nothing moves", Object.values(still.final).every((f) => f.moved === 0 && f.on === "table_01"), still.final);

const slide = simulateLab(scene, { kind: "push", target: "blue_cup_01", dir: -1, distanceM: 0.2, speedMps: 0.5 });
const expected = 0.2 + 0.5 ** 2 / (2 * cup.friction * g);
check(`push 0.20 m at 0.5 m/s slides to ≈ ${expected.toFixed(3)} m (v²/2μg)`, near(slide.final.blue_cup_01.moved, expected, 0.1), slide.final.blue_cup_01);

const edge = simulateLab(scene, { kind: "push", target: "blue_cup_01", dir: 1, distanceM: 0.2 });
const land = edge.events.find((e) => e.id === "blue_cup_01" && e.kind === "lands");
const fallSpeed = Math.sqrt(2 * g * TABLE_TOP);
check("edge push: crosses the edge, falls, lands", ["crosses_edge", "falls", "lands"].every((k) => edge.events.some((e) => e.id === "blue_cup_01" && e.kind === k)), edge.events);
check(`floor impact ≈ √(2gh) = ${fallSpeed.toFixed(2)} m/s`, !!land && near(land.speed!, fallSpeed, 0.08), land);
check("fragile cup over its break speed: may break", edge.events.some((e) => e.kind === "may_break"), edge.events);
check("red cup is not reached", edge.final.red_cup_01.moved === 0, edge.final.red_cup_01);

const flick = simulateLab(scene, { kind: "flick", target: "blue_cup_01", dir: -1, speedMps: 2 });
check("flick toward the centre hits the red cup", flick.events.some((e) => e.kind === "collides" && e.id === "blue_cup_01" && e.other === "red_cup_01"), flick.events);

const again = simulateLab(scene, { kind: "push", target: "blue_cup_01", dir: 1, distanceM: 0.2 });
check("deterministic", JSON.stringify(again.events) === JSON.stringify(edge.events), null);

process.exit(failures ? 1 : 0);
