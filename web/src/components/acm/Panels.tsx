"use client";

/**
 * The three ARM demo panels. Each one shows the tool as intended:
 *   input  ->  MLM meaning  ->  (prediction, for physical scenes)  ->  ARM blast radius
 * and exposes run(): Promise<void> so the page's "Run Demo" can drive all three.
 */

import { forwardRef, useImperativeHandle, useMemo, useRef, useState } from "react";
import { buttonClass, buttonGhostClass, inputClass, Caveat, ErrorBox } from "@/components/ui";
import { StatusTag } from "@/components/multimodal/Stages";
import { TabletopScene } from "@/components/multimodal/TabletopScene";
import { toSimAction, toSimScene } from "@/components/multimodal/Results";
import { simulate } from "@/lib/multimodal/tabletop";
import type { ActionKey, DemoBundle, PhraseResult, Scenario } from "@/lib/multimodal/types";
import { ACTION_KEYS } from "@/lib/multimodal/types";
import { BlastRadius } from "./BlastRadius";
import { PhraseChat } from "./Chat";
import { HowItWorks } from "./HowItWorks";
import { PhysicsLab, type LabHandle } from "./PhysicsLab";

export interface PanelHandle {
  run: () => Promise<void>;
}

type Step = { label: string; state: "waiting" | "running" | "done" | "error" };
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function Steps({ steps }: { steps: Step[] }) {
  if (steps.length === 0) return null;
  const mark = { waiting: "○", running: "◌", done: "●", error: "✕" } as const;
  const tone = { waiting: "faint", running: "text-splm-300 animate-pulse-soft", done: "text-ok-400", error: "text-danger-400" } as const;
  return (
    <ol className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px]" aria-live="polite">
      {steps.map((s) => (
        <li key={s.label} className={`flex items-center gap-1.5 ${tone[s.state]}`}>
          <span aria-hidden>{mark[s.state]}</span>
          <span>{s.label}</span>
          <span className="sr-only">{s.state}</span>
        </li>
      ))}
    </ol>
  );
}

function useSteps(labels: string[]) {
  const [steps, setSteps] = useState<Step[]>([]);
  const start = () => setSteps(labels.map((label) => ({ label, state: "waiting" })));
  const set = (i: number, state: Step["state"]) =>
    setSteps((s) => s.map((step, j) => (j === i ? { ...step, state } : step)));
  return { steps, start, set, clear: () => setSteps([]) };
}

function PanelShell({ id, title, subtitle, children }: { id: string; title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <section id={id} className="panel scroll-mt-[calc(var(--nav-h,60px)+52px)]">
      <header className="hairline flex flex-wrap items-baseline gap-x-3 border-b px-4 py-3">
        <h2 className="text-[15px] font-semibold">{title}</h2>
        <p className="dim text-[12px]">{subtitle}</p>
      </header>
      <div className="flex flex-col gap-4 p-4">{children}</div>
    </section>
  );
}

function MeaningLine({ items }: { items: [string, string | null | undefined, string][] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {items.map(([label, value, status]) => (
        <span key={label} className="panel-raised flex items-center gap-1.5 px-2 py-1 text-[11.5px]">
          <span className="eyebrow">{label}</span>
          <span className="font-medium">{value ?? "unknown"}</span>
          <StatusTag status={value ? status : "unknown"} />
        </span>
      ))}
    </div>
  );
}

// -- phrase ------------------------------------------------------------------------------------

export const PhrasePanel = forwardRef<
  PanelHandle,
  { demo: DemoBundle; live: boolean; liveReason: string; running: boolean; autoShow?: boolean }
