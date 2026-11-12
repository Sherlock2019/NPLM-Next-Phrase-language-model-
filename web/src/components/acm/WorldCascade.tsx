"use client";

/**
 * 1 actor · 1 action = consequences in cascade, for the physics lab.
 *
 * The origin actor (red) performs the action (red vector). Prediction routing reads the action's
 * WHERE, which names the world the action happens in (here always the physical world: on, above
 * or under table_01). The consequences then cascade outward by proximity through the eight worlds,
 * each judged by its own laws, in the order of docs/world-layers.svg (atomic at the bottom, earth
 * at the top). Every item comes from the simulation's events:
 *   physical            motion, edge, tip, fall and landing events        (simulated)
 *   atomic & molecular  fracture-rule events: may break, survives, spill   (rule-derived)
 *   perception          a simulated impact is visible and audible          (inferred, possible)
 * The other worlds are listed with their laws and say they are not modelled in this lab.
 */

import { useEffect, useState } from "react";
import type { LabAction, LabEvent, LabResult } from "@/lib/acm/physics";
import { actionLabel, eventChain } from "@/lib/acm/objects";
import { StatusTag } from "@/components/multimodal/Stages";

type WorldId = "atomic" | "physical" | "perception" | "behaviour" | "digital" | "business" | "society" | "earth";

/** Bottom to top, as in the world-layers stack. */
const WORLDS: { id: WorldId; icon: string; name: string; laws: string; colour: string }[] = [
  { id: "atomic", icon: "⚛️", name: "Atomic & molecular", laws: "atomic and chemical laws: bonds, material strength", colour: "#a855f7" },
  { id: "physical", icon: "⚙️", name: "Physical", laws: "physical laws: force, motion, gravity, friction", colour: "#3b82f6" },
  { id: "perception", icon: "👁️", name: "Perception", laws: "laws of vibration and signals: light, sound", colour: "#818cf8" },
  { id: "behaviour", icon: "🧠", name: "Human & animal behaviour", laws: "behavioural and psychological laws", colour: "#14b8a6" },
  { id: "digital", icon: "💻", name: "Digital systems", laws: "digital system laws: records, workflows", colour: "#22c55e" },
  { id: "business", icon: "🏭", name: "Business & institutions", laws: "institutional laws: contracts, accounting", colour: "#f97316" },
  { id: "society", icon: "🏛️", name: "Society & economy", laws: "economic, legal and social laws", colour: "#eab308" },
  { id: "earth", icon: "🌍", name: "Earth", laws: "earth laws: ecology, resources", colour: "#10b981" },
];
const ORIGIN: WorldId = "physical";
const ORIGIN_INDEX = WORLDS.findIndex((w) => w.id === ORIGIN);
const MAX_RIPPLE = Math.max(ORIGIN_INDEX, WORLDS.length - 1 - ORIGIN_INDEX);

const PHYSICAL = new Set<LabEvent["kind"]>(["pushed", "starts_moving", "collides", "crosses_edge", "tips", "falls", "lands", "comes_to_rest", "stays_supported"]);
const ATOMIC = new Set<LabEvent["kind"]>(["may_break", "survives_impact", "would_spill"]);

interface Item { t: number; basis: string; text: string }

function itemsFor(world: WorldId, events: LabEvent[]): Item[] | null {
  const chain = (e: LabEvent): Item => {
    const c = eventChain(e);
    return { t: e.t, basis: c.basis, text: `${e.id} ${c.does} — ${e.detail}` };
  };
  if (world === "physical") return events.filter((e) => PHYSICAL.has(e.kind)).map(chain);
  if (world === "atomic") return events.filter((e) => ATOMIC.has(e.kind)).map(chain);
  if (world === "perception") {
    return events
      .filter((e) => (e.kind === "lands" || e.kind === "collides") && (e.speed ?? 0) > 0.3)
      .map((e) => ({
        t: e.t, basis: "inferred",
        text: `${e.id} hits ${e.other ?? "something"} at ${(e.speed ?? 0).toFixed(2)} m/s: visible, and a sound anyone nearby could hear (possible)`,
      }));
  }
  return null; // not modelled in this lab
}

function whereOf(a: LabAction): string {
  switch (a.kind) {
    case "push":
    case "flick": return "on table_01";
    case "drop": return "above table_01";
    case "remove_support": return "under the objects (table_01)";
    default: return "nowhere: no action";
  }
}

