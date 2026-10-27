"use client";

/**
 * "How it works" for each kind of input (phrase, image, video): the pipeline step by
 * step, what runs at each step, and whether it is real, rule-based, simulated, an LLM,
 * a mock or a replayed fixture. Steps a page does not run are dimmed with where they run.
 */

import { useState } from "react";

export type InputKind = "phrase" | "image" | "video";
export type PageKind = "demo" | "inference" | "multimodal";

type Badge = "real" | "rules" | "sim" | "llm" | "mock" | "fixture" | "assumed" | "input";

const BADGE: Record<Badge, { word: string; tone: string; means: string }> = {
  input: { word: "input", tone: "bg-white/8 text-[var(--text-dim)] ring-white/15", means: "what you give it" },
  real: { word: "real", tone: "bg-ok-400/12 text-ok-400 ring-ok-400/30", means: "runs live on your input" },
  rules: { word: "rules", tone: "bg-splm-500/15 text-splm-300 ring-splm-500/30", means: "ACM's knowledge packs: deterministic, every row has a reason" },
  sim: { word: "simulated", tone: "bg-fuchsia-500/12 text-fuchsia-400 ring-fuchsia-500/30", means: "computed by a physics simulator" },
  llm: { word: "LLM", tone: "bg-sky-500/15 text-sky-300 ring-sky-500/30", means: "local qwen2.5:7b — words answers and reads questions, never decides consequences" },
  mock: { word: "mock", tone: "bg-warn-400/12 text-warn-400 ring-warn-400/30", means: "a stand-in for a model that is not wired in yet" },
  fixture: { word: "fixture", tone: "bg-warn-400/12 text-warn-400 ring-warn-400/30", means: "a hand-authored extraction replayed, labelled as such" },
  assumed: { word: "assumed", tone: "bg-warn-400/12 text-warn-400 ring-warn-400/30", means: "a typical value for the object class, not measured" },
};

interface Step {
  title: string;
  badges: Badge[];
  engine: string;
  does: string;
  example: string;
  pages: PageKind[];
}

const ALL: PageKind[] = ["demo", "inference", "multimodal"];