>(
  function PhrasePanel({ demo, live, liveReason, running, autoShow = false }, ref) {
    const examples = demo.phrases;
    const [index, setIndex] = useState(0);
    const [text, setText] = useState(examples[0].text);
    const [context, setContext] = useState(examples[0].context.join("\n"));
    // autoShow: open on the first example's (precomputed) result, as the README does.
    const [result, setResult] = useState<PhraseResult | null>(autoShow ? examples[0] : null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const s = useSteps(["MLM reads the meaning", "ARM predicts the consequences"]);
    const example = examples[index];
    const edited = text.trim() !== example.text || context.trim() !== example.context.join("\n");

    function choose(i: number) {
      setIndex(i);
      setText(examples[i].text);
      setContext(examples[i].context.join("\n"));
      setResult(null);
      setError(null);
      s.clear();
    }

    async function run() {
      if (busy) return;
      setBusy(true);
      setError(null);
      setResult(null);
      s.start();
      try {
        s.set(0, "running");
        let next: PhraseResult;
        if (edited) {
          if (!live) throw new Error("Your own sentence needs Live mode (the MLM parser). Pick an example, or switch to Live.");
          const response = await fetch("/api/acm/phrase", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, context: context.split("\n").map((c) => c.trim()).filter(Boolean) }),
          });
          const body = await response.json();
          if (!response.ok) throw new Error(body?.detail ?? `${response.status}`);
          next = body as PhraseResult;
        } else {
          await wait(450);
          next = example;
        }
        s.set(0, "done");
        s.set(1, "running");
        await wait(350);
        setResult(next);
        s.set(1, "done");
      } catch (e) {
        setError((e as Error).message);
        s.set(0, "error");
      } finally {
        setBusy(false);
      }
    }

    useImperativeHandle(ref, () => ({ run }));
    const sum = result?.summary;

    return (
      <PanelShell id="phrase" title="1 · Start with a phrase" subtitle="An action sentence (+ context) → what that action changes, ring by ring">
        <HowItWorks inputs={["phrase"]} page="demo" />
        <div className="grid gap-4 lg:grid-cols-[minmax(300px,420px)_1fr]">
          <div className="flex flex-col gap-2.5">
            <label className="flex flex-col gap-1">
              <span className="eyebrow">Example action</span>
              <select className={inputClass} value={index} onChange={(e) => choose(Number(e.target.value))}>
                {examples.map((p, i) => (
                  <option key={p.id} value={i}>
                    {p.text}
                  </option>
                ))}
              </select>
              <span className="faint text-[10.5px]">Shows: {example.shows}</span>
            </label>
            <label className="flex flex-col gap-1">
              <span className="eyebrow">Context (earlier sentences: other people&apos;s goals)</span>
              <textarea className={`${inputClass} min-h-12`} value={context} onChange={(e) => { setContext(e.target.value); setResult(null); s.clear(); }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="eyebrow">Action sentence</span>
              <textarea className={`${inputClass} min-h-14 text-[13px]`} value={text} onChange={(e) => { setText(e.target.value); setResult(null); s.clear(); }} />
            </label>
            {edited && !live && (
              <p className="text-[11px] text-warn-400">Edited text needs Live mode (MLM parser). {liveReason}</p>
            )}
            <div className="flex flex-wrap gap-2">
              <button type="button" className={buttonClass} onClick={run} disabled={busy || running || (edited && !live)}>
                {busy ? "Running…" : "Run phrase"}
              </button>
              <button type="button" className={buttonGhostClass} onClick={() => choose(index)}>
                Reset
              </button>
            </div>
            <Steps steps={s.steps} />
            {error && <ErrorBox error={error} />}
          </div>

          <div className="flex flex-col gap-3">
            {!result ? (
              <p className="faint grid min-h-40 place-items-center text-center text-xs">Run to see what this action changes, ring by ring.</p>
            ) : (
              <>
                <MeaningLine
                  items={[
                    ["WHO", sum?.self_view ? "self (I)" : sum?.actor, "observed"],
                    ["DOES", sum?.predicate ? `${sum.predicate}${sum.concept ? ` → ${sum.concept}` : " (no concept)"}` : null, "observed"],
                    ["WHERE", sum?.places.join(", ") || null, "observed"],
                    ["WHEN", sum?.tense, "observed"],
                    ["CERTAINTY", sum ? sum.certainty.toFixed(2) : null, "inferred"],
                  ]}
                />
                {sum && !sum.realized && <p className="text-xs text-warn-400">The action is negated: none of its consequences follow.</p>}
                <BlastRadius rings={result.rings} caption="Ownership, payment and layer impacts are rule-derived (ARM packs). Certainty is a rule weight, not a probability." />
                {sum && sum.notes.length > 0 && (
                  <ul className="faint flex flex-col gap-0.5 text-[11px]">
                    {sum.notes.map((n) => <li key={n}>• {n}</li>)}
                  </ul>
                )}
                <details className="panel-raised px-3 py-2 text-xs">
                  <summary className="cursor-pointer font-medium">ARM text report</summary>
                  <pre className="num mt-2 max-h-80 overflow-auto text-[11px] leading-relaxed">{result.report_text}</pre>
                </details>
              </>
            )}
          </div>
        </div>
        {result && <PhraseChat result={result} live={live} liveReason={liveReason} />}
      </PanelShell>
    );
  },
);

