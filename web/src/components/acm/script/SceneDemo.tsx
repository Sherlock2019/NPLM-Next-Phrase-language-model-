"use client";

/**
 * ACM scene demo, rendered from a scene bundle written by the ACM scene engine
 * (`acm scene bundle` / `acm demo --json` → public/demo/scene_<id>.json).
 *
 *   A Scene overview · B Actions and dialogue · C Actors · D Consequence radius · E Next scenes
 *
 * An actor focus applies across every section; "Show all" lays them out on one page.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { actorColors, type SceneBundle } from "@/lib/acm/scene";
import { ActorCards } from "./ActorCards";
import { Branches, ExportButton } from "./Branches";
import { Overview } from "./Overview";
import { RadiusMap } from "./RadiusMap";
import { ScriptPlayer } from "./ScriptPlayer";
import { SourceBadge, StatusBadge } from "./shared";

const STAGES = [
  { k: "A", title: "Scene overview", hint: "Where, when, who, what is at stake" },
  { k: "B", title: "Actions and dialogue", hint: "The script, step by step" },
  { k: "C", title: "Actors", hint: "Goals, behaviour, possible feelings, unknowns" },
  { k: "D", title: "Consequence radius", hint: "Eight scopes around the action" },
  { k: "E", title: "Next scenes", hint: "Possible continuations and export" },
];

export function SceneDemo({ b, initialStage = 0, initialAll = false }: { b: SceneBundle; initialStage?: number; initialAll?: boolean }) {
  const s = b.scene;
  const colors = actorColors(s);
  const [stage, setStage] = useState(Math.min(Math.max(initialStage, 0), STAGES.length - 1));
  const [all, setAll] = useState(initialAll);
  const [focus, setFocus] = useState<string | null>(null);
  const top = useRef<HTMLDivElement>(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    if (!all) top.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [stage, all]);

  const action = s.action ?? s.description;
  const views: ReactNode[] = [
    <Overview key="a" b={b} colors={colors} focus={focus} />,
    <div key="b" className="flex flex-col gap-3">
      <ScriptPlayer scene={s} events={s.events} steps={b.timeline} colors={colors} focus={focus} label="Scene 1" />
      <ExportButton directions={b.directions} name={`${s.id}_scene1_directions.json`} />
    </div>,
    <ActorCards key="c" b={b} colors={colors} focus={focus} setFocus={setFocus} />,
    <RadiusMap key="d" b={b} colors={colors} focus={focus} action={action} />,
    <Branches key="e" b={b} colors={colors} focus={focus} />,
  ];

  return (
    <div className="flex flex-col gap-5">
      <header className="panel flex flex-col gap-3 p-5 sm:p-7">
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-cyan-500">ACM · Action–Consequence Model · scene engine</p>
        <h1 className="text-[26px] font-extrabold leading-tight tracking-tight sm:text-[34px]">{s.title}</h1>
        <p className="text-[17px] font-semibold">Can a model understand what an action might cause?</p>
        <p className="dim max-w-3xl text-[14.5px] leading-relaxed">{s.description}</p>
        <p className="faint flex flex-wrap items-center gap-2 text-[12px]">
          Labels: <SourceBadge s="scenario_fact" /> <SourceBadge s="authored_demo" /> <SourceBadge s="generated_inference" /> ·
          <StatusBadge s="stated" /> <StatusBadge s="possible" /> <StatusBadge s="unknown" /> <StatusBadge s="not_identified" />
        </p>
        <p className="faint text-[12px]">
          Rendered from <code className="num">{s.schema}</code> data produced by the ACM scene engine ({b.generated_by}). The script, analysis and four branches are
          authored demo content, deterministic and offline: they show the reasoning format, not live predictions.
        </p>
      </header>

      <div ref={top} className="sticky z-30 flex scroll-mt-[calc(var(--nav-h,72px)+8px)] flex-col gap-2 rounded-xl border border-[var(--border)] bg-[var(--page)]/95 p-2 backdrop-blur"
        style={{ top: "calc(var(--nav-h, 72px) + 4px)" }}>
        <nav aria-label="Demo sections" className="flex gap-1 overflow-x-auto">
          {STAGES.map((st, k) => (
            <button key={st.k} type="button" onClick={() => { setAll(false); setStage(k); }} aria-current={!all && stage === k ? "step" : undefined}
              className={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-1.5 text-[13px] font-semibold transition-colors ${!all && stage === k ? "bg-cyan-400 text-[#0b1b2e]" : "hover:bg-[var(--panel-raised)]"}`}>
              <span className="num">{st.k}</span><span className="hidden sm:inline">{st.title}</span>
            </button>
          ))}
          <button type="button" onClick={() => setAll(!all)} aria-pressed={all}
            className={`ml-auto shrink-0 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold ring-1 ${all ? "text-cyan-500 ring-cyan-400" : "ring-[var(--border)]"}`}>
            {all ? "Step by step" : "Show all"}
          </button>
        </nav>
        <div className="flex flex-wrap items-center gap-1.5 px-1 text-[12.5px]" role="group" aria-label="Focus on an actor">
          <span className="faint mr-1 font-semibold">Focus:</span>
          <button type="button" aria-pressed={focus === null} onClick={() => setFocus(null)}
            className={`rounded-full px-2.5 py-0.5 font-semibold ring-1 ${focus === null ? "bg-[var(--text)] text-[var(--page)] ring-transparent" : "ring-[var(--border)]"}`}>Everyone</button>
          {s.actors.map((a) => (
            <button key={a.id} type="button" aria-pressed={focus === a.id} onClick={() => setFocus(focus === a.id ? null : a.id)}
              className="rounded-full px-2.5 py-0.5 font-semibold ring-1"
              style={focus === a.id ? { background: colors[a.id], color: "#fff" } : { color: colors[a.id], boxShadow: `inset 0 0 0 1px ${colors[a.id]}66` }}>
              {a.name}
            </button>
          ))}
        </div>
      </div>

      {STAGES.map((st, k) => (all || stage === k) && (
        <section key={st.k} className="panel flex flex-col gap-4 p-4 sm:p-6" aria-labelledby={`sec-${st.k}`}>
          <header className="flex items-start gap-3">
            <span className="num grid size-9 shrink-0 place-items-center rounded-full bg-cyan-400/15 text-[15px] font-bold text-cyan-500">{st.k}</span>
            <div>
              <h2 id={`sec-${st.k}`} className="text-[21px] font-extrabold tracking-tight">{st.title}</h2>
              <p className="dim text-[13px]">{st.hint}</p>
            </div>
          </header>
          {views[k]}
        </section>
      ))}

      {!all && (
        <div className="flex justify-between gap-2">
          <button type="button" disabled={stage === 0} onClick={() => setStage(stage - 1)}
            className="rounded-lg border border-[var(--border)] px-4 py-2 text-[14px] font-semibold disabled:opacity-40">← {stage > 0 ? STAGES[stage - 1].title : "Previous"}</button>
          <button type="button" disabled={stage === STAGES.length - 1} onClick={() => setStage(stage + 1)}
            className="rounded-lg bg-cyan-400 px-4 py-2 text-[14px] font-semibold text-[#0b1b2e] disabled:opacity-40">{stage < STAGES.length - 1 ? STAGES[stage + 1].title : "Done"} →</button>
        </div>
      )}
    </div>
  );
}
