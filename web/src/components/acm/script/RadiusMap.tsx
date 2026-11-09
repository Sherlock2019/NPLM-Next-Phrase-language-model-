"use client";

/**
 * D · Consequence radius: the scene's scopes as concentric rings around the action, the
 * analysis' consequences in the selected ring, and a table alternative. A focused actor
 * highlights the rings and consequences that concern them. Scopes with nothing identified
 * say so; the rings are scopes to investigate, not a chain every effect passes through.
 */

import { useState, type KeyboardEvent } from "react";
import { nameOf, type Consequence, type SceneBundle } from "@/lib/acm/scene";
import { CONSEQUENCE_RINGS } from "@/components/acm/ConsequenceRings";
import { HORIZON, SourceBadge, StatusBadge, ValenceTag, btn } from "./shared";

const INK = "#0b1b2e";

export function RadiusMap({ b, colors, focus, action }: { b: SceneBundle; colors: Record<string, string>; focus: string | null; action: string }) {
  const s = b.scene;
  const [sel, setSel] = useState(s.scopes[0]?.id);
  const [table, setTable] = useState(false);
  const by = (scope: string) => b.analysis.consequences.filter((c) => c.scope === scope);
  const relevant = (scope: string) => !focus || by(scope).some((c) => c.affected.includes(focus));
  const empty = (scope: string) => by(scope).every((c) => c.status === "not_identified");
  const size = 600, c = 300, core = 58;
  const step = (c - core - 6) / Math.max(s.scopes.length, 1);
  const r = (n: number) => core + step * n;
  const fill = (n: number) => CONSEQUENCE_RINGS[n - 1]?.fill ?? "#e2e8f0";
  const scope = s.scopes.find((x) => x.id === sel) ?? s.scopes[0];
  const key = (id: string) => (e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSel(id); } };

  const Effects = ({ x }: { x: Consequence }) => (
    <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
      <StatusBadge s={x.status} />
      {x.status !== "not_identified" && <span className="faint text-[11.5px] font-semibold">{HORIZON[x.horizon]}</span>}
      {focus
        ? x.effect[focus] ? <ValenceTag v={x.effect[focus]} who={nameOf(s, focus)} /> : x.status !== "not_identified" && <span className="faint text-[11.5px]">does not name {nameOf(s, focus)}</span>
        : Object.entries(x.effect).map(([id, v]) => <ValenceTag key={id} v={v} who={nameOf(s, id)} />)}
    </span>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-[15px]"><span className="faint mr-2 text-[11px] font-bold uppercase tracking-wider">At the centre</span><b>{action}</b></p>
        <button type="button" className={`${btn} ml-auto`} aria-pressed={table} onClick={() => setTable(!table)}>{table ? "Show the diagram" : "Show as a table"}</button>
      </div>

      {table ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-[13px]">
            <caption className="faint pb-2 text-left text-[12px]">Consequences by scope ({b.analysis.provider} provider, <SourceBadge s={b.analysis.source} />)</caption>
            <thead><tr className="hairline border-b text-left text-[11px] uppercase tracking-wider text-[var(--text-faint)]">
              <th className="py-2 pr-2">Ring</th><th className="py-2 pr-2">Scope</th><th className="py-2 pr-2">Consequence</th><th className="py-2 pr-2">Affected</th><th className="py-2">Status · timing · effect</th>
            </tr></thead>
            <tbody>
              {s.scopes.flatMap((sc) => by(sc.id).map((x, k) => (
                <tr key={x.id} className={`hairline border-b align-top ${relevant(sc.id) ? "" : "opacity-45"}`}>
                  <td className="num py-2 pr-2">{k === 0 ? sc.n : ""}</td>
                  <td className="py-2 pr-2 font-semibold">{k === 0 ? sc.title : ""}</td>
                  <td className="py-2 pr-2">{x.description}{x.evidence.length > 0 && <span className="faint"> (events {x.evidence.join(", ")})</span>}</td>
                  <td className="py-2 pr-2">{x.affected.map((id) => nameOf(s, id)).join(", ") || "—"}</td>
                  <td className="py-2"><Effects x={x} /></td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="flex flex-col gap-2">
            <svg viewBox={`0 0 ${size} ${size}`} className="mx-auto block w-full max-w-[540px]" role="group" aria-label="Consequence radius rings">
              {[...s.scopes].reverse().map((sc) => {
                const on = sel === sc.id;
                return (
                  <circle key={sc.id} cx={c} cy={c} r={r(sc.n)} fill={fill(sc.n)} fillOpacity={relevant(sc.id) ? 1 : 0.3}
                    stroke={on ? INK : "#fff"} strokeWidth={on ? 3.5 : 2.5} strokeDasharray={empty(sc.id) && !on ? "6 4" : undefined}
                    role="button" tabIndex={0} aria-pressed={on} aria-label={`Ring ${sc.n}: ${sc.title}${empty(sc.id) ? ", nothing specific identified" : ""}`}
                    className="cursor-pointer outline-none" onClick={() => setSel(sc.id)} onKeyDown={key(sc.id)} />
                );
              })}
              {s.scopes.map((sc) => (
                <text key={sc.id} x={c} y={c - r(sc.n) + step / 2 + 4} textAnchor="middle" fontSize={11} fontWeight={700} fill={INK}
                  opacity={relevant(sc.id) ? 1 : 0.45} pointerEvents="none">{sc.n} · {sc.short}</text>
              ))}
              <circle cx={c} cy={c} r={core - 4} fill={focus ? colors[focus] : INK} stroke="#fff" strokeWidth={3} />
              <text x={c} y={c - 2} textAnchor="middle" fontSize={12.5} fontWeight={800} letterSpacing={1} fill="#fff" pointerEvents="none">ACTION</text>
              <text x={c} y={c + 14} textAnchor="middle" fontSize={9.5} fill="#fff" opacity={0.85} pointerEvents="none">{focus ? `for ${nameOf(s, focus)}` : ""}</text>
            </svg>
            <p className="faint text-center text-[11.5px]">Rings are scopes to investigate, not a chain: effects can overlap or skip scopes. Dashed ring = nothing specific identified.</p>
          </div>
          <div className="flex flex-col gap-3">
            <ol className="grid grid-cols-2 gap-1.5 sm:grid-cols-4" aria-label="Scopes">
              {s.scopes.map((sc) => (
                <li key={sc.id}>
                  <button type="button" onClick={() => setSel(sc.id)} aria-pressed={sel === sc.id}
                    className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12px] font-semibold ring-1 ${sel === sc.id ? "bg-cyan-400/10 ring-cyan-400" : "ring-[var(--border)]"} ${relevant(sc.id) ? "" : "opacity-45"}`}>
                    <span className="num grid size-5 shrink-0 place-items-center rounded-full text-[11px]" style={{ background: fill(sc.n), color: INK }}>{sc.n}</span>
                    <span className="truncate">{sc.short}</span>
                  </button>
                </li>
              ))}
            </ol>
            {scope && (
              <section className="panel-raised flex flex-col gap-3 p-4" aria-live="polite">
                <header>
                  <p className="text-[11px] font-bold uppercase tracking-wider text-cyan-500">Ring {scope.n}</p>
                  <h3 className="text-[18px] font-bold">{scope.title}</h3>
                </header>
                <ul className="flex flex-col gap-2.5">
                  {by(scope.id).map((x) => (
                    <li key={x.id} className={`flex flex-col gap-1.5 rounded-lg border border-[var(--border)] p-3 ${focus && x.status !== "not_identified" && !x.affected.includes(focus) ? "opacity-45" : ""}`}>
                      <p className={`text-[13.5px] ${x.status === "possible" ? "italic" : ""}`}>{x.description}</p>
                      <Effects x={x} />
                      {x.evidence.length > 0 && <p className="faint text-[11.5px]">Supported by events {x.evidence.join(", ")}</p>}
                      {x.assumptions.length > 0 && <p className="faint text-[11.5px]">Assumes: {x.assumptions.join("; ")}</p>}
                      {x.questions.length > 0 && <p className="faint text-[11.5px]">Open: {x.questions.join("; ")}</p>}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