// -- image -------------------------------------------------------------------------------------

function ScenarioResultView({ scenario, flowScene, label }: { scenario: Scenario; flowScene: DemoBundle["flows"]["image"]["scene"]; label: string }) {
  const result = useMemo(() => simulate(toSimScene(flowScene), toSimAction(scenario)), [flowScene, scenario]);
  const outcome = result.events.filter((e) => e.kind !== "remains_supported");
  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 md:grid-cols-2">
        <TabletopScene entities={flowScene.entities} table={[0, 0, 1.2, 0.8]} title="Now" tag={{ text: label, tone: "observed" }} result={null} />
        <TabletopScene entities={flowScene.entities} table={[0, 0, 1.2, 0.8]} title={`If: ${scenario.label}`} tag={{ text: "Illustrative simulation", tone: "predicted" }} result={result} />
      </div>
      <p className="text-xs">
        <b>Predicted:</b>{" "}
        {outcome.length ? outcome.map((e) => `${e.kind.replace("_", " ")} (${e.entity_id})`).join(" · ") : "every object stays where it is supported"}
      </p>
      {scenario.rings ? (
        <BlastRadius rings={scenario.rings} caption="Simulated rows come from the constrained tabletop simulator; damage and spill stay unknown." />
      ) : (
        <p className="faint text-xs">No action: no rule applies and the simulator predicts no change — nothing to evaluate.</p>
      )}
    </div>
  );
}

