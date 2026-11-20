/**
 * "What it is": the README's WHAT · WHY · SO WHAT · WHAT NEXT on one page.
 * Figures are the README's measured results (SmolLM2-135M, 61-item hand-written suite) with
 * the same caveats; nothing here is new evidence.
 */

import Link from "next/link";
import { ACM_PROJECT_URL } from "@/lib/app";
import { Caveat, Panel, Pill } from "@/components/ui";

const REPO = "https://github.com/Sherlock2019/NPLM-Next-Phrase-language-model-";

const WHY_ROWS: [string, string, string][] = [
  [
    "“John will meet Sarah in ___”",
    "A probability over fragments: the 38.3%, a 5.4%, her 3.3%. No idea what kind of word is needed.",
    "Expected slot: location 81.6%, time 13.8%. Paris, London, Boston gain +2.05 logits.",
  ],
  [
    "“If John knew that Sarah might leave, he would call her.”",
    "One flat string of tokens.",
    "A nested frame: ACTION call (conditional) under STATE know (John), containing ACTION leave (Sarah, possible).",
  ],
  [
    "The same event in English, French and Vietnamese",
    "Three unrelated token sequences.",
    "The same structure: ACTION meet · WHO John · WITH WHOM Sarah · WHERE Paris. Agreement en↔fr 93.3%.",
  ],
  [
    "🎤 “Book a meeting with Sarah tomorrow.” (spoken)",
    "Qwen alone: “Please provide your availability for a meeting with Sarah tomorrow.”",
    "Phrase DNA finds a day but no clock time and asks: “What time would you like to book meeting with Sarah?”",
  ],
  [
    "What is missing from a sentence",
    "Not tracked.",
    "Listed: “NOT STATED: WHAT, TO WHOM, WHERE TO, USING WHAT, WHY”.",
  ],
];

const RESULTS: [string, string, string, string][] = [
  ["Expected slot accuracy (top-1)", "—", "73.8% (45/61)", "PLM-only capability"],
  ["Next-word accuracy (top-1)", "63.6%", "72.7%", "insufficient data (n=11)"],
  ["Mean reciprocal rank", "0.739", "0.809", "—"],
  ["Latency per prediction (warm)", "75 ms", "306 ms", "cost: about 4×"],
];

