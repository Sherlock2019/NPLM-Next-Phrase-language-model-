"use client";

/**
 * The ARM tour: how ARM works, how it differs from a language model, and how it
 * stays one meaning across text, image and video. Every number and answer on this
 * page comes from bundled, real outputs:
 *   inference_suite.json  ARM on parses by MLM's real parser
 *   llm_vs_acm.json       a real local language model asked the same questions
 *   demo_results.json     the multimodal pipeline (fixture-replayed extraction)
 */

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { buttonClass, buttonGhostClass, ErrorBox, Loading } from "@/components/ui";
import { RingDiagram } from "@/components/acm/BlastRadius";
import { ReasoningChain } from "@/components/acm/Inference";
import { Intro } from "@/components/acm/Intro";
import { StatusTag } from "@/components/multimodal/Stages";
import type { DemoBundle, InferenceSuite, LlmVsAcm } from "@/lib/multimodal/types";

function Chapter({ n, title, lead, children, id }: { n: number; title: string; lead: string; children: React.ReactNode; id: string }) {
  return (
    <section id={id} className="panel scroll-mt-24 p-5 sm:p-6">
      <div className="mb-4 flex items-baseline gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-splm-500 text-sm font-bold text-ink-950">{n}</span>
        <div>
          <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
          <p className="dim mt-0.5 max-w-3xl text-[13px] leading-relaxed">{lead}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

// -- 1. how ARM thinks ---------------------------------------------------------------

function HowItThinks({ suite }: { suite: InferenceSuite }) {
  const item = suite.items.find((i) => i.action === "John sold his car to Sarah.") ?? suite.items[0];
  const [step, setStep] = useState(-1);
  const timers = useRef<number[]>([]);
  const play = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setStep(-1);
    for (let s = 0; s <= 8; s++) timers.current.push(window.setTimeout(() => setStep(s), 650 * s + 200));
  };
  useEffect(() => () => timers.current.forEach(clearTimeout), []);
  const highlights = item.answers.filter((a) => ["impacted", "goal", "layer"].includes(a.kind)).slice(0, 5);

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <div className="flex flex-col gap-3">
        <div className="panel-raised p-4">
          <p className="dim text-[12px]">Context: {item.context.map((c) => `“${c}”`).join(" ")}</p>
          <p className="mt-1 text-[20px] font-semibold">“{item.action}”</p>
        </div>
        <div className="flex gap-2">
          <button type="button" className={buttonClass} onClick={play}>▶ Watch ARM think</button>
          <button type="button" className={buttonGhostClass} onClick={() => setStep((s) => Math.min(s + 1, 8))}>next step</button>
          <button type="button" className={buttonGhostClass} onClick={() => setStep(8)}>show all</button>
        </div>
        <ReasoningChain item={item} active={step} />
      </div>
      <div className={`flex flex-col gap-3 transition-opacity ${step >= 8 ? "opacity-100" : "opacity-30"}`} aria-live="polite">
        <span className="eyebrow">…so ARM answers</span>
        <ul className="flex flex-col gap-2">
          {highlights.map((a) => (
            <li key={a.question} className="panel-raised px-3 py-2">
              <div className="text-[12.5px] font-medium">{a.question}</div>
              <div className="mt-0.5 text-[14px]">{a.answer}</div>
              <div className="num faint mt-0.5 text-[10.5px]">↳ {a.why[0]}</div>
            </li>
          ))}
        </ul>
        <div className="max-w-[260px] self-center">
          <RingDiagram rings={item.rings} />
        </div>
      </div>
    </div>
  );
}

// -- 2. ARM vs a language model -----------------------------------------------------------