export const ImagePanel = forwardRef<PanelHandle, { demo: DemoBundle; running: boolean }>(function ImagePanel({ demo, running }, ref) {
  const flow = demo.flows.image;
  const [action, setAction] = useState<ActionKey>("push_edge");
  const [shown, setShown] = useState<ActionKey | null>(null);
  const [busy, setBusy] = useState(false);
  const s = useSteps(["MLM reads the scene", "Simulate the action", "ARM predicts the consequences", "Physics lab: detect + simulate"]);
  const lab = useRef<LabHandle>(null);

  async function run() {
    if (busy) return;
    setBusy(true);
    setShown(null);
    s.start();
    for (let i = 0; i < 3; i++) {
      s.set(i, "running");
      await wait(450);
      s.set(i, "done");
      if (i === 0) setShown("none"); // reveal the meaning first
    }
    setShown(action);
    s.set(3, "running");
    await lab.current?.run();
    s.set(3, "done");
    setBusy(false);
  }
  useImperativeHandle(ref, () => ({ run }));
  const relations = flow.scene.relations;

  return (
    <PanelShell id="image" title="2 · An image" subtitle="A picture of a scene + a proposed action → the consequences of that action">
      <HowItWorks inputs={["image"]} page="demo" />
      <div className="grid gap-4 lg:grid-cols-[minmax(300px,420px)_1fr]">
        <div className="flex flex-col gap-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/demo/tabletop_scene.svg" alt="Tabletop scene: blue cup near the right edge, red cup near the center" className="panel-raised w-full" />
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Proposed action (not read from the image)</span>
            <select className={inputClass} value={action} onChange={(e) => { setAction(e.target.value as ActionKey); setShown(null); s.clear(); }}>
              {ACTION_KEYS.map((k) => <option key={k} value={k}>{demo.action_labels[k]}</option>)}
            </select>
          </label>
          <div className="flex gap-2">
            <button type="button" className={buttonClass} onClick={run} disabled={busy || running}>
              {busy ? "Running…" : "Run image"}
            </button>
          </div>
          <Steps steps={s.steps} />
          <Caveat>Extraction replayed from a fixture (demo mode), not live model detection.</Caveat>
        </div>
        <div className="flex flex-col gap-3">
          {shown === null ? (
            <p className="faint grid min-h-40 place-items-center text-center text-xs">Run to see what the image shows and what the action would do.</p>
          ) : (
            <>
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">What MLM reads from the image</span>
                <div className="flex flex-wrap gap-1.5">
                  {relations.map((r, i) => (
                    <span key={i} className="panel-raised flex items-center gap-1.5 px-2 py-1 text-[11.5px]">
                      <StatusTag status={r.status} /> {r.subject} {r.relation} {r.object}
                      {r.value ? ` (${String(r.value)})` : ""}
                    </span>
                  ))}
                </div>
                <span className="faint text-[11px]">
                  Not supported by a still image (rejected): {flow.meaning.rejected_claims?.map((c) => `“${c.claim}”`).join(", ")}
                </span>
              </div>
              {shown !== "none" && <ScenarioResultView scenario={flow.scenarios[shown]} flowScene={flow.scene} label="Observed (fixture replay)" />}
            </>
          )}
        </div>
      </div>
      <PhysicsLab ref={lab} scene={flow.scene} mode="image" defaultTarget="blue_cup_01" actor="you (proposed action)" />
    </PanelShell>
  );
});

// -- video -------------------------------------------------------------------------------------

