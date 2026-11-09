"use client";

/**
 * "The radius of consequences": ACM's blast radius as eight concentric rings around the
 * action, from the actor out to the world. Hover or click a ring (or its legend row) to see
 * what ACM reports there for the example "I will sell my car to Sarah in Paris tomorrow to pay
 * my debt." (context: Mark wants to buy my car; Sarah needs a car).
 *
 * The eight rings are the presentation grouping; each names the engine layer(s) it shows
 * (self · impacted · other actors · environment · neighbour · organization · city · country ·
 * society · earth), so a researcher can match it to the report and the README.
 */

import { useState } from "react";

export interface ConsequenceRing {
  n: number;
  title: string;
  sub: string;
  fill: string;
  layers: string;
  example: string[];
}

export const CONSEQUENCE_RINGS: ConsequenceRing[] = [
  { n: 1, title: "Actor", sub: "Goals, resources and immediate outcomes", fill: "#e0e7ff", layers: "self",
    example: ["loses my car · gains money", "own goal “pay my debt”: ENABLED ➕ (the sale provides the money it needs)"] },
  { n: 2, title: "Other participants", sub: "People affected, their goals and possible reactions", fill: "#dbeafe", layers: "impacted · other actors",
    example: ["Sarah: gains my car · loses money", "Mark wants to buy my car: BLOCKED ❌ (Sarah has it now)", "Sarah needs a car: ADVANCED ✅"] },
  { n: 3, title: "Local physical world", sub: "Objects, surroundings and immediate environment", fill: "#cffafe", layers: "local environment",
    example: ["Paris: the sale takes place here", "image / video: objects and their physics, simulated (matter.js today, Unreal Engine 5 proposed)"] },
  { n: 4, title: "Neighbourhood", sub: "Nearby people, places and community", fill: "#ccfbf1", layers: "neighbour",
    example: ["Boulogne-Billancourt, Saint-Denis, Montreuil: no known impact (no rule matched, which is not evidence of none)"] },
  { n: 5, title: "City / region", sub: "Local services, infrastructure and institutions", fill: "#dcfce7", layers: "organization · city",
    example: ["insurers and the vehicle registry must record the new owner ●", "Paris (city): no known impact"] },
  { n: 6, title: "Society", sub: "Social norms, trust and collective behaviour", fill: "#fef9c3", layers: "society",
    example: ["money circulates through the economy ●"] },
  { n: 7, title: "Economy & countries", sub: "Markets, organisations and national effects", fill: "#fde68a", layers: "country",
    example: ["France: a taxable transaction counts in national economic activity ●"] },
  { n: 8, title: "The world", sub: "Cross-border, global and planetary effects", fill: "#fed7aa", layers: "earth",
    example: ["an existing car is reused instead of a new one being made ▲"] },
];

const INK = "#0b1b2e";

export function ConsequenceRings() {
  const [pick, setPick] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const active = hover ?? pick;
  const size = 520;
  const c = size / 2;
  const core = 44;
  const step = (c - core - 6) / CONSEQUENCE_RINGS.length;
  const radius = (n: number) => core + step * n;
  const shown = CONSEQUENCE_RINGS.find((r) => r.n === active);
  const toggle = (n: number) => setPick(pick === n ? null : n);

  return (
    <figure className="flex flex-col gap-4">
      <figcaption>
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-cyan-500">Action–Consequence Model</p>
        <h3 className="text-[22px] font-extrabold tracking-tight sm:text-[26px]">The radius of consequences</h3>
        <p className="dim text-[14px]">One action can create effects across people, places and systems. Point at a ring to see what ACM finds there for the example.</p>
      </figcaption>

      <div className="grid items-center gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <svg viewBox={`0 0 ${size} ${size}`} className="mx-auto block w-full max-w-[520px]" role="img"
          aria-label="Eight concentric rings around the action: actor, other participants, local physical world, neighbourhood, city or region, society, economy and countries, the world">
          {[...CONSEQUENCE_RINGS].reverse().map((r) => {
            const on = active === r.n;
            const dim = active !== null && !on;
            return (
              <circle key={r.n} cx={c} cy={c} r={radius(r.n)} fill={r.fill} fillOpacity={dim ? 0.45 : 1}
                stroke={on ? INK : "#ffffff"} strokeWidth={on ? 3 : 2.5} className="cursor-pointer transition-[fill-opacity]"
                onMouseEnter={() => setHover(r.n)} onMouseLeave={() => setHover(null)} onClick={() => toggle(r.n)}>
                <title>{`${r.n} · ${r.title}: ${r.sub}`}</title>
              </circle>
            );
          })}
          {CONSEQUENCE_RINGS.map((r) => (
            <text key={r.n} x={c} y={c - radius(r.n) + step / 2 + 5} textAnchor="middle" fontSize={14} fontWeight={700}
              fill={INK} pointerEvents="none">{r.n}</text>
          ))}
          <circle cx={c} cy={c} r={core - 4} fill={INK} stroke="#ffffff" strokeWidth={3} />
          <text x={c} y={c + 4.5} textAnchor="middle" fontSize={12.5} fontWeight={800} letterSpacing={1} fill="#ffffff" pointerEvents="none">ACTION</text>
        </svg>

        <ol className="flex flex-col gap-1">
          {CONSEQUENCE_RINGS.map((r) => {
            const on = active === r.n;
            return (
              <li key={r.n}>
                <button type="button" aria-pressed={pick === r.n} onClick={() => toggle(r.n)}
                  onMouseEnter={() => setHover(r.n)} onMouseLeave={() => setHover(null)}
                  className={`flex w-full items-start gap-3 rounded-lg px-2 py-1.5 text-left transition-colors ${on ? "bg-cyan-400/10 ring-1 ring-cyan-400/40" : "hover:bg-[var(--panel-raised)]"}`}>
                  <span className="num grid size-7 shrink-0 place-items-center rounded-full text-[13px] font-bold" style={{ background: r.fill, color: INK }}>{r.n}</span>
                  <span className="min-w-0">
                    <span className="block text-[14px] font-bold uppercase tracking-wide">{r.title}</span>
                    <span className="dim block text-[12.5px]">{r.sub}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="panel-raised min-h-[92px] p-4" aria-live="polite">
        {shown ? (
          <>
            <p className="text-[12px] font-semibold">
              <span className="num mr-2 rounded px-1.5 py-0.5" style={{ background: shown.fill, color: INK }}>{shown.n}</span>
              {shown.title}
              <span className="faint ml-2 font-normal">engine layer: {shown.layers}</span>
            </p>
            <ul className="mt-2 flex flex-col gap-1 text-[13.5px]">
              {shown.example.map((e) => <li key={e}>• {e}</li>)}
            </ul>
          </>
        ) : (
          <p className="dim text-[13.5px]">
            <b className="text-[var(--text)]">“I will sell my car to Sarah in Paris tomorrow to pay my debt.”</b> Choose a ring to see what ACM reports there,
            and which engine layer it comes from. A ring with no matching rule says <i>no known impact</i>, never <i>no impact</i>.
          </p>
        )}
      </div>
    </figure>
  );
}
