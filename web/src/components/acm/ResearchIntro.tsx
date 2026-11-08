/**
 * The ARM home page's researcher intro, in five chapters plus the physical-world path:
 *
 *   What is ARM?  ·  Why it exists (LLM limits)  ·  So what (ARM vs an LLM)  ·
 *   How it works  ·  The physical world (Unreal Engine 5)  ·  What next
 *
 * The text is condensed from the ACM README (https://github.com/Sherlock2019/ACM). The LLM
 * answers quoted under "Why" are real recordings (examples/llm_baseline.json, SmolLM2-135M);
 * ARM's answers are its real outputs for the same inputs. The Unreal Engine chapter is the
 * proposed design: today the prototype runs matter.js in 2D and says so.
 */

import Link from "next/link";
import type { ReactNode } from "react";

const SCROLL = "scroll-mt-[calc(var(--nav-h,72px)+16px)]";

function Chapter({ id, n, kicker, title, lead, children }: {
  id: string; n: string; kicker: string; title: string; lead: ReactNode; children?: ReactNode;
}) {
  return (
    <section id={id} className={`panel ${SCROLL} flex flex-col gap-5 p-5 sm:p-7`}>
      <header className="flex items-start gap-4">
        <span aria-hidden className="grid size-11 shrink-0 place-items-center rounded-full bg-cyan-400/15 text-[16px] font-bold text-cyan-500">{n}</span>
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-cyan-500">{kicker}</p>
          <h2 className="mt-0.5 text-[24px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h2>
          <div className="dim mt-2 max-w-3xl text-[15px] leading-relaxed">{lead}</div>
        </div>
      </header>
      {children}
    </section>
  );
}

function Card({ title, children, tone = "plain" }: { title: string; children: ReactNode; tone?: "plain" | "warn" | "ok" }) {
  const ring = tone === "warn" ? "border-amber-400/40 bg-amber-400/5" : tone === "ok" ? "border-emerald-400/40 bg-emerald-400/5" : "";
  return (
    <div className={`panel-raised flex flex-col gap-1.5 p-4 ${ring}`}>
      <h3 className="text-[15px] font-bold">{title}</h3>
      <div className="dim text-[13.5px] leading-relaxed">{children}</div>
    </div>
  );
}

/* ---------- 01 what -------------------------------------------------------------------- */

const RINGS: { group: "who" | "where"; name: string; finding: string }[] = [
  { group: "who", name: "Self (I)", finding: "loses my car · gains money · own goal “pay my debt”: ENABLED ➕" },
  { group: "who", name: "Impacted (Sarah)", finding: "gains my car · loses money" },
  { group: "who", name: "Other actors", finding: "Mark wants my car: BLOCKED ❌ · Sarah needs a car: ADVANCED ✅" },
  { group: "where", name: "Local (Paris)", finding: "the sale takes place here" },
  { group: "where", name: "Neighbours", finding: "no known impact (no rule matched, which is not evidence of none)" },
  { group: "where", name: "Organization", finding: "insurers and the vehicle registry must record the new owner ●" },
  { group: "where", name: "Country (France)", finding: "a taxable transaction counts in national economic activity ●" },
  { group: "where", name: "Society", finding: "money circulates through the economy ●" },
  { group: "where", name: "Earth", finding: "an existing car is reused instead of a new one being made ▲" },
];

/* ---------- 02 why --------------------------------------------------------------------- */

const LIMITS = [
  { title: "It predicts words, not world states", text: "An LLM is trained to continue text. Nothing inside it records that the car now belongs to Sarah, so nothing stops the next sentence from giving it to Mark." },
  { title: "Fluent is not the same as grounded", text: "A plausible answer and a correct one look identical. The model cannot point at the rule or observation that produced its claim." },
  { title: "It never says “I don't know”", text: "Gaps are filled with the most likely words. A missing cause becomes an invented one, and an unknown verb still gets a confident verdict." },
  { title: "Same question, different answers", text: "Sampling changes the outcome. Three runs of the same prompt can disagree about who ends up with the car." },
  { title: "No physics", text: "Whether a mug falls depends on mass, friction and distance to the edge. Text statistics only roughly encode these, and the model never simulates them." },
  { title: "The view stops at the people mentioned", text: "Consequences for neighbours, organizations, the country and the earth only appear if the text happens to mention them." },
];