function VsLlm({ data, suite }: { data: LlmVsAcm; suite: InferenceSuite }) {
  const [index, setIndex] = useState(0);
  const pair = data.pairs[index];
  const unstable = data.pairs.filter((p) => p.llm_distinct_answers > 1).length;
  const negated = data.pairs.find((p) => p.action.includes("did not"));
  const limits = suite.items.filter((i) => i.answers.some((a) => a.kind === "limits")).length;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Questions">
        {data.pairs.map((p, i) => (
          <button key={`${p.action}-${p.subject}`} type="button" role="tab" aria-selected={i === index} onClick={() => setIndex(i)}
            className={`rounded-md px-2.5 py-1 text-[11.5px] ${i === index ? "bg-splm-500/20 text-splm-300 ring-1 ring-splm-500/40" : "panel-raised dim hover:text-[var(--text)]"}`}>
            {p.action.replace(/\.$/, "")} → {p.subject}
          </button>
        ))}
      </div>

      <div className="panel-raised px-4 py-3">
        {pair.context.length > 0 && <p className="dim text-[12px]">Context: {pair.context.map((c) => `“${c}”`).join(" ")}</p>}
        <p className="text-[16px] font-semibold">“{pair.action}” — what happens next to {pair.subject}?</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="panel-raised flex flex-col gap-2 p-4">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold">A language model</span>
            <span className="faint text-[11px]">{data.model} · {data.kind}</span>
          </div>
          <div>
            <span className="eyebrow">most likely answer (greedy)</span>
            <p className="mt-0.5 text-[15px]">“{pair.greedy}”</p>
          </div>
          <div>
            <span className="eyebrow">asked again three times (sampling)</span>
            <ul className="mt-0.5 flex flex-col gap-0.5 text-[13px]">
              {pair.samples.map((s, i) => <li key={i} className="dim">• “{s}”</li>)}
            </ul>
          </div>
          <p className="faint text-[11px]">
            {pair.llm_distinct_answers} different answer{pair.llm_distinct_answers === 1 ? "" : "s"} in 4 runs · no reason given · recorded
            {" "}{data.recorded}, prompt shown below.
          </p>
          <details className="text-[11px]">
            <summary className="faint cursor-pointer">exact prompt</summary>
            <pre className="num mt-1 whitespace-pre-wrap">{pair.prompt}</pre>
          </details>
        </div>

        <div className="panel-raised flex flex-col gap-2 p-4 ring-1 ring-splm-500/30">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold text-splm-300">ARM</span>
            <span className="faint text-[11px]">rules over MLM&apos;s meaning · deterministic</span>
          </div>
          <div>
            <span className="eyebrow">{pair.acm.question}</span>
            <p className="mt-0.5 text-[15px] font-medium">{pair.acm.answer}</p>
          </div>
          <div>
            <span className="eyebrow">why</span>
            <ul className="mt-0.5 flex flex-col gap-0.5">
              {pair.acm.why.map((w, i) => <li key={i} className="num dim text-[11.5px]">↳ {w}</li>)}
            </ul>
          </div>
          <p className="faint text-[11px]">Same answer on every run · every claim traceable to a rule, a role or a goal comparison.</p>
          <Link href={`/acm/inference`} className="text-[11px] underline">see all {suite.stats.questions} ARM answers →</Link>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-[12.5px]">
          <thead>
            <tr className="hairline border-b">
              <th className="eyebrow py-2 pr-3">What you can check</th>
              <th className="eyebrow py-2 pr-3">This language model</th>
              <th className="eyebrow py-2">ARM</th>
            </tr>
          </thead>
          <tbody className="align-top">
            <tr className="hairline border-b"><td className="py-2 pr-3 font-medium">Why this answer?</td><td className="dim py-2 pr-3">No reason — text continuation</td><td className="py-2">Rule, role and evidence for every sentence</td></tr>
            <tr className="hairline border-b"><td className="py-2 pr-3 font-medium">Same question twice</td><td className="dim py-2 pr-3">{unstable} of {data.pairs.length} questions got different answers across 4 runs</td><td className="py-2">Identical every time</td></tr>
            {negated && (
              <tr className="hairline border-b"><td className="py-2 pr-3 font-medium">“{negated.action}”</td><td className="dim py-2 pr-3">“{negated.greedy}”</td><td className="py-2">{negated.acm.answer}</td></tr>
            )}
            <tr className="hairline border-b"><td className="py-2 pr-3 font-medium">Other people&apos;s plans</td><td className="dim py-2 pr-3">Not tracked</td><td className="py-2">{Object.entries(suite.stats.relations).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(" · ")} across the suite</td></tr>
            <tr className="hairline border-b"><td className="py-2 pr-3 font-medium">What it can&apos;t know</td><td className="dim py-2 pr-3">Not stated</td><td className="py-2">Stated for {limits} of {suite.stats.scenarios} actions (“no rule ≠ no impact”)</td></tr>
            <tr className="hairline border-b"><td className="py-2 pr-3 font-medium">Input</td><td className="dim py-2 pr-3">Text only (this model)</td><td className="py-2">Text, image and video, into one meaning (chapter 3)</td></tr>
            <tr><td className="py-2 pr-3 font-medium">Checked against reality</td><td className="dim py-2 pr-3">—</td><td className="py-2">Prediction vs outcome, scored (chapter 4)</td></tr>
          </tbody>
        </table>
      </div>

      <div className="rounded-lg border border-warn-400/30 bg-warn-400/8 p-4 text-[12.5px] leading-relaxed">
        <b className="text-warn-400">Where a language model is better — honestly.</b> This is a small base model ({data.model});
        large chat models answer these questions far more sensibly. Any LLM knows about far more of the world than ARM&apos;s 18 concepts
        and seed rules, writes fluently, and copes with verbs ARM has never seen (ARM then says “no verdict”). ARM is not a
        replacement for an LLM: it is the part that turns meaning into <b>checkable consequences</b> — explicit, repeatable, and honest
        about what it doesn&apos;t know. The natural design is both: the LLM talks, ARM checks what an action does.
      </div>
    </div>
  );
}

