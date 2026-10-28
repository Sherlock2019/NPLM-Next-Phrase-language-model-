"use client";

/** Definitions: the terms used across the site (ARM, MLM, LLM, Phrase DNA, rings, badges...), searchable. */

import { useMemo, useState } from "react";
import { inputClass } from "@/components/ui";

interface Term {
  term: string;
  full?: string;
  text: string;
  example?: string;
}

const GROUPS: { title: string; terms: Term[] }[] = [
  {
    title: "The models",
    terms: [
      {
        term: "ARM", full: "Action Reaction Model",
        text: "This system. It predicts what an action changes and for whom: for the one acting, for those it lands on, for other people's goals, and across its blast radius from the place it happens out to the earth. It works from a sentence, an image or a video, and gives a reason for every claim. Its engine is the Python package acm (the project was first called ACM, the Actions Consequential Model).",
        example: "“John flew to London.” → John is now in London; aircraft noise for Croydon, Watford, Slough; emissions for the UK and the earth.",
      },
      {
        term: "MLM", full: "Meaning Language Model",
        text: "The meaning layer under ARM. It reads a sentence into its structure — who does what, to whom, where, when, how and why (Phrase DNA) — with the Stanza parser and its own rules. It does not use an LLM to do this. MLM also has a next-word prediction mode (the MLM Playground) that re-scores a small language model's guesses with that structure.",
        example: "“John will meet Sarah in Paris tomorrow” → WHO John · DOES meet · WITH WHOM Sarah · WHERE Paris · WHEN tomorrow.",
      },
      {
        term: "LLM", full: "Large Language Model",
        text: "A neural network trained to continue text. In ARM a local LLM (qwen2.5:7b, run with Ollama) only puts answers into words and reads free-form physics questions; it never decides a consequence — those come from ARM's rules and the simulator. Without it, the chats fall back to ARM's own sentences.",
      },
      {
        term: "SmolLM2", full: "a small base language model (135M parameters)",
        text: "The model MLM's next-word prediction re-scores in the MLM Playground, Ablation and Benchmark pages. It is not instruction-tuned and plays no part in ARM's consequences.",
      },
      {
        term: "Stanza",
        text: "A dependency parser from Stanford NLP. MLM uses it to find each word's grammatical role before building Phrase DNA.",
      },
      {
        term: "Ollama",
        text: "A program that runs language models on your own machine. ARM uses it to run qwen2.5:7b locally, so no text leaves the machine. Set ACM_LLM_MODEL to use another model (e.g. qwen2.5:3b on a machine without a GPU).",
      },
    ],
  },
  {
    title: "Reading a sentence",
    terms: [
      {
        term: "Phrase DNA", full: "Universal Phrase Frame",
        text: "MLM's structure of one clause: WHO (subject) · DOES (predicate) · WHAT (objects) · TO WHOM (recipients) · WITH WHOM (participants) · WHERE / WHERE TO / FROM WHERE · WHEN · HOW · WHY (goal or cause) · IF (condition), plus tense, negation and modality.",
      },
      {
        term: "Context",
        text: "Earlier sentences given with the action. ARM reads them for other people's goals and actions, so it can say whose plan an action helps or blocks.",
        example: "context “Mark wants to buy my car.” + action “I will sell my car to Sarah.” → Mark's goal: blocked.",
      },
      {
        term: "Self view",
        text: "When the actor is “I”, the report is the model's view of its own planned action.",
      },
      {
        term: "Concept",
        text: "The kind of action a verb stands for, from ARM's knowledge packs (sell → SALE, fly → MOVE, steal → THEFT). Each concept declares its roles and the state changes it causes.",
      },
      {
        term: "Roles bound",
        text: "Which person or thing fills each role of the concept, taken from Phrase DNA (seller = John, buyer = Sarah, thing = his car).",
      },
      {
        term: "Negation",
        text: "A negated action (“John did not sell his car”) changes nothing; ARM says so instead of predicting consequences.",
      },
    ],
  },
  {
    title: "Consequences",
    terms: [
      {
        term: "Consequence",
        text: "A change ARM predicts: a state that becomes true or false (Sarah has the car; John no longer has it), or an impact on a wider layer (aircraft noise for the neighbours).",
      },
      {
        term: "Blast radius",
        text: "How far an action's effects reach, ring by ring: who is affected, then where.",
      },
      {
        term: "Rings",
        text: "Who: Actor (the one acting) · Impacted (what or whom it lands on) · Other actors (their goals and actions). Where: Local environment (where it happens) · Neighbours · Organization · City · Country · Society · Earth.",
      },
      {
        term: "Knowledge packs (rule packs)",
        text: "ARM's YAML knowledge: verbs → concepts, each concept's effects, impact rules per layer, and a place gazetteer (London → its neighbours, city, country). Every rule-derived row names the rule it came from.",
      },
      {
        term: "Impact rule",
        text: "A rule that fires for a layer when the action's concept or its categories match (flying → aircraft noise for the neighbours, emissions for the country and the earth).",
      },
      {
        term: "Goal status",
        text: "How an action bears on someone's goal: advanced (makes it true), enabled (provides what it needs), blocked (makes it impossible), at risk (blocked, unless an unnamed participant turns out to be the goal's owner), hindered (removes something it needs), unaffected, or no evidence.",
      },
      {
        term: "Certainty",
        text: "A rule weight from tense, modality and conditions (a past action 1.0, a planned one 0.9). It is not a calibrated probability.",
      },
      {
        term: "No supporting evidence",
        text: "No rule matched for that ring. It never means “no impact”.",
      },
      {
        term: "What-if (counterfactual)",
        text: "A question like “What if John took the train?”: ARM runs again on the new action, with the same context, and lists which consequences are new, which no longer follow and which stay.",
      },
    ],
  },
  {
    title: "Images, video and physics",
    terms: [
      {
        term: "Object recognition",
        text: "The first step for images and video: a computer-vision model identifies each object and matches it to the object library of the environment it sees. In this prototype it is mocked.",
      },
      {
        term: "Object library",
        text: "Typical objects per environment — kitchen, house, garden, street, mountain — each with mass, shape, texture and material, plus friction, restitution, fragility and the physics rules that apply.",
        example: "mug → ceramic · 0.3 kg · cylinder with handle · smooth glaze · μ 0.35 · breaks above 2.5 m/s.",
      },
      {
        term: "Physics engine",
        text: "Software that simulates how objects move under forces, gravity and collisions. The proposed engine is Unreal Engine 5 / Chaos; this prototype uses matter.js in 2D.",
      },
      {
        term: "Friction (μ)",
        text: "How strongly a surface resists sliding. A sliding object slows at μ·g.",
      },
      {
        term: "Restitution (e)",
        text: "How bouncy a collision is: 0 = no bounce, 1 = a perfect bounce.",
      },
      {
        term: "Break speed",
        text: "The impact speed above which a fragile object may break (an assumed library value; a ceramic mug: 2.5 m/s).",
      },
      {
        term: "Checkpoint T",
        text: "For video: the moment the prediction is made from. Only frames up to T are used, so the prediction can be compared with what happened after.",
      },
    ],
  },
  {
    title: "Labels you will see",
    terms: [
      { term: "Rule-derived", text: "Computed by ARM's knowledge packs; deterministic, with the rule named." },
      { term: "Simulated", text: "Computed by a physics simulator." },
      { term: "Observed", text: "Read from the evidence (a sentence, an image, a video)." },
      { term: "Inferred", text: "Concluded from the evidence, not stated in it." },
      { term: "Assumed", text: "A typical value used because the evidence cannot give it (table height, a mug's mass)." },
      { term: "Unknown", text: "ARM cannot say, and states what it would need (e.g. whether the cup spills: its contents)." },
      { term: "Generic", text: "ARM has no concept for the verb, so it gives no verdict." },
      { term: "Fixture", text: "A hand-authored extraction replayed in the demo, labelled as such — not live model output." },
      { term: "Mock", text: "A stand-in for a model that is not wired in yet (e.g. object detection)." },
      { term: "Ablation", text: "Switching parts of MLM off one at a time to measure what each one contributes." },
    ],
  },
];