/* ---------- 03 so what ----------------------------------------------------------------- */

const VS: { aspect: string; llm: string; arm: string }[] = [
  { aspect: "What it outputs", llm: "the next likely words", arm: "explicit state changes: has(Sarah, car) = true" },
  { aspect: "Why it says so", llm: "hidden in the weights", arm: "every consequence carries its basis (rule · simulation · observation) and the rule that fired" },
  { aspect: "Unknowns", llm: "filled with plausible text", arm: "reported: “no rule matched” never means “no impact”, and unknown places are not guessed" },
  { aspect: "Other people's goals", llm: "often forgotten or contradicted", arm: "checked one by one: advanced · enabled · blocked · at risk · hindered" },
  { aspect: "Reach", llm: "whoever the text mentions", arm: "the full blast radius: self → impacted → others → local → … → earth" },
  { aspect: "Physical actions", llm: "guessed from text", arm: "simulated in a physics engine using object properties" },
  { aspect: "Repeatability", llm: "varies with sampling", arm: "same input, same report, same certainty score" },
  { aspect: "Memory", llm: "the context window", arm: "a graph vector database of every analysed action" },
  { aspect: "Changing what it knows", llm: "retrain or fine-tune", arm: "edit a YAML pack; no Python, no retraining" },
];

const LLM_BETTER = ["breadth: it has seen every verb", "fluency: it writes natural sentences", "unseen situations: it always answers something"];

/* ---------- 04 how --------------------------------------------------------------------- */

const STEPS: { n: number; title: string; text: string; code?: string }[] = [
  { n: 1, title: "Phrase DNA (MLM)", text: "The Meaning Language Model parses the sentence into who · does what · to whom · where · when · why. A purpose (“to pay my debt”) becomes its own nested frame.",
    code: "WHO self · DOES sell · WHAT my car\nTO WHOM Sarah · WHERE Paris · WHEN tomorrow\nWHY → pay(my debt)" },
  { n: 2, title: "Concept and state changes", text: "The verb maps to a universal concept (sell, vendre and bán all reach SALE). The concept says what becomes true or false.",
    code: "has(Sarah, car)  = true\nhas(self, car)   = false\nhas(self, money) = true" },
  { n: 3, title: "Who it lands on", text: "Each change is placed on the actor, the impacted participants or the local environment." },
  { n: 4, title: "Other actors' goals", text: "Context sentences (“Mark wants to buy my car”) become wanted states. Exclusive states, such as one owner per thing, show who is blocked and who is helped." },
  { n: 5, title: "Blast radius, layer by layer", text: "A gazetteer gives each place its neighbours, organization, city and country. Impact rules, each scoped to a layer, say what the action does there, out to society and the earth." },
  { n: 6, title: "Graph + vector memory", text: "The whole report becomes one graph with an 83-dimensional vector on every node, stored in SQLite and searchable by similarity and by entity history." },
  { n: 7, title: "The LLM only phrases it", text: "A local LLM (qwen2.5:7b) turns ARM's facts into plain sentences. It may use only what ARM or the simulator computed. It never decides a consequence." },
];

/* ---------- 05 unreal ------------------------------------------------------------------ */

const UE_SYSTEMS = [
  { name: "Chaos Physics", role: "Simulates the action", text: "Rigid bodies, collisions and gravity, plus Chaos Destruction for breakage. The proposed push becomes a force; the engine steps time, and the mug slides, tips and falls." },
  { name: "Physical Materials", role: "Gives objects their properties", text: "Friction, restitution and density for each surface. Values come from ARM's per-environment object library (kitchen, house, garden, street, mountain): mass, shape, texture, material." },
  { name: "Sequencer + Movie Render Queue", role: "Shows what would happen", text: "Renders the predicted outcome as frames or video from the original camera, so the prediction can be compared, frame by frame, with what really happened." },
];