// -- 3. one meaning, three senses ---------------------------------------------------------------

function ThreeSenses({ demo }: { demo: DemoBundle }) {
  const flows = [
    { key: "text", title: "Text", evidence: "states a plan", flow: demo.flows.text },
    { key: "image", title: "Image", evidence: "shows a scene", flow: demo.flows.image },
    { key: "video", title: "Video", evidence: "shows events", flow: demo.flows.video },
  ] as const;
  const outcome = (k: (typeof flows)[number]) =>
    k.flow.scenarios.push_edge.events.filter((e) => e.kind !== "remains_supported").map((e) => `${e.kind.replace("_", " ")}: ${e.entity_id}`);
  const same = new Set(flows.map((f) => outcome(f).join("|"))).size === 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 md:grid-cols-3">
        {flows.map((f) => {
          const m = f.flow.meaning;
          return (
            <div key={f.key} className="panel-raised flex flex-col gap-2.5 p-4">
              <div className="flex items-baseline gap-2">
                <span className="text-[15px] font-semibold">{f.title}</span>
                <span className="faint text-[11.5px]">{f.evidence}</span>
              </div>
              <div className="grid h-36 place-items-center overflow-hidden rounded-md bg-[var(--page)]">
                {f.key === "text" && <p className="px-3 text-center text-[12.5px] italic">“{String(f.flow.input.text)}”</p>}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {f.key === "image" && <img src="/demo/tabletop_scene.svg" alt="Tabletop scene" className="h-full w-full object-contain" />}
                {f.key === "video" && (
                  <video src="/demo/tabletop_push_synthetic.mp4" muted loop autoPlay playsInline className="h-full w-full object-contain" aria-label="Synthetic push video" />
                )}
              </div>
              <span className="eyebrow">MLM meaning</span>
              <ul className="flex flex-col gap-1 text-[12px]">
                {(["who", "action", "what", "why"] as const).map((k) => {
                  const field = m[k];
                  return field ? (
                    <li key={k} className="flex items-center gap-1.5">
                      <span className="faint w-14 uppercase">{k}</span>
                      <span className="flex-1">{field.value ?? "unknown"}</span>
                      <StatusTag status={field.status} />
                    </li>
                  ) : null;
                })}
              </ul>
              <span className="eyebrow">ARM predicts (push toward the edge)</span>
              <ul className="text-[12.5px]">{outcome(f).map((o) => <li key={o}>• {o} <span className="faint">(simulated)</span></li>)}</ul>
              <span className="faint text-[11px]">damage and spill: unknown · society and earth: no supporting evidence</span>
            </div>
          );
        })}
      </div>
      <div className={`rounded-lg p-3 text-[13px] ${same ? "bg-ok-400/10 text-ok-400" : "bg-warn-400/10 text-warn-400"}`}>
        {same
          ? "Same meaning, same consequence: from the sentence, the picture and the clip, ARM reaches the same prediction — blue_cup_01 crosses the edge and falls."
          : "The three inputs lead to different predictions here."}{" "}
        <span className="dim">What differs is kept: the text <i>states</i> a plan (positions assumed), the image <i>shows</i> a scene (it cannot show a push),
        the video <i>shows</i> events (it cannot show why). A text-only LLM sees none of the picture or the clip.</span>
      </div>
    </div>
  );
}

// -- 4. reality check -----------------------------------------------------------------------------