export default function DefinitionsPage() {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const groups = useMemo(
    () => GROUPS.map((g) => ({
      ...g,
      terms: g.terms.filter((t) => !q || [t.term, t.full ?? "", t.text, t.example ?? ""].join(" ").toLowerCase().includes(q)),
    })).filter((g) => g.terms.length),
    [q],
  );

  return (
    <div className="flex flex-col gap-5">
      <header className="panel flex flex-col gap-3 p-5 sm:p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Definitions</h1>
        <p className="dim max-w-3xl text-[14px] leading-relaxed">
          The terms used across ARM: the models (ARM, MLM, LLM), how a sentence is read, how consequences are predicted, the physics
          side, and the labels on every row.
        </p>
        <input className={`${inputClass} max-w-md text-[13px]`} placeholder="Search a term… (e.g. MLM, ring, friction)"
          value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search definitions" />
        <nav aria-label="Sections" className="flex flex-wrap gap-1.5 text-[12px]">
          {GROUPS.map((g) => (
            <a key={g.title} href={`#${g.title.toLowerCase().replace(/[^a-z]+/g, "-")}`} className="panel-raised px-2.5 py-1 hover:text-[var(--text)]">
              {g.title}
            </a>
          ))}
        </nav>
      </header>

      {groups.length === 0 && <p className="faint text-[13px]">No term matches “{query}”.</p>}
      {groups.map((g) => (
        <section key={g.title} id={g.title.toLowerCase().replace(/[^a-z]+/g, "-")}
          className="panel scroll-mt-[calc(var(--nav-h,72px)+16px)] p-5">
          <h2 className="mb-3 text-[18px] font-semibold">{g.title}</h2>
          <dl className="grid gap-3 md:grid-cols-2">
            {g.terms.map((t) => (
              <div key={t.term} id={t.term.toLowerCase().replace(/[^a-z0-9]+/g, "-")} className="panel-raised flex flex-col gap-1 p-3">
                <dt className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-[16px] font-bold text-cyan-400">{t.term}</span>
                  {t.full && <span className="dim text-[13px]">{t.full}</span>}
                </dt>
                <dd className="text-[13.5px] leading-relaxed">{t.text}</dd>
                {t.example && <dd className="faint text-[12.5px] italic leading-snug">e.g. {t.example}</dd>}
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}
