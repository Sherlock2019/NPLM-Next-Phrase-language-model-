"use client";

/**
 * C · Actor cards. What the script says (role, goal, stated position, actions in the script)
 * is kept apart from what the demo infers (possible thoughts, feelings, reactions), from the
 * consequences that concern the actor, and from what is unknown.
 */

import { nameOf, type SceneBundle } from "@/lib/acm/scene";
import { STATUS, SourceBadge, StatusBadge, ValenceTag } from "./shared";

export function ActorCards({ b, colors, focus, setFocus }: {
  b: SceneBundle; colors: Record<string, string>; focus: string | null; setFocus: (id: string | null) => void;
}) {
  const s = b.scene;
  return (
    <div className="flex flex-col gap-3">
      <p className="dim flex flex-wrap items-center gap-2 text-[13px]">
        A model cannot observe thoughts or feelings. <StatusBadge s="stated" /> comes from the script; <StatusBadge s="possible" /> is an inference;
        <StatusBadge s="unknown" /> is not established.
      </p>
      <div className="grid gap-3 lg:grid-cols-3">
        {s.actors.map((a) => {
          const c = colors[a.id];
          const acts = s.events.filter((e) => e.actor === a.id);
          const cons = b.analysis.consequences.filter((x) => x.affected.includes(a.id));
          return (
            <article key={a.id} className={`panel-raised flex flex-col gap-3 border-t-4 p-4 ${focus && focus !== a.id ? "opacity-50" : ""}`} style={{ borderTopColor: c }}>
              <header className="flex items-start gap-3">
                <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-full text-[16px] font-extrabold text-white" style={{ background: c }}>{a.name[0]}</span>
                <div className="min-w-0 flex-1">
                  <h3 className="text-[17px] font-bold" style={{ color: c }}>{a.name}</h3>
                  <p className="dim text-[12.5px]">{a.role}</p>
                  <p className="faint text-[11.5px]">{Object.entries(a.relationships).map(([k, v]) => `${nameOf(s, k)}: ${v}`).join(" · ")}</p>
                </div>
                <button type="button" aria-pressed={focus === a.id} onClick={() => setFocus(focus === a.id ? null : a.id)}
                  className="shrink-0 rounded-lg px-2.5 py-1 text-[12px] font-semibold ring-1 ring-[var(--border)]"
                  style={focus === a.id ? { background: c, color: "#fff" } : undefined}>
                  {focus === a.id ? "✓ Focused" : "Focus"}
                </button>
              </header>

              <section>
                <p className="mb-1 flex items-center gap-2"><StatusBadge s="stated" /><span className="faint text-[11px]">what the script says</span></p>
                <dl className="flex flex-col gap-1 text-[13px]">
                  <div><dt className="faint inline font-semibold">Known goal: </dt><dd className="inline">{a.goals.join("; ") || "none stated"}</dd></div>
                  <div><dt className="faint inline font-semibold">Stated position: </dt><dd className="inline">{a.preferences.join("; ") || "none stated"}</dd></div>
                  <div>
                    <dt className="faint font-semibold">Actions and words in the script</dt>
                    <dd><ul className="list-disc pl-5">{acts.map((e) => <li key={e.id}>{e.dialogue ? `“${e.dialogue}”` : e.description}</li>)}</ul></dd>
                  </div>
                </dl>
              </section>

              <section>
                <p className="mb-1 flex items-center gap-2"><StatusBadge s="possible" /><span className="faint text-[11px]">{STATUS.possible.hint}</span></p>
                <ul className="flex flex-col gap-1 text-[13px] italic">
                  {a.inferences.map((x) => <li key={x.text}><span className="faint not-italic font-semibold">{x.kind}: </span>{x.text}</li>)}
                </ul>
              </section>

              <section>
                <p className="faint mb-1 text-[11px] font-bold uppercase">Potential consequences for {a.name}</p>
                <ul className="flex flex-col gap-1.5 text-[13px]">
                  {cons.map((x) => (
                    <li key={x.id} className="flex flex-col gap-0.5">
                      <span>{x.description}</span>
                      <span className="flex flex-wrap items-center gap-2"><StatusBadge s={x.status} />{x.effect[a.id] && <ValenceTag v={x.effect[a.id]} who={a.name} />}</span>
                    </li>
                  ))}
                </ul>
              </section>

              <section>
                <p className="mb-1 flex items-center gap-2"><StatusBadge s="unknown" /></p>
                <ul className="list-disc pl-5 text-[13px]">{a.unknown.map((u) => <li key={u}>{u}</li>)}</ul>
              </section>
              <p className="mt-auto"><SourceBadge s="authored_demo" /></p>
            </article>
          );
        })}
      </div>
    </div>
  );
}