const STEPS: Record<InputKind, { lead: string; steps: Step[] }> = {
  phrase: {
    lead: "A sentence (plus earlier sentences as context) → what it means → what the action changes, ring by ring → answers to your questions.",
    steps: [
      { title: "Phrase + context", badges: ["input"], engine: "you", pages: ALL,
        does: "An action sentence. Earlier sentences tell ACM what other people want or did.",
        example: "context “Mark wants to buy my car.” · action “I will sell my car to Sarah to pay my debt.”" },
      { title: "MLM reads the meaning", badges: ["real"], engine: "Stanza parser + MLM frame builder (no LLM)", pages: ALL,
        does: "Turns the sentence into Universal Phrase DNA: who does what, to whom, where, when, how and why, plus tense and negation.",
        example: "WHO=I · DOES=sell · WHAT=my car · TO WHOM=Sarah · WHY=to pay my debt · WHEN=future" },
      { title: "Concept + roles", badges: ["rules"], engine: "ACM packs: actions → concepts", pages: ALL,
        does: "Maps the verb to a concept and binds its roles to the people and things in the sentence.",
        example: "sell → SALE · seller=I · buyer=Sarah · thing=my car" },
      { title: "State changes per ring", badges: ["rules"], engine: "ACM engine", pages: ALL,
        does: "Applies the concept's effects and lands each change on a ring: actor, impacted, local place, then the impact rules out to neighbours, organization, city, country, society and earth.",
        example: "Actor: I lose my car, gain money · Impacted: Sarah gains my car · Organization: registry records the new owner" },
      { title: "Other people's goals", badges: ["rules"], engine: "ACM relation check", pages: ALL,
        does: "Compares every change with the goals and actions from the context: advanced, enabled, blocked, at risk, hindered.",
        example: "Mark wants to buy my car → blocked (Sarah has it) · my own aim ‘pay my debt’ → enabled" },
      { title: "Ask a question", badges: ["real", "rules"], engine: "MLM parses the question · acm/ask.py", pages: ["demo"],
        does: "MLM reads your question; ACM picks the subjects, rings or intent it names (who, why, where, when, what-if) and answers from its report. A what-if re-runs ACM on the new clause and lists what changes.",
        example: "“What happens to Mark?” → Other actors / goal: buy my car — blocked" },
      { title: "LLM words the answer", badges: ["llm"], engine: "qwen2.5:7b on Ollama (local)", pages: ["demo"],
        does: "Writes the answer in plain sentences plus one Phrase DNA line per consequence, using only ACM's facts. ACM's own rows stay underneath as evidence; without the LLM, ACM's sentence is shown.",
        example: "“Mark's plan to buy the car is blocked, because Sarah now has it.” → WHO=Mark · DOES=goal blocked · WHY=because: I will sell my car to Sarah" },
    ],
  },
  image: {
    lead: "A picture of a scene + a proposed action (not read from the picture) → the objects and their state → simulated motion → consequences → answers per object.",
    steps: [
      { title: "Image + proposed action", badges: ["input"], engine: "you", pages: ALL,
        does: "The picture shows a scene. The action is stated separately: a still image cannot show what someone intends.",
        example: "tabletop photo · “push the blue cup 0.20 m toward the edge”" },
      { title: "Detect objects", badges: ["mock"], engine: "YOLO-style detector (mock: boxes from the fixture scene)", pages: ["demo"],
        does: "Finds each object with a box, a class and a confidence. A live version would run a detector or a vision-language model.",
        example: "cup 0.93 · cup 0.91 · dining table 0.97" },
      { title: "MLM scene meaning", badges: ["fixture", "real"], engine: "fixture extraction → MLM meaning schema", pages: ["demo", "multimodal"],
        does: "Writes the scene as MLM meaning: entities, positions, relations (on, near the edge). Claims an image cannot support are rejected with a reason.",
        example: "blue_cup_01 on table_01 · near the right edge · rejected: “someone pushed the cup”" },
      { title: "Behaviour library", badges: ["assumed"], engine: "object class → material, mass, friction, rules", pages: ["demo"],
        does: "Looks each class up like a game engine's physical materials: material, mass, friction, bounce, fragility, container, and the physics rules that apply.",
        example: "cup → ceramic, 0.3 kg, μ 0.35, breaks above 2.5 m/s, container (contents unknown)" },
      { title: "Simulate the action", badges: ["sim"], engine: "tabletop simulator (ACM) · matter.js rigid bodies (physics lab)", pages: ["demo", "multimodal"],
        does: "Runs the action: sliding friction, support, tipping at the edge, falling, collisions. The physics lab shows it in side view with a timeline.",
        example: "crosses the edge t=0.31 s → falls → hits the floor 3.7 m/s → may break" },
      { title: "ACM consequences", badges: ["rules", "sim"], engine: "ACM engine", pages: ["demo", "multimodal"],
        does: "Places simulated changes and rule-derived ones on the rings. What cannot be known (damage, spill) is marked unknown with what it would need.",
        example: "Impacted: blue cup loses the table's support, is on the floor · spill: unknown — needs contents" },
      { title: "Ask about an object", badges: ["llm", "sim"], engine: "LLM reads the question → simulator → LLM words the events", pages: ["demo"],
        does: "The LLM turns your question into a plan (object, intent, action, distance); the simulator runs it; the LLM answers from the events and library values only. Falls back to a keyword parser.",
        example: "“Will the red mug survive a hard knock to the right?” → flick red_cup_01 +x → events → answer" },
    ],
  },
  video: {
    lead: "A clip → objects tracked over time → meaning up to a checkpoint T → predict from T → compare with what actually happened → answers per object.",
    steps: [
      { title: "Clip + checkpoint T", badges: ["input"], engine: "you", pages: ALL,
        does: "A video and a moment T. The prediction may only use frames up to T, so it can be checked against what follows.",
        example: "synthetic clip, T = 2.0 s (just before the push)" },
      { title: "Detect + track", badges: ["mock"], engine: "YOLO + ByteTrack style (mock)", pages: ["demo"],
        does: "Finds the objects in each frame and keeps one identity per object over time.",
        example: "track #2 blue_cup_01 · track #4 pusher_01 (hand)" },
      { title: "MLM timeline", badges: ["fixture", "real"], engine: "fixture events → MLM meaning schema", pages: ["demo", "multimodal"],
        does: "Writes events with their roles and times; the scene is cut at T. Causes the frames cannot show stay uncertain.",
        example: "2.0–3.0 s push AGENT=pusher_01 PATIENT=blue_cup_01 · 3.0–4.0 s fall (after T: not used)" },
      { title: "Behaviour library", badges: ["assumed"], engine: "object class → material, mass, friction, rules", pages: ["demo"],
        does: "The same library as for images; the hand is an agent that moves as the action says.",
        example: "pusher → agent, rule: contact push" },
      { title: "Predict from T", badges: ["sim", "rules"], engine: "tabletop simulator + ACM · matter.js (physics lab)", pages: ["demo", "multimodal"],
        does: "Simulates the proposed action from the state at T and lets ACM place the consequences on the rings.",
        example: "push 0.20 m +x → crosses the edge → falls · landing position: unknown" },
      { title: "Compare with what happened", badges: ["fixture"], engine: "scripted outcome + metrics", pages: ["demo", "multimodal"],
        does: "Plays the rest of the clip and scores the prediction: fall predicted and observed, support state, position error.",
        example: "fall: precision 1 / recall 1 · red cup position error 0 m · landing: abstained" },
      { title: "Ask about an object", badges: ["llm", "sim"], engine: "LLM → simulator → LLM", pages: ["demo"],
        does: "As for images: the LLM reads the question, the simulator answers it, the LLM words the events.",
        example: "“What does the hand do?” → pusher_01 is the actor: it pushes blue_cup_01 0.20 m…" },
    ],
  },
};

