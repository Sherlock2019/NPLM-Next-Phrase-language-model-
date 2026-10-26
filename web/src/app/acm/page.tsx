"use client";

/**
 * ACM demo: a phrase, an image and a video, each predicting the consequences of
 * an action, as the tool is meant to be used. One "Run Demo" runs all three.
 */

import { useEffect, useRef, useState } from "react";
import { buttonClass, ErrorBox, Loading } from "@/components/ui";
import { ImagePanel, PhrasePanel, VideoPanel, type PanelHandle } from "@/components/acm/Panels";
import type { DemoBundle, LiveStatus, VideoScript } from "@/lib/multimodal/types";

const STAGES = ["phrase", "image", "video"] as const;

export default function AcmDemoPage() {
  const [demo, setDemo] = useState<DemoBundle | null>(null);
  const [script, setScript] = useState<VideoScript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [running, setRunning] = useState<(typeof STAGES)[number] | "done" | null>(null);
  const panels = {
    phrase: useRef<PanelHandle>(null),
    image: useRef<PanelHandle>(null),
    video: useRef<PanelHandle>(null),
  };

  useEffect(() => {
    Promise.all([
      fetch("/demo/demo_results.json").then((r) => (r.ok ? r.json() : Promise.reject(new Error(`demo_results.json ${r.status}`)))),
      fetch("/demo/tabletop_video_script.json").then((r) => (r.ok ? r.json() : Promise.reject(new Error(`video script ${r.status}`)))),
    ])
      .then(([d, s]) => {
        setDemo(d);
        setScript(s);
      })
      .catch((e: Error) => setError(`Bundled demo material could not be loaded: ${e.message}`));
    fetch("/api/multimodal/status")
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => setStatus(s))
      .catch(() => setStatus(null));
  }, []);

  async function runAll() {
    if (running && running !== "done") return;
    for (const key of STAGES) {
      setRunning(key);
      document.getElementById(key)?.scrollIntoView({ behavior: "smooth", block: "start" });
      await panels[key].current?.run();
    }
    setRunning("done");
  }

  const live = Boolean(status?.live.text);
  const busy = running !== null && running !== "done";

  return (
    <div className="flex flex-col gap-5">
      <div className="sticky top-[60px] z-30 flex flex-wrap items-center gap-2 rounded-lg bg-fuchsia-700 px-3 py-2 text-xs font-semibold text-white shadow" role="status">
        <span>Demo mode — example extraction and simulated consequences</span>
        <span className="ml-auto font-normal opacity-90">
          {live ? "Phrase: your own sentences run live (MLM parser + ACM)" : "Image/video extractions are replayed fixtures, not live model inference."}
        </span>
      </div>

      <header className="panel flex flex-col gap-4 p-5 sm:p-6">
        <div className="flex flex-wrap items-start gap-4">
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-semibold tracking-tight">Actions Consequential Model (ACM)</h1>
            <p className="mt-1 text-[15px] font-semibold text-splm-300">See what an action changes before taking it.</p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <button type="button" className={`${buttonClass} px-5 py-2.5 text-sm`} onClick={runAll} disabled={!demo || busy}>
              {busy ? `Running ${running}…` : "▶ Run Demo"}
            </button>
            <span className="faint text-[10.5px]">runs a phrase, then an image, then a video</span>
          </div>
        </div>
        <blockquote className="border-l-2 border-splm-500/60 pl-4 text-[13.5px] leading-relaxed">
          A language model predicts the next word. MLM first works out what a sentence means.{" "}
          <b>
            ACM goes one step further: it predicts what an action <i>does</i>. It traces the consequences for the one acting,
            for those it lands on, for other actors&apos; goals, and then across its whole blast radius, layer by layer: the place
            it happens, its neighbours, the organization it belongs to, its city, its country, society, and the earth.
          </b>
        </blockquote>
        <p className="dim max-w-4xl text-[13px] leading-relaxed">
          ACM is built on the Meaning Language Model (MLM), which turns a phrase into Universal Phrase DNA: who does what, to
          whom, where, when, how and why. ACM turns that structure into a graph of the full action in its context and predicts
          the consequences circle by circle (who is affected) and across the blast radius, layer by layer (where the effects
          reach). When the actor is <b>&quot;I&quot;</b>, the report is the model&apos;s view of its <b>own</b> planned action. The same
          works from an <b>image</b> plus a proposed action, and from a <b>video</b>.
        </p>
        <p className="faint text-[11.5px]">
          who: <b>Self / Actor</b> → <b>Impacted</b> → <b>Other actors</b> · where: <b>Local</b> → <b>Neighbours</b> →{" "}
          <b>Organization</b> → <b>City</b> → <b>Country</b> → <b>Society</b> → <b>Earth</b>
        </p>
      </header>

      {demo && (
        <ol className="flex flex-wrap gap-2 text-[11.5px]" aria-label="Demo progress">
          {STAGES.map((key, i) => {
            const state = running === "done" || (running && STAGES.indexOf(running as never) > i) ? "done" : running === key ? "running" : "waiting";
            return (
              <li key={key}>
                <a href={`#${key}`} className={`panel-raised inline-flex items-center gap-1.5 px-2.5 py-1 ${state === "running" ? "ring-2 ring-splm-500/60" : ""}`}>
                  <span aria-hidden>{state === "done" ? "●" : state === "running" ? "◌" : "○"}</span>
                  {i + 1}. {key} <span className="faint">({state})</span>
                </a>
              </li>
            );
          })}
        </ol>
      )}

      {error && <ErrorBox error={error} />}
      {!demo || !script ? (
        !error && <Loading label="Loading the demo" />
      ) : (
        <div className="flex flex-col gap-5">
          <PhrasePanel ref={panels.phrase} demo={demo} live={live} liveReason={status?.reasons.text ?? "the MLM API is not reachable"} running={busy} autoShow />
          <ImagePanel ref={panels.image} demo={demo} running={busy} />
          <VideoPanel ref={panels.video} demo={demo} checkpoint={script.checkpoint_s} running={busy} />
        </div>
      )}

      <p className="faint text-[11px] leading-relaxed">
        How to read it: <b>rule-derived</b> rows come from ACM&apos;s knowledge packs, <b>simulated</b> rows from a constrained tabletop
        simulator, <b>unknown</b> rows say what ACM cannot know and what it would need. “No supporting evidence” means no rule
        matched — never “no impact”. Certainty values are rule weights, not calibrated probabilities. The full step-by-step view is on
        the <a className="underline" href="/multimodal">Multimodal</a> page.
      </p>
    </div>
  );
}
