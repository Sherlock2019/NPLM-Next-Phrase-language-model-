"use client";

/** A · Scene overview: what, where, when, who (with goals), which objects, the transaction, status. */

import { nameOf, type SceneBundle } from "@/lib/acm/scene";
import { Player } from "./ScriptPlayer";
import { Dot, SourceBadge, StatusBadge } from "./shared";

export function Overview({ b, colors, focus }: { b: SceneBundle; colors: Record<string, string>; focus: string | null }) {
  const s = b.scene;
  const end = b.timeline[b.timeline.length - 1].state;
  const obligations = s.objects.filter((o) => o.kind === "obligation");
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex flex-col gap-2">
          <Player scene={s} state={b.timeline[0].state} event={null} colors={colors} focus={focus} />
          <p className="faint text-[11.5px]">Starting positions, drawn from the scene’s stage marks. A 2D player: no 3D, no physics.</p>
        </div>
        <div className="flex flex-col gap-3">
          <dl className="panel-raised grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 p-4 text-[13.5px]">
            <dt className="faint font-semibold">Location</dt><dd>{s.location.name}{s.location.city ? `, ${s.location.city}` : ""}</dd>
            <dt className="faint font-semibold">Time</dt><dd>{s.time}</dd>
            <dt className="faint font-semibold">Status</dt>
            <dd><span className="rounded-md bg-amber-400/15 px-2 py-0.5 font-semibold text-amber-500 ring-1 ring-amber-400/40">{s.status}</span></dd>
            <dt className="faint font-semibold">At the end</dt>
            <dd className="dim">{Object.entries(end.scene ?? {}).map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v)}`).join(" · ")}</dd>
          </dl>
          <div className="panel-raised flex flex-col gap-2 p-4">
            <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-faint)]">People</p>
            {s.actors.map((a) => (
              <div key={a.id} className={`text-[13px] ${focus && focus !== a.id ? "opacity-40" : ""}`}>
                <p className="flex items-center gap-2"><Dot color={colors[a.id]} /><b style={{ color: colors[a.id] }}>{a.name}</b><span className="dim">· {a.role}</span></p>
                <p className="dim pl-[18px]">{[...a.goals.map((g) => `Goal: ${g}`), ...a.preferences].join(" · ") || "No goal stated"}</p>
              </div>
            ))}
          </div>
          <div className="panel-raised flex flex-col gap-1.5 p-4 text-[13px]">
            <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-faint)]">Objects and the transaction</p>
            {s.objects.filter((o) => o.kind === "physical").map((o) => (
              <p key={o.id}><b>{o.label}</b> <span className="dim">· {o.description}{o.owner ? ` · owner: ${nameOf(s, o.owner)}` : ""}{o.holder ? ` · held by ${nameOf(s, o.holder)}` : ""}</span></p>
            ))}
            {obligations.map((o) => (
              <p key={o.id}><b>{o.label}</b> <span className="dim">· {o.description} · status at the end: {String(end[o.id]?.status ?? o.attributes.status)}</span></p>
            ))}
          </div>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="panel-raised p-4">
          <p className="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-[var(--text-faint)]">Context <SourceBadge s="scenario_fact" /></p>
          <ul className="list-disc pl-5 text-[13.5px]">{s.context.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>
        <div className="panel-raised p-4">
          <p className="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-[var(--text-faint)]">Not established <StatusBadge s="unknown" /></p>
          <ul className="list-disc pl-5 text-[13.5px]">{s.unknowns.map((c) => <li key={c}>{c}</li>)}</ul>
          <p className="mb-1 mt-3 text-[11px] font-bold uppercase tracking-wider text-[var(--text-faint)]">Caveats</p>
          <ul className="list-disc pl-5 text-[13px] text-amber-500">{s.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>
      </div>
    </div>
  );
}