const PAGE_NOTE: Record<PageKind, Partial<Record<InputKind, string>>> = {
  demo: {},
  inference: { phrase: "On this page the parses are frozen real MLM parses and every answer is assembled by ACM; no LLM writes them. Ask your own questions (with the LLM) on the ACM Demo page." },
  multimodal: {
    phrase: "Here the sentence states a tabletop plan: MLM reads it, the positions are assumed (text has no geometry) and the tabletop simulator predicts the motion before ACM.",
    image: "This page shows the meaning and ACM stages in detail. Detection, the behaviour library, the physics lab and the object chat are on the ACM Demo page.",
    video: "This page shows the meaning and ACM stages in detail. Tracking, the physics lab and the object chat are on the ACM Demo page.",
  },
};

/** The matching row of the "MLM → ACM" infographic, cropped from public/acm/how-chat-works.webp. */
const CHAT_IMAGE: Record<InputKind, { src: string; h: number; alt: string }> = {
  phrase: {
    src: "/acm/how-chat-phrase.webp", h: 376,
    alt: "Phrase chat: 1 question, 2 MLM parses it (Stanza and its own rules) into Phrase DNA, 3 ACM's rule packs compute the consequences, " +
      "4 the LLM phrases ACM's facts in plain language; ACM's sentence and supporting rows stay visible as evidence.",
  },
  image: {
    src: "/acm/how-chat-image-video.webp", h: 368,
    alt: "Image/video chat: 1 question and scene, 2 the LLM plans the object, question, action and force, 3 matter.js simulates it with " +
      "library properties, 4 the LLM explains the simulated events; object assumptions and simulation events stay visible.",
  },
  video: { src: "/acm/how-chat-image-video.webp", h: 368, alt: "" },
};
CHAT_IMAGE.video.alt = CHAT_IMAGE.image.alt;