const UE_LOOP = [
  "Image / video", "Recognise objects + library properties", "Rebuild the scene in Unreal 3D",
  "Apply the proposed action", "Chaos steps the physics", "Events → ARM state changes (basis: simulation)", "Rings + explanation, before acting",
];

/* ---------- 06 next -------------------------------------------------------------------- */

const NEXT = [
  { title: "Unreal Engine 5 in the loop", text: "Replace the 2D matter.js stand-in with a 3D Unreal scene driven through its Python / Remote Control API, and feed simulated events back into ARM." },
  { title: "Real perception", text: "Swap the hand-authored image and video replays for a vision-language model (Qwen3-VL) and a detector/tracker (YOLO), keeping the no-future-leakage rule." },
  { title: "Bigger knowledge packs", text: "Today: about 18 concepts, 50 English verbs, 40 impact rules and 20 places. Each one is a YAML edit away, in more languages." },
  { title: "Learned components that beat the baseline", text: "A learned embedder, then trained consequence models. The current rules are the honest baseline they must outperform on the benchmark." },
  { title: "World models", text: "V-JEPA 2-AC and similar models plug in behind the same transition interface as the tabletop simulator." },
  { title: "An AI checking its own actions", text: "When the actor is “I”, the report is the agent's view of its own planned action. ARM becomes a pre-action check: see the consequences, then decide." },
  { title: "People and objects together", text: "Human responses to physical events, such as a worker reacting to a falling box. This is a concept today and not built yet." },
];