function Dummy({ colour, size = 22 }: { colour: string; size?: number }) {
  return (
    <svg viewBox="0 0 24 30" width={size} height={size * 1.25} aria-hidden className="shrink-0">
      <circle cx="12" cy="5" r="4" fill={colour} />
      <g stroke={colour} strokeWidth="2.6" strokeLinecap="round">
        <line x1="12" y1="10" x2="12" y2="20" />
        <line x1="12" y1="12" x2="5" y2="17" />
        <line x1="12" y1="12" x2="19" y2="17" />
        <line x1="12" y1="20" x2="7" y2="28" />
        <line x1="12" y1="20" x2="17" y2="28" />
      </g>
    </svg>
  );
}

export function WorldCascade({ result, action, actor }: { result: LabResult | null; action: LabAction | null; actor: string }) {
  const [ripple, setRipple] = useState(-1);

  // reveal the worlds ripple by ripple, outward from the action's world
  useEffect(() => {
    if (!result || !action) { setRipple(-1); return; }
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { setRipple(MAX_RIPPLE); return; }
    setRipple(0);
    let step = 0;
    const id = window.setInterval(() => {
      step += 1;
      setRipple(step);
      if (step >= MAX_RIPPLE) window.clearInterval(id);
    }, 450);
    return () => window.clearInterval(id);
  }, [result, action]);

  return (
    <div className="flex flex-col gap-2">
      <span className="eyebrow">4 · 1 actor · 1 action = consequences in cascade across the worlds</span>
      {!result || !action || action.kind === "none" ? (
        <p className="faint text-[11.5px] italic">Simulate an action to see its consequences cascade, world by world.</p>
      ) : (
        <>
          <div className="panel-raised flex flex-wrap items-center gap-x-2.5 gap-y-1.5 p-2 text-[12px]">
            <span className="flex items-center gap-1.5">
              <Dummy colour="#ef4444" />
              <span><b className="text-red-400">{actor}</b> <span className="faint">origin actor</span></span>
            </span>
            <span aria-hidden className="text-[16px] font-bold text-red-500">⟶</span>
            <span className="rounded border border-red-500/60 bg-red-500/10 px-1.5 py-0.5 font-semibold text-red-300">
              action: {actionLabel(action)}
            </span>
            <span aria-hidden className="faint">·</span>
            <span>
              <b>WHERE</b>: {whereOf(action)} <span aria-hidden>→</span>{" "}
              <b style={{ color: WORLDS[ORIGIN_INDEX].colour }}>{WORLDS[ORIGIN_INDEX].icon} physical world</b>
              <span className="faint"> (prediction routing reads the WHERE of the phrase)</span>
            </span>
          </div>

          <ol className="flex flex-col gap-1" aria-label="Worlds, from earth (top) to atomic (bottom)">
            {[...WORLDS].reverse().map((w) => {
              const index = WORLDS.findIndex((x) => x.id === w.id);
              const distance = Math.abs(index - ORIGIN_INDEX);
              const shown = distance <= ripple;
              const items = itemsFor(w.id, result.events);
              const origin = w.id === ORIGIN;
              return (
                <li key={w.id}
                  className={`flex gap-2 rounded-md px-2 py-1.5 transition-all duration-500 ${shown ? "opacity-100" : "opacity-15"} ${origin ? "ring-2" : "ring-1"}`}
                  style={{ background: `${w.colour}14`, boxShadow: `inset 3px 0 0 ${w.colour}`, ["--tw-ring-color" as string]: `${w.colour}${origin ? "cc" : "40"}` }}>
                  <div className="flex w-44 shrink-0 flex-col">
                    <span className="text-[12px] font-bold" style={{ color: w.colour }}>{w.icon} {w.name}</span>
                    <span className="faint text-[10.5px] leading-snug">{w.laws}</span>
                    <span className="faint mt-0.5 text-[10px] uppercase tracking-wide">
                      {origin ? "★ the action happens here" : `ripple ${distance} ${index > ORIGIN_INDEX ? "↑" : "↓"} by proximity`}
                    </span>
                  </div>
                  <div className="min-w-0 flex-1">
                    {items === null ? (
                      <span className="faint text-[11px] italic">not modelled in this lab</span>
                    ) : items.length === 0 ? (
                      <span className="faint text-[11px] italic">no consequence for this action</span>
                    ) : (
                      <ul className="flex flex-col gap-0.5">
                        {items.map((it, i) => (
                          <li key={i} className="flex items-start gap-1.5 text-[11px] leading-snug">
                            <span className="num faint w-11 shrink-0">{it.t.toFixed(2)}s</span>
                            <StatusTag status={it.basis} />
                            <span className="dim">{it.text}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          <p className="faint text-[10.5px]">
            Vs desired outcome: not stated in this scene. Physical items are simulated, atomic items come from the fracture rule, perception is
            inferred from simulated impacts; the cascade order (proximity) is the model&apos;s design, and worlds above perception are not
            modelled in this lab.
          </p>
        </>
      )}
    </div>
  );
}
