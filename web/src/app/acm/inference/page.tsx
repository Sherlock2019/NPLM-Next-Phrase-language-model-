"use client";

/**
 * "What happens next?" - the ARM inference explorer.
 *
 * 53 scenarios, each answered by ARM subject by subject (the actor, the people and
 * things it lands on, other people's goals, the place, the wider layers, and what
 * ARM cannot tell), with the reasoning it actually followed and three visual views.
 * Answers are assembled from the engine's own records; the parses are real MLM
 * (Stanza) parses frozen in ARM's examples/inference_suite.conllu.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buttonClass, buttonGhostClass, inputClass, ErrorBox, Loading } from "@/components/ui";
import { BlastRadius } from "@/components/acm/BlastRadius";
import { AnswerCard, EntityGraph, ReasoningChain } from "@/components/acm/Inference";
import { HowItWorks } from "@/components/acm/HowItWorks";
import { Intro } from "@/components/acm/Intro";
import type { InferenceItem, InferenceSuite } from "@/lib/multimodal/types";

type View = "reasoning" | "graph" | "rings" | "report";
const VIEWS: [View, string][] = [["reasoning", "Reasoning chain"], ["graph", "Who is affected"], ["rings", "Blast radius"], ["report", "ARM report"]];

export default function InferencePage() {
  const [suite, setSuite] = useState<InferenceSuite | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<string>("All");
  const [query, setQuery] = useState("");
  const [current, setCurrent] = useState(0);
  const [open, setOpen] = useState<Set<number>>(new Set([0]));
  const [view, setView] = useState<View>("reasoning");
  const [step, setStep] = useState(7);
  const [playing, setPlaying] = useState(false);
  const [typing, setTyping] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    fetch("/demo/inference_suite.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`inference_suite.json ${r.status}`))))
      .then(setSuite)
      .catch((e: Error) => setError(`The inference suite could not be loaded: ${e.message}. Run ARM's ./start.sh to generate it.`));
  }, []);

  const items = useMemo(() => {
    if (!suite) return [];
    const q = query.trim().toLowerCase();
    return suite.items.filter(
      (it) =>
        (theme === "All" || it.theme === theme) &&
        (!q || [it.action, ...it.context, it.shows, it.summary.concept ?? ""].join(" ").toLowerCase().includes(q)),
    );
  }, [suite, theme, query]);

  const item: InferenceItem | undefined = items[Math.min(current, items.length - 1)];

  const clearTimers = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };

  /** Show one scenario the way ARM works through it: reasoning step by step, then each answer. */
  const present = useCallback((index: number, animate: boolean) => {
    clearTimers();
    setCurrent(index);
    if (!animate) {
      setStep(7);
      setOpen(new Set([0]));
      setTyping(false);
      return 0;
    }
    setTyping(true);
    setStep(-1);
    setOpen(new Set());
    const target = items[index];
    const n = target?.answers.length ?? 0;
    for (let s = 0; s < 8; s++) timers.current.push(window.setTimeout(() => setStep(s), 220 * s));
    for (let a = 0; a < n; a++)
      timers.current.push(window.setTimeout(() => setOpen((o) => new Set([...o, a])), 1900 + 650 * a));
    return 1900 + 650 * n + 900;
  }, [items]);

  useEffect(() => () => clearTimers(), []);

  // Play mode: walk through every scenario in the current filter.
  useEffect(() => {
    if (!playing || !items.length) return;
    let cancelled = false;
    const run = (i: number) => {
      if (cancelled || i >= items.length) {
        setPlaying(false);
        return;
      }
      const duration = present(i, true);
      timers.current.push(window.setTimeout(() => run(i + 1), duration));
    };
    run(current);
    return () => {
      cancelled = true;
      clearTimers();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowRight") present(Math.min(current + 1, items.length - 1), true);
      if (e.key === "ArrowLeft") present(Math.max(current - 1, 0), true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, items.length, present]);

  if (error) return <ErrorBox error={error} />;
  if (!suite) return <Loading label="Loading 53 inferences" />;
  const stats = suite.stats;

  return (
    <div className="flex flex-col gap-4">
      <Intro page="inference" />
      <header className="panel flex flex-col gap-3 p-5">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-semibold tracking-tight">What happens next?</h1>
            <p className="dim mt-1 max-w-4xl text-[13px] leading-relaxed">
              {stats.scenarios} actions, {stats.questions} questions. For each one ARM answers what happens next to everyone and
              everything the action touches — the actor, the people and things it lands on, other people&apos;s plans, the place,
              its neighbours, organization, city and country, society and the earth — and shows the reasoning behind every answer.
            </p>
          </div>
          <div className="flex gap-2">
            {playing ? (
              <button type="button" className={buttonClass} onClick={() => { setPlaying(false); clearTimers(); }}>■ Stop</button>
            ) : (
              <button type="button" className={`${buttonClass} px-5 py-2.5 text-sm`} onClick={() => setPlaying(true)} disabled={!items.length}>
                ▶ Play all {items.length}
              </button>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 text-[11px]">
          {Object.entries(stats.relations).map(([k, v]) => (
            <span key={k} className="panel-raised px-2 py-0.5"><b>{v}</b> goals {k.replace("_", " ")}</span>
          ))}
          {Object.entries(stats.layers_reached).map(([k, v]) => (
            <span key={k} className="panel-raised px-2 py-0.5"><b>{v}</b>× reaches {k}</span>
          ))}
          <span className="panel-raised px-2 py-0.5"><b>{stats.concepts.length}</b> concepts</span>
        </div>
        <p className="faint text-[10.5px]">
          Parses: {suite.parse}. Answers are assembled from ARM&apos;s own trace (rules, roles, goal comparisons) — no language model writes them.
          Certainty values are rule weights, not probabilities.
        </p>
        <HowItWorks inputs={["phrase"]} page="inference" />
      </header>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <aside className="panel flex max-h-[80vh] flex-col overflow-hidden">
          <div className="hairline flex flex-col gap-2 border-b p-3">
            <input className={inputClass} placeholder="Search actions…" value={query} onChange={(e) => { setQuery(e.target.value); setCurrent(0); }} aria-label="Search scenarios" />
            <div className="flex flex-wrap gap-1">
              {["All", ...Object.keys(stats.themes)].map((t) => (
                <button key={t} type="button" onClick={() => { setTheme(t); setCurrent(0); }} aria-pressed={theme === t}
                  className={`rounded px-2 py-0.5 text-[11px] ${theme === t ? "bg-splm-500/20 text-splm-300" : "dim hover:bg-white/5"}`}>
                  {t}{t !== "All" ? ` · ${stats.themes[t]}` : ""}
                </button>
              ))}
            </div>
          </div>
          <ol className="flex-1 overflow-y-auto p-1.5" aria-label="Scenarios">
            {items.map((it, i) => (
              <li key={it.id}>
                <button type="button" onClick={() => present(i, true)} aria-current={i === current}
                  className={`w-full rounded-md px-2.5 py-1.5 text-left text-[12px] leading-snug ${i === current ? "bg-splm-500/15 text-[var(--text)]" : "dim hover:bg-white/4"}`}>
                  <span className="num faint mr-1.5">{it.id.slice(1)}</span>
                  {it.action}
                  <span className="faint block text-[10.5px]">{it.summary.concept ?? "no concept"} · {it.theme}</span>
                </button>
              </li>
            ))}
            {items.length === 0 && <li className="faint p-3 text-xs">No scenario matches.</li>}
          </ol>
        </aside>

        {item && (
          <main className="flex flex-col gap-4">
            <section className="panel p-4">
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span className="faint">{item.theme} · scenario {current + 1} of {items.length}</span>
                <span className="ml-auto flex gap-1.5">
                  <button type="button" className={buttonGhostClass} onClick={() => present(Math.max(current - 1, 0), true)} disabled={current === 0}>← prev</button>
                  <button type="button" className={buttonGhostClass} onClick={() => present(Math.min(current + 1, items.length - 1), true)} disabled={current >= items.length - 1}>next →</button>
                </span>
              </div>
              {item.context.length > 0 && (
                <p className="dim mt-2 text-[12.5px]">
                  <span className="eyebrow mr-2">context</span>
                  {item.context.map((c) => `“${c}”`).join("  ")}
                </p>
              )}
              <p className="mt-1.5 text-[19px] font-semibold leading-snug">“{item.action}”</p>
              <p className="faint mt-1 text-[11.5px]">Shows: {item.shows}</p>
            </section>

            <div className="grid gap-4 xl:grid-cols-2">
              <section className="panel p-4">
                <div className="mb-2 flex items-center gap-2">
                  <h2 className="eyebrow flex-1">Ask ARM</h2>
                  <button type="button" className="dim text-[11px] underline" onClick={() => { setTyping(false); setOpen(new Set(item.answers.map((_, i) => i))); }}>
                    answer all
                  </button>
                </div>
                <ul className="flex flex-col gap-1.5">
                  {item.answers.map((qa, i) => (
                    <AnswerCard key={`${item.id}-${i}`} qa={qa} typing={typing} open={open.has(i)}
                      onToggle={() => setOpen((o) => { const n = new Set(o); if (n.has(i)) n.delete(i); else n.add(i); return n; })} />
                  ))}
                </ul>
              </section>

              <section className="panel flex flex-col">
                <div role="tablist" aria-label="Visualizations" className="hairline flex flex-wrap gap-1 border-b p-2">
                  {VIEWS.map(([key, label]) => (
                    <button key={key} role="tab" aria-selected={view === key} type="button" onClick={() => setView(key)}
                      className={`rounded px-2.5 py-1 text-[11.5px] font-medium ${view === key ? "bg-splm-500/15 text-splm-300" : "dim hover:bg-white/5"}`}>
                      {label}
                    </button>
                  ))}
                </div>
                <div className="p-4">
                  {view === "reasoning" && <ReasoningChain item={item} active={step} />}
                  {view === "graph" && (
                    <>
                      <EntityGraph item={item} />
                      <p className="faint mt-1 text-[10.5px]">
                        Centre: the action and its concept. Around it: everyone and everything it changes. Dashed lines are other people&apos;s
                        goals — green advanced, red blocked, amber at risk or hindered.
                      </p>
                    </>
                  )}
                  {view === "rings" && <BlastRadius rings={item.rings} />}
                  {view === "report" && (
                    <pre className="num max-h-[60vh] overflow-auto text-[11px] leading-relaxed">{item.report_text}</pre>
                  )}
                </div>
              </section>
            </div>
          </main>
        )}
      </div>
    </div>
  );
}