export function ResearchIntro() {
  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="Intro chapters" className="flex flex-wrap gap-2 text-[13px] font-semibold">
        {[["what", "What"], ["why", "Why"], ["so-what", "So what"], ["how", "How"], ["unreal", "Physical world"], ["next", "What next"]].map(([id, label]) => (
          <a key={id} href={`#${id}`} className="rounded-full border border-[var(--border)] px-3 py-1.5 transition-colors hover:border-cyan-400 hover:text-cyan-500">{label}</a>
        ))}
      </nav>

      {/* 01 WHAT */}
      <Chapter id="what" n="01" kicker="What it is" title="A model that predicts what an action does"
        lead={<>
          A language model predicts the next word. <b className="text-[var(--text)]">MLM</b>, the Meaning Language Model, first works out what a sentence
          means. <b className="text-[var(--text)]">ARM, the Action Reaction Model, goes one step further: it predicts what an action <i>does</i>.</b> It
          traces the consequences for the one acting, for those it lands on and for other actors' goals, and then across its whole <b className="text-[var(--text)]">blast radius</b>,
          from the place where it happens out to the earth.
        </>}>
        <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="flex flex-col gap-3">
            <blockquote className="rounded-lg border-l-4 border-cyan-400 bg-cyan-400/10 p-4 text-[16px] font-semibold leading-snug">
              “I will sell my car to Sarah in Paris tomorrow to pay my debt.”
              <span className="dim mt-2 block text-[13px] font-normal">Context: “Mark wants to buy my car.” “Sarah needs a car.”</span>
            </blockquote>
            <p className="dim text-[13.5px] leading-relaxed">
              One sentence in, one structured report out, ring by ring. Three circles say <b>who</b> is affected. Seven layers say <b>where</b> the effects land.
              When the actor is <b>“I”</b>, the report is the model's view of its <b>own</b> planned action.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] border-collapse text-[13px]">
              <tbody>
                {RINGS.map((r) => (
                  <tr key={r.name} className="hairline border-b last:border-0">
                    <td className="py-1.5 pr-2 align-top">
                      <span className={`rounded px-1.5 py-0.5 text-[10.5px] font-bold uppercase ${r.group === "who" ? "bg-violet-400/15 text-violet-400" : "bg-cyan-400/15 text-cyan-500"}`}>{r.group}</span>
                    </td>
                    <td className="whitespace-nowrap py-1.5 pr-3 align-top font-semibold">{r.name}</td>
                    <td className="dim py-1.5 align-top">{r.finding}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Chapter>

      {/* 02 WHY */}
      <Chapter id="why" n="02" kicker="Why it exists" title="Language fluency is not a world model"
        lead={<>LLMs are remarkable at language, but an agent that acts in the world needs to know what its actions <i>change</i>. An LLM has these limits by design:</>}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {LIMITS.map((l) => <Card key={l.title} title={l.title}>{l.text}</Card>)}
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <Card title="Recorded: a real LLM, the same question" tone="warn">
            <p className="mb-2 text-[12.5px]">“Mark wants to buy John's car. Sarah needs a car. John sold his car to Sarah. <b>What happens next to Mark?</b>”</p>
            <ul className="flex flex-col gap-1 text-[13px]">
              <li>greedy: <i>“Mark buys a car.”</i></li>
              <li>sample: <i>“Mark gets a car.”</i></li>
              <li>sample: <i>“Mary bought a car. Mary sold a car to Mark.”</i></li>
            </ul>
            <p className="faint mt-2 text-[11.5px]">SmolLM2-135M, local, recorded 2026-10-26 (examples/llm_baseline.json). A small base model makes the failure easy to see; larger models fail less often, but in the same way and less visibly.</p>
          </Card>
          <Card title="ARM, same input" tone="ok">
            <p className="text-[14px] font-semibold text-[var(--text)]">Mark wants to buy John's car: BLOCKED ❌</p>
            <p className="mt-1 text-[13px]">Why: SALE makes <code className="num">has(Sarah, car) = true</code>. Ownership is exclusive, so <code className="num">has(Mark, car)</code> cannot hold.</p>
            <p className="mt-1 text-[13px]">Sarah needs a car: ADVANCED ✅. Basis: rule, certainty 1.0 (past action).</p>
          </Card>
        </div>
      </Chapter>

      {/* 03 SO WHAT */}
      <Chapter id="so-what" n="03" kicker="So what" title="What ARM gives you that LLM mode does not"
        lead="Rules determine the outcomes and the LLM only explains them. Every claim can be inspected, repeated and corrected.">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] border-collapse text-[13.5px]">
            <thead>
              <tr className="hairline border-b text-left text-[11px] uppercase tracking-wider">
                <th className="faint py-2 pr-3 font-semibold"> </th>
                <th className="py-2 pr-3 font-semibold text-amber-500">LLM mode</th>
                <th className="py-2 font-semibold text-cyan-500">ARM</th>
              </tr>
            </thead>
            <tbody>
              {VS.map((v) => (
                <tr key={v.aspect} className="hairline border-b last:border-0">
                  <td className="py-2 pr-3 align-top font-semibold">{v.aspect}</td>
                  <td className="dim py-2 pr-3 align-top">{v.llm}</td>
                  <td className="py-2 align-top">{v.arm}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="dim rounded-lg border border-dashed border-[var(--border)] p-3 text-[13px]">
          <b className="text-[var(--text)]">Where an LLM is still better:</b> {LLM_BETTER.join(" · ")}. That is why ARM keeps an LLM to phrase its
          answers and to read free-form questions, but never lets it decide a consequence.
        </p>
      </Chapter>

      {/* 04 HOW */}
      <Chapter id="how" n="04" kicker="How it works" title="From a sentence to its consequences in seven explicit steps"
        lead={<>No linguistic or world facts live in Python. Which verb is a sale, what a sale changes, which country Paris is in and what flying does to the climate
          are all YAML packs, so a researcher can read, test and extend every rule.</>}>
        <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {STEPS.map((s) => (
            <li key={s.n} className="panel-raised flex flex-col gap-2 p-4">
              <div className="flex items-center gap-2">
                <span className="num grid size-7 place-items-center rounded-full bg-cyan-400 text-[13px] font-bold text-[#0b1b2e]">{s.n}</span>
                <h3 className="text-[15px] font-bold">{s.title}</h3>
              </div>
              <p className="dim text-[13px] leading-relaxed">{s.text}</p>
              {s.code && <pre className="num mt-auto overflow-x-auto rounded-md bg-[var(--page)] p-2 text-[11.5px] leading-snug">{s.code}</pre>}
            </li>
          ))}
          <li className="flex flex-col justify-center gap-2 rounded-lg border border-dashed border-cyan-400/50 p-4 text-[13px]">
            <b>Honesty rules, enforced in tests</b>
            <span className="dim">Unknown verb → no verdict. No rule ≠ no impact. Unknown place → not placed. Negation changes nothing. Observed, proposed and predicted never merge. No future leakage.</span>
          </li>
        </ol>
        <div className="flex flex-wrap gap-3 text-[13px]">
          <Link href="/acm/tour" className="rounded-lg bg-cyan-400 px-4 py-2 font-semibold text-[#0b1b2e] hover:bg-cyan-300">Step-by-step tour →</Link>
          <Link href="/acm/inference" className="rounded-lg border border-[var(--border)] px-4 py-2 font-semibold hover:border-cyan-400">53 actions, 283 answers with reasoning →</Link>
          <a href="https://github.com/Sherlock2019/ACM" target="_blank" rel="noreferrer" className="rounded-lg border border-[var(--border)] px-4 py-2 font-semibold hover:border-cyan-400">README and code ↗</a>
        </div>
      </Chapter>

      {/* 05 UNREAL */}
      <Chapter id="unreal" n="05" kicker="The physical world" title="Unreal Engine 5: letting the AI see the physical consequences of its actions"
        lead={<>Words cannot tell an agent whether a pushed mug falls. A game engine can. ARM proposes using three systems that already exist in
          <b className="text-[var(--text)]"> Unreal Engine 5</b> to rebuild the scene in 3D, simulate the proposed action and return what happens as
          ARM state changes with the basis <code className="num">simulation</code>, before the agent acts.</>}>
        <div className="grid gap-3 md:grid-cols-3">
          {UE_SYSTEMS.map((u, i) => (
            <div key={u.name} className="panel-raised flex flex-col gap-1.5 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-cyan-500">Engine {i + 1} · {u.role}</p>
              <h3 className="text-[16px] font-bold">{u.name}</h3>
              <p className="dim text-[13px] leading-relaxed">{u.text}</p>
            </div>
          ))}
        </div>
        <ol aria-label="The physical loop" className="flex flex-wrap items-stretch gap-2 text-[12.5px]">
          {UE_LOOP.map((s, i) => (
            <li key={s} className="flex items-center gap-2">
              <span className={`rounded-lg px-3 py-2 font-medium ${i === 2 || i === 4 ? "bg-cyan-400/15 text-cyan-500 ring-1 ring-cyan-400/40" : "panel-raised"}`}>{s}</span>
              {i < UE_LOOP.length - 1 && <span aria-hidden className="faint">→</span>}
            </li>
          ))}
        </ol>
        <p className="rounded-lg border border-amber-400/40 bg-amber-400/5 p-3 text-[13px]">
          <b>Prototype status:</b> the Image / Video chat runs a <b>matter.js</b> 2D rigid-body engine as a stand-in for Unreal, and object detection is mocked.
          Object properties are library assumptions, and the page labels them that way. <Link href="/acm/scene?source=image" className="font-semibold text-cyan-500 underline">Try the physics lab →</Link>
        </p>
      </Chapter>

      {/* 06 NEXT */}
      <Chapter id="next" n="06" kicker="What next" title="The research roadmap"
        lead="The current system is a transparent, rule-based baseline. Each next step replaces one part with something learned or simulated, measured against that baseline.">
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {NEXT.map((x, i) => (
            <li key={x.title} className="panel-raised flex flex-col gap-1.5 p-4">
              <span className="num text-[12px] font-bold text-cyan-500">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="text-[15px] font-bold leading-snug">{x.title}</h3>
              <p className="dim text-[13px] leading-relaxed">{x.text}</p>
            </li>
          ))}
        </ol>
      </Chapter>
    </div>
  );
}
