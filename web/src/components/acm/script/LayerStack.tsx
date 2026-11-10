"use client";

/**
 * D · World layers: the scene seen through ACM's layer stack. The action sits at the bottom;
 * the consequence router (layer 3) shows which layers, actors and objects each event was sent
 * to and why; every other layer lists the consequences the analysis records there. The routing
 * table doubles as the accessible, non-visual view of the whole stack.
 */

import { useState } from "react";
import { nameOf, type LayerId, type SceneBundle } from "@/lib/acm/scene";
import { LAYER_FILL, LayerFacts, LayerStackView } from "@/components/acm/WorldLayers";
import { HORIZON, StatusBadge, ValenceTag } from "./shared";

export function LayerStack({ b, focus, action }: { b: SceneBundle; colors: Record<string, string>; focus: string | null; action: string }) {
  const s = b.scene;
  const layers = b.layers;
  const [sel, setSel] = useState<LayerId>("routing");
  const l = layers.find((x) => x.id === sel) ?? layers[0];
  const at = (id: LayerId) => b.analysis.consequences.filter((c) => c.layer === id);
  const routedTo = (id: LayerId) => b.routing.filter((row) => row.routes.some((r) => r.layer === id));
  const concerns = (id: LayerId) => !focus || at(id).some((c) => c.affected.includes(focus))
    || b.routing.some((row) => row.routes.some((r) => r.layer === id && r.actors.includes(focus)));
  const count = (id: LayerId) => id === "action" ? s.events.length : id === "routing" ? b.routing.length : at(id).filter((c) => c.status !== "not_identified").length;
  const ev = (id: string) => s.events.find((e) => e.id === id);
  const shown = layers.filter((x) => x.id !== "action" && x.id !== "routing");

  return (
    <div className="flex flex-col gap-4">
      <p className="dim max-w-3xl text-[13.5px] leading-relaxed">
        The same scene, sorted by <b className="text-[var(--text)]">which kind of system</b> each consequence is about. Bottom-up: the action happens in the
        physical world, is perceived, and the <b className="text-[var(--text)]">consequence router</b> sends each event to the world models that should
        examine it. The radius (next section) is the other axis: <i>how far</i> a consequence reaches.
      </p>
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <div className="flex flex-col gap-1.5">
          <LayerStackView layers={layers} selected={sel} onSelect={setSel} count={count} dim={(id) => !concerns(id)} />
          <p className="faint text-[11.5px]">Numbers: events (0), routed events (3), identified consequences (other layers). {focus ? `Dimmed: nothing recorded for ${nameOf(s, focus)}.` : ""}</p>
        </div>

        <section className="panel-raised flex flex-col gap-3 p-4" aria-live="polite">
          <header>
            <p className="text-[11px] font-bold uppercase tracking-wider text-cyan-500">{l.id === "action" ? "The source" : `Layer ${l.level}`}</p>
            <h3 className="text-[18px] font-bold">{l.icon} {l.name}</h3>
          </header>
          <LayerFacts l={l} />

          {l.id === "action" && (
            <div className="flex flex-col gap-1.5 border-t border-[var(--border)] pt-3 text-[13px]">
              <p><b>{action}</b></p>
              <ol className="flex flex-col gap-0.5">
                {s.events.map((e) => <li key={e.id}><span className="num faint mr-1.5">{e.id}</span>{e.actor ? <b>{nameOf(s, e.actor)}: </b> : null}{e.description}</li>)}
              </ol>
            </div>
          )}

          {l.id === "routing" && (
            <div className="flex flex-col gap-2 border-t border-[var(--border)] pt-3">
              <p className="text-[13px] font-semibold">Where each event was routed, and why</p>
              <ul className="flex flex-col gap-2">
                {b.routing.map((row) => {
                  const e = ev(row.event);
                  return (
                    <li key={row.event} className={`rounded-lg border border-[var(--border)] p-2.5 ${focus && !row.routes.some((r) => r.actors.includes(focus)) ? "opacity-45" : ""}`}>
                      <p className="text-[13px]"><span className="num faint mr-1.5">{row.event}</span>{e?.description}</p>
                      <ul className="mt-1.5 flex flex-col gap-1">
                        {row.routes.map((r) => {
                          const target = layers.find((x) => x.id === r.layer);
                          return (
                            <li key={r.layer} className="flex flex-wrap items-baseline gap-x-2 text-[12px]">
                              <button type="button" onClick={() => setSel(r.layer)} className="rounded px-1.5 py-0.5 font-semibold text-[#0b1b2e]" style={{ background: LAYER_FILL[r.layer] }}>
                                → {target?.icon} {target?.name}
                              </button>
                              <span className="dim">{r.reasons.join("; ")}</span>
                              {(r.actors.length > 0 || r.objects.length > 0) && <span className="faint">({[...r.actors, ...r.objects].map((id) => nameOf(s, id)).join(", ")})</span>}
                            </li>
                          );
                        })}
                      </ul>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {l.id !== "action" && l.id !== "routing" && (
            <div className="flex flex-col gap-2 border-t border-[var(--border)] pt-3">
              <p className="text-[13px] font-semibold">Consequences at this layer</p>
              {at(l.id).length === 0 && <p className="faint text-[13px]">None recorded. That means nothing was identified here, not that nothing happens.</p>}
              <ul className="flex flex-col gap-2">
                {at(l.id).map((x) => (
                  <li key={x.id} className={`flex flex-col gap-1.5 rounded-lg border border-[var(--border)] p-3 ${focus && x.status !== "not_identified" && !x.affected.includes(focus) ? "opacity-45" : ""}`}>
                    <p className={`text-[13.5px] ${x.status === "possible" ? "italic" : ""}`}>{x.description}</p>
                    <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                      <StatusBadge s={x.status} />
                      {x.status !== "not_identified" && <span className="faint text-[11.5px] font-semibold">{HORIZON[x.horizon]}</span>}
                      <span className="faint text-[11.5px]">ring: {s.scopes.find((sc) => sc.id === x.scope)?.title ?? x.scope}</span>
                      {Object.entries(x.effect).map(([id, v]) => <ValenceTag key={id} v={v} who={nameOf(s, id)} />)}
                    </span>
                    {x.evidence.length > 0 && <p className="faint text-[11.5px]">Supported by events {x.evidence.join(", ")}</p>}
                  </li>
                ))}
              </ul>
              {routedTo(l.id).length > 0 && (
                <p className="faint text-[11.5px]">Routed here: events {routedTo(l.id).map((r) => r.event).join(", ")}.</p>
              )}
            </div>
          )}
        </section>
      </div>

      <details className="rounded-lg border border-[var(--border)] p-3">
        <summary className="cursor-pointer text-[13px] font-semibold">Routing table (every event × every world layer)</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-[12px]">
            <caption className="faint pb-2 text-left text-[11.5px]">✓ = the router sent the event to that layer. Rules and cited evidence, from acm.scene.layers.route.</caption>
            <thead><tr className="hairline border-b text-left">
              <th className="py-1.5 pr-2">Event</th>
              {shown.map((x) => <th key={x.id} className="px-1 py-1.5 text-center" title={x.name}><span aria-hidden>{x.icon}</span><span className="sr-only">{x.name}</span><span className="faint block text-[10px]">{x.level}</span></th>)}
            </tr></thead>
            <tbody>
              {b.routing.map((row) => (
                <tr key={row.event} className="hairline border-b">
                  <td className="py-1.5 pr-2"><span className="num faint mr-1">{row.event}</span>{ev(row.event)?.description}</td>
                  {shown.map((x) => {
                    const r = row.routes.find((y) => y.layer === x.id);
                    return <td key={x.id} className="px-1 py-1.5 text-center" title={r?.reasons.join("; ")}>{r ? "✓" : <span className="faint">·</span>}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