function RealityCheck({ demo }: { demo: DemoBundle }) {
  const m = demo.flows.video.comparison.metrics;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-4">
        {[
          ["Predicted at", "T = 2.0 s, before the push"],
          ["Fall predicted", `precision ${m.fall_events.precision} · recall ${m.fall_events.recall}`],
          ["Support state", `${m.support_state_accuracy * 100}% matched`],
          ["Landing position", "abstained (unknown)"],
        ].map(([k, v]) => (
          <div key={k} className="panel-raised px-3 py-2.5">
            <div className="eyebrow">{k}</div>
            <div className="mt-1 text-[14px] font-semibold">{v}</div>
          </div>
        ))}
      </div>
      <p className="dim text-[12.5px]">
        ARM&apos;s prediction is a set of explicit state changes, so it can be <b>scored</b> against what happens next — frames after T are
        used only for checking, never as input. Here the outcome is a scripted animation, so this shows the workflow, not real-world
        accuracy.
      </p>
      <div className="flex flex-wrap gap-2">
        <Link href="/acm" className={buttonClass}>▶ Run the demo (phrase · image · video)</Link>
        <Link href="/acm/inference" className={buttonGhostClass}>Explore 53 actions</Link>
        <Link href="/multimodal" className={buttonGhostClass}>Step-by-step multimodal view</Link>
      </div>
    </div>
  );
}

export default function TourPage() {
  const [suite, setSuite] = useState<InferenceSuite | null>(null);
  const [llm, setLlm] = useState<LlmVsAcm | null>(null);
  const [demo, setDemo] = useState<DemoBundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const get = (f: string) => fetch(`/demo/${f}`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${f} ${r.status}`))));
    Promise.all([get("inference_suite.json"), get("llm_vs_acm.json"), get("demo_results.json")])
      .then(([s, l, d]) => { setSuite(s); setLlm(l); setDemo(d); })
      .catch((e: Error) => setError(`Tour material could not be loaded: ${e.message}. Run ARM's ./start.sh.`));
  }, []);

  const ready = useMemo(() => suite && llm && demo, [suite, llm, demo]);
  if (error) return <ErrorBox error={error} />;
  if (!ready) return <Loading label="Loading the tour" />;

  return (
    <div className="flex flex-col gap-5">
      <Intro page="tour" />
      <header className="panel flex flex-col gap-3 p-6">
        <h1 className="text-3xl font-semibold tracking-tight">See what an action changes — before taking it.</h1>
        <p className="dim max-w-4xl text-[14px] leading-relaxed">
          A language model predicts the next word. <b>ARM predicts what an action does</b>: for the one acting, for those it lands on, for
          other people&apos;s plans, and outward to the place, the city, the country, society and the earth — from a sentence, a picture or a
          video, with a reason for every claim.
        </p>
        <nav className="flex flex-wrap gap-2 text-[12px]" aria-label="Chapters">
          {[["how", "1 · How ARM thinks"], ["llm", "2 · ARM vs a language model"], ["senses", "3 · One meaning, three senses"], ["reality", "4 · Checked against reality"]].map(([id, label]) => (
            <a key={id} href={`#${id}`} className="panel-raised px-3 py-1.5 hover:text-splm-300">{label}</a>
          ))}
        </nav>
      </header>

      <Chapter id="how" n={1} title="How ARM thinks" lead="One sentence, eight explicit steps: MLM reads who does what to whom; ARM binds it to a concept, works out the state changes, places each one, checks other people's goals, applies its layer rules — and only then answers.">
        <HowItThinks suite={suite!} />
      </Chapter>

      <Chapter id="llm" n={2} title="ARM vs a language model" lead="The same questions, asked to a real language model running locally and to ARM. Read the answers yourself; the table only counts what is on screen.">
        <VsLlm data={llm!} suite={suite!} />
      </Chapter>

      <Chapter id="senses" n={3} title="One meaning, three senses" lead="A sentence, a picture and a video of the same tabletop. MLM turns each into the same kind of meaning; ARM predicts from that meaning — not from a vision model's prose.">
        <ThreeSenses demo={demo!} />
      </Chapter>

      <Chapter id="reality" n={4} title="Checked against reality" lead="A prediction you can score: made from the video up to T, compared with what happened after.">
        <RealityCheck demo={demo!} />
      </Chapter>
    </div>
  );
}