export default function WhatItIsPage() {
  return (
    <div className="flex flex-col gap-4">
      <section className="panel p-6">
        <p className="eyebrow">What it is</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">
          PLM · Phrase Language Model: understand meaning before predicting language
        </h1>
        <p className="dim mt-2 max-w-4xl text-[13px] leading-relaxed">
          A language model predicts the next <em>token</em>, often a fragment of a word, from statistics. PLM
          first asks <strong>who does what, to whom, where, when, how and why</strong>, turns the sentence into
          language-independent <strong>Universal Phrase DNA</strong>, predicts which kind of meaning comes next,
          and then re-scores the <em>same</em> Transformer&apos;s candidates against it. A research proof of
          concept in English, French and Vietnamese.
        </p>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <a href="#what" className="rounded-md bg-splm-500/15 px-3 py-1.5 font-medium text-splm-300">What</a>
          <a href="#why" className="rounded-md bg-splm-500/15 px-3 py-1.5 font-medium text-splm-300">Why: the problem</a>
          <a href="#so-what" className="rounded-md bg-splm-500/15 px-3 py-1.5 font-medium text-splm-300">So what: vs an LLM</a>
          <a href="#what-next" className="rounded-md bg-splm-500/15 px-3 py-1.5 font-medium text-splm-300">What next: evolution</a>
        </div>
      </section>

      <div id="what" className="scroll-mt-24">
        <Panel title="What · a meaning layer on top of a language model">
          <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
            <div className="flex flex-col gap-3 text-[13px] leading-relaxed">
              <p>
                Before the language model picks the next token, PLM asks <em>what is happening, who is involved,
                and what information is missing?</em> The token model still writes the words; Phrase DNA decides
                what <em>kind</em> of words should come next.
              </p>
              <pre className="num panel-raised overflow-x-auto p-3 text-[11.5px] leading-relaxed">{`John will meet Sarah in Paris tomorrow.

ACTION: meet     WHO: John     WITH WHOM: Sarah
WHERE:  Paris    WHEN: tomorrow     tense=future`}</pre>
              <ul className="dim flex list-disc flex-col gap-1 pl-5 text-[12.5px]">
                <li><strong>Universal Phrase DNA</strong>: WHO · ACTION or STATE · WHAT · TO WHOM · WHERE · WHEN · HOW · USING WHAT · WITH WHOM · WHY · FOR WHAT GOAL, independent of word order and language.</li>
                <li><strong>Expected-slot predictor</strong>: which kind of meaning comes next (a place, a time, an instrument…).</li>
                <li><strong>Candidate scorer</strong>: re-weights the Transformer&apos;s top-K candidates against the slot; every change is explained.</li>
                <li><strong>Context graph</strong>, <strong>language packs</strong> (YAML, en · fr · vi), and a <strong>Speech Lab</strong>: talk, see your words sorted into Phrase DNA, hear the answer.</li>
              </ul>
            </div>
            <div className="flex flex-col gap-2">
              <p className="eyebrow">What it is not (yet)</p>
              {[
                ["Not a new foundation model", "it re-scores an existing Transformer; everything reported is rule-based."],
                ["Not proven on natural text", "the favourable numbers come from a small hand-written suite."],
                ["Not a filter", "it re-weights and deletes nothing: “less compatible”, never “impossible”."],
                ["Not real vision yet", "image and video inputs are labelled replays."],
                ["Not a production voice assistant", "the Speech Lab is a measurement bench on CPU."],
              ].map(([title, body]) => (
                <div key={title} className="panel-raised px-3 py-2 text-[12px]">
                  <span className="font-semibold">{title}</span> <span className="dim">— {body}</span>
                </div>
              ))}
            </div>
          </div>
        </Panel>
      </div>

      <div id="why" className="scroll-mt-24">
        <Panel title="Why · the problem it solves"
          hint="Language models predict the next token, not the next phrase. They have no explicit idea of who does what, to whom, where and why.">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[12.5px]">
              <thead className="faint">
                <tr className="hairline border-b">
                  <th className="py-2 pr-4 font-semibold">Input</th>
                  <th className="py-2 pr-4 font-semibold"><Pill tone="base">LLM prediction</Pill></th>
                  <th className="py-2 font-semibold"><Pill tone="splm">PLM prediction</Pill></th>
                </tr>
              </thead>
              <tbody>
                {WHY_ROWS.map(([input, llm, plm]) => (
                  <tr key={input} className="hairline border-b align-top last:border-0">
                    <td className="py-2 pr-4 font-medium">{input}</td>
                    <td className="dim py-2 pr-4">{llm}</td>
                    <td className="py-2">{plm}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Caveat>
            The hypothesis under test: making the structure explicit, and using it to re-weight candidates, improves
            prediction enough to justify its cost. The project exists to find out, not to assume it.
          </Caveat>
        </Panel>
      </div>

      <div id="so-what" className="scroll-mt-24">
        <Panel title="So what · benefits compared with a plain LLM">
          <div className="grid gap-4 lg:grid-cols-2">
            <ul className="flex flex-col gap-2 text-[12.5px] leading-relaxed">
              {[
                ["A prediction a plain model cannot make", "what kind of meaning comes next, not only which fragment."],
                ["One structure across languages", "English, French and Vietnamese sentences that mean the same give the same frame."],
                ["Explainable", "every adjustment comes with the slot and the evidence behind it."],
                ["Never worse on the suite", "2 wins, 9 ties, 0 losses by rank of the correct answer; ablating everything reproduces the base model."],
                ["Voice that knows what is missing", "spoken requests are sorted into Phrase DNA, so an agent can ask instead of guessing."],
                ["The input to consequence prediction", "text, images and video become the actor, action, object and state that ACM needs."],
              ].map(([title, body]) => (
                <li key={title} className="panel-raised px-3 py-2">
                  <span className="font-semibold text-splm-300">{title}</span> <span className="dim">— {body}</span>
                </li>
              ))}
            </ul>
            <div className="flex flex-col gap-2">
              <p className="eyebrow">Measured (SmolLM2-135M, CPU, 61-item hand-written suite)</p>
              <table className="num w-full text-left text-[12px]">
                <thead className="faint">
                  <tr className="hairline border-b">
                    <th className="py-1.5 pr-3">Metric</th><th className="pr-3">LLM</th><th className="pr-3">PLM</th><th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {RESULTS.map(([metric, base, plm, verdict]) => (
                    <tr key={metric} className="hairline border-b last:border-0">
                      <td className="py-1.5 pr-3">{metric}</td><td className="pr-3">{base}</td>
                      <td className="pr-3 text-splm-300">{plm}</td><td className="faint">{verdict}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Caveat>
                Real measurements of a small model on a small suite, not a benchmark of record. PLM is not yet
                shown to improve next-word prediction on natural text, and it costs about 4× the latency.
              </Caveat>
            </div>
          </div>
        </Panel>
      </div>

      <div id="what-next" className="scroll-mt-24">
        <Panel title="What next · evolution of the model">
          <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
            <ol className="flex flex-col gap-2 text-[12.5px] leading-relaxed">
              <li className="panel-raised px-3 py-2">
                <span className="font-semibold">Now → next release:</span>{" "}
                <span className="dim">evaluate on Universal Dependencies (natural text) at a size that permits a verdict;
                wider gazetteers; cut latency; Speech Lab on real voices.</span>
              </li>
              <li className="panel-raised px-3 py-2">
                <span className="font-semibold">Next:</span>{" "}
                <span className="dim">train the scorer and slot predictor; UniMorph and PropBank importers; real vision;
                dialogue memory for the Speech Lab.</span>
              </li>
              <li className="panel-raised px-3 py-2">
                <span className="font-semibold">Later:</span>{" "}
                <span className="dim">feed role and phrase embeddings into the Transformer; PLM becomes the front end of a full
                Action Prediction Model — PLM understands the action, ACM predicts its consequences and decides.</span>
              </li>
            </ol>
            <div className="flex flex-col gap-2">
              <p className="eyebrow">Follow the evolution</p>
              <Link href="/acm/inference" className="panel-raised px-3 py-2 text-[12.5px] transition-colors hover:bg-white/5">
                <span className="font-semibold text-splm-300">What happens next? →</span>
                <span className="dim block text-[11.5px]">Actions answered with their reasoning (PLM → ACM)</span>
              </Link>
              <Link href="/acm" className="panel-raised px-3 py-2 text-[12.5px] transition-colors hover:bg-white/5">
                <span className="font-semibold text-splm-300">ACM Demo →</span>
                <span className="dim block text-[11.5px]">From meaning to consequences</span>
              </Link>
              <a href={ACM_PROJECT_URL} target="_blank" rel="noopener noreferrer"
                className="panel-raised px-3 py-2 text-[12.5px] transition-colors hover:bg-white/5">
                <span className="font-semibold text-splm-300">Live ACM demo project ↗</span>
                <span className="dim block text-[11.5px]">The Action–Consequence Model, deployed on its own</span>
              </a>
              <a href={`${REPO}#what-next-evolution-of-the-product`} target="_blank" rel="noopener noreferrer"
                className="panel-raised px-3 py-2 text-[12.5px] transition-colors hover:bg-white/5">
                <span className="font-semibold text-splm-300">Full roadmap in the README ↗</span>
                <span className="dim block text-[11.5px]">Now → next → later, and how to build it with us</span>
              </a>
              <Link href="/" className="mt-1 text-[12px] text-splm-300 underline">Try it in the Playground →</Link>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