export const VideoPanel = forwardRef<PanelHandle, { demo: DemoBundle; checkpoint: number; running: boolean }>(function VideoPanel(
  { demo, checkpoint: T, running },
  ref,
) {
  const flow = demo.flows.video;
  const video = useRef<HTMLVideoElement>(null);
  const [phase, setPhase] = useState<"idle" | "watching" | "predicted" | "revealed">("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const s = useSteps([`Watch until T = ${T}s`, "MLM reads the scene at T", "Simulate + ARM consequences", "Reveal what happened next", "Physics lab: detect + simulate"]);
  const lab = useRef<LabHandle>(null);

  function playUntil(limit: number | null): Promise<void> {
    const el = video.current;
    if (!el) return Promise.reject(new Error("video not ready"));
    return new Promise((resolve, reject) => {
      const onTime = () => {
        if (limit !== null && el.currentTime >= limit) {
          el.pause();
          el.currentTime = limit;
          done();
        }
      };
      const onEnded = () => done();
      const done = () => {
        el.removeEventListener("timeupdate", onTime);
        el.removeEventListener("ended", onEnded);
        resolve();
      };
      el.addEventListener("timeupdate", onTime);
      el.addEventListener("ended", onEnded);
      el.play().catch((e) => reject(e));
    });
  }

  async function run() {
    if (busy) return;
    setBusy(true);
    setError(null);
    setPhase("idle");
    s.start();
    try {
      const el = video.current!;
      el.currentTime = 0;
      s.set(0, "running");
      setPhase("watching");
      await playUntil(T); // frames after T are never used for the prediction
      s.set(0, "done");
      s.set(1, "running");
      await wait(400);
      s.set(1, "done");
      s.set(2, "running");
      await wait(400);
      setPhase("predicted");
      s.set(2, "done");
      await wait(1600);
      s.set(3, "running");
      await playUntil(null);
      setPhase("revealed");
      s.set(3, "done");
      s.set(4, "running");
      await lab.current?.run();
      s.set(4, "done");
    } catch (e) {
      setError(`Playback failed: ${(e as Error).message}. Press Run video again.`);
    } finally {
      setBusy(false);
    }
  }
  useImperativeHandle(ref, () => ({ run }));
  const scenario = flow.scenarios.push_edge;
  const m = flow.comparison.metrics;

  return (
    <PanelShell id="video" title="3 · A video" subtitle="A clip of events → predict at T, then compare with what happened">
      <HowItWorks inputs={["video"]} page="demo" />
      <div className="grid gap-4 lg:grid-cols-[minmax(300px,420px)_1fr]">
        <div className="flex flex-col gap-2.5">
          <div className="panel-raised overflow-hidden">
            <video ref={video} playsInline muted preload="auto" className="block w-full" aria-label="Synthetic video: a pusher pushes the blue cup off the table">
              <source src="/demo/tabletop_push_synthetic.webm" type="video/webm" />
              <source src="/demo/tabletop_push_synthetic.mp4" type="video/mp4" />
            </video>
          </div>
          <div className="flex gap-2">
            <button type="button" className={buttonClass} onClick={run} disabled={busy || running}>
              {busy ? "Running…" : "Run video"}
            </button>
          </div>
          <Steps steps={s.steps} />
          {error && <ErrorBox error={error} />}
          <Caveat>Synthetic demonstration — scripted motion. Events replayed from a fixture, not live tracking.</Caveat>
        </div>
        <div className="flex flex-col gap-3">
          {phase === "idle" || phase === "watching" ? (
            <p className="faint grid min-h-40 place-items-center text-center text-xs">
              {phase === "watching" ? `Watching… the prediction will use frames up to ${T}s only.` : "Run to predict from the video, then see what actually happened."}
            </p>
          ) : (
            <>
              <MeaningLine
                items={[
                  ["WHO", "pusher_01", "observed"],
                  ["TOUCHING", "blue_cup_01", "inferred"],
                  ["WHERE", "table_01, near right edge", "observed"],
                  ["WHEN", `T = ${T}s`, "observed"],
                  ["WHY", null, "unknown"],
                ]}
              />
              <span className="eyebrow">Prediction at T (proposed action: push 0.20 m toward the edge)</span>
              <ScenarioResultView scenario={scenario} flowScene={flow.scene} label={`Observed at T=${T}s`} />
              {phase === "revealed" && (
                <div className="panel-raised flex flex-col gap-2 p-3">
                  <span className="eyebrow">What happened next (scripted outcome)</span>
                  <ol className="flex flex-col gap-0.5 text-[12px]">
                    {flow.timeline.map((ev) => (
                      <li key={ev.id}>
                        <span className="num">{ev.start_s.toFixed(1)}–{ev.end_s.toFixed(1)}s</span> <b>{ev.predicate}</b>{" "}
                        {Object.entries(ev.roles).map(([r, v]) => `${r}=${v.join(",")}`).join(" ")} · cause {ev.causal_attribution}
                      </li>
                    ))}
                  </ol>
                  <p className="text-[12px]">
                    <b>Prediction vs outcome:</b> fall predicted and observed (precision {m.fall_events.precision}, recall {m.fall_events.recall}) ·
                    support state {m.support_state_accuracy * 100}% · red cup position error {m.position_error_m.mean} m · landing position: abstained.
                  </p>
                  <p className="text-[11px] text-warn-400">{flow.scripted_outcome.label}. This shows the workflow, not real-world accuracy.</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
      <PhysicsLab ref={lab} scene={flow.scene} mode="video" defaultTarget="blue_cup_01" actor="pusher_01" />
    </PanelShell>
  );
});