const LABEL: Record<InputKind, string> ={ phrase: "Phrase", image: "Image", video: "Video" };
const PAGE_NAME: Record<PageKind, string> = { demo: "ACM Demo", inference: "What happens next?", multimodal: "Text · Image · Video" };

function BadgeTag({ b }: { b: Badge }) {
  return (
    <span title={BADGE[b].means} className={`inline-flex rounded px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide ring-1 ring-inset ${BADGE[b].tone}`}>
      {BADGE[b].word}
    </span>
  );
}

export function HowItWorks({ inputs = ["phrase", "image", "video"], page, initial, open = true }: {
  inputs?: InputKind[];
  page: PageKind;
  initial?: InputKind;
  open?: boolean;
}) {
  const [kind, setKind] = useState<InputKind>(initial ?? inputs[0]);
  const shown = inputs.includes(kind) ? kind : inputs[0];
  const flow = STEPS[shown];
  const used = new Set(flow.steps.flatMap((s) => s.badges));
  const note = PAGE_NOTE[page][shown];
  return (
    <details open={open} className="panel-raised group px-3 py-2">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-[13px] font-semibold">
        <span aria-hidden className="text-splm-300 transition-transform group-open:rotate-90">▸</span>
        How it works{inputs.length === 1 ? ` — ${LABEL[shown].toLowerCase()}` : ""}
        <span className="faint text-[11px] font-normal">{flow.lead}</span>
      </summary>
      <div className="mt-3 flex flex-col gap-3">
        <a href={CHAT_IMAGE[shown].src} target="_blank" rel="noreferrer" title="Open full size">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={CHAT_IMAGE[shown].src} alt={CHAT_IMAGE[shown].alt} width={1568} height={CHAT_IMAGE[shown].h} className="block h-auto w-full rounded-md" />
        </a>
        {inputs.length > 1 && (
          <div role="tablist" aria-label="Input type" className="flex gap-1">
            {inputs.map((k) => (
              <button key={k} type="button" role="tab" aria-selected={k === shown} onClick={() => setKind(k)}
                className={`rounded px-2.5 py-1 text-[12px] font-semibold ${k === shown ? "bg-splm-500 text-ink-950" : "dim hover:bg-white/5"}`}>
                {LABEL[k]}
              </button>
            ))}
          </div>
        )}
        {note && <p className="text-[11.5px] text-sky-300">{note}</p>}
        <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {flow.steps.map((s, i) => {
            const here = s.pages.includes(page);
            return (
              <li key={s.title} className={`hairline relative flex flex-col gap-1.5 rounded-lg border p-2.5 ${here ? "" : "opacity-45"}`}>
                <div className="flex items-center gap-2">
                  <span className="grid size-5 shrink-0 place-items-center rounded-full bg-splm-500 text-[10.5px] font-bold text-ink-950">{i + 1}</span>
                  <span className="text-[12.5px] font-semibold leading-tight">{s.title}</span>
                </div>
                <div className="flex flex-wrap gap-1">{s.badges.map((b) => <BadgeTag key={b} b={b} />)}</div>
                <p className="text-[11.5px] leading-snug">{s.does}</p>
                <p className="faint text-[10.5px] leading-snug">runs: {s.engine}</p>
                <p className="num rounded bg-white/4 px-1.5 py-1 text-[10.5px] leading-snug">e.g. {s.example}</p>
                {!here && <p className="text-[10.5px] text-warn-400">not on this page — see {s.pages.map((p) => PAGE_NAME[p]).join(", ")}</p>}
                {i < flow.steps.length - 1 && <span aria-hidden className="faint absolute -right-2 top-3 hidden text-[13px] xl:block">→</span>}
              </li>
            );
          })}
        </ol>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10.5px]">
          {(Object.keys(BADGE) as Badge[]).filter((b) => used.has(b)).map((b) => (
            <span key={b} className="flex items-center gap-1"><BadgeTag b={b} /><span className="faint">{BADGE[b].means}</span></span>
          ))}
        </div>
      </div>
    </details>
  );
}
