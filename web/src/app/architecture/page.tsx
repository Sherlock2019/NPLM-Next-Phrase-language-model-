"use client";

import { useState } from "react";
import { Panel, Pill } from "@/components/ui";

/**
 * Architecture page: what each stage contributes, and what it does not.
 *
 * The `honest` field on each stage is the point of this page. A diagram that only
 * lists capabilities invites the reader to assume more than the system does, so every
 * stage states its limitation next to its contribution.
 */

interface Stage {
  id: string;
  title: string;
  lane: "input" | "knowledge" | "meaning" | "model" | "output";
  contributes: string;
  answers: string;
  detail: string;
  honest: string;
  module: string;
}

const STAGES: Stage[] = [
  {
    id: "input",
    title: "Input",
    lane: "input",
    answers: "What was written?",
    contributes: "The raw text, unchanged.",
    detail:
      "SPLM never rewrites the prompt. The base model sees exactly the string the user typed, which is what makes the two arms comparable.",
    honest: "No preprocessing means no opportunity to help the model by cleaning input.",
    module: "splm/pipeline.py",
  },
  {
    id: "language",
    title: "Language detector",
    lane: "input",
    answers: "Which language is this?",
    contributes:
      "A language code with a confidence, plus locale and script kept separately.",
    detail:
      "Function words and diacritic signatures, optionally cross-checked against a statistical identifier. Language and locale are never conflated: a fr-FR locale does not make English text French.",
    honest:
      "Short fragments are genuinely hard. Confidence is reported rather than rounded up, and low confidence flows through to everything downstream.",
    module: "splm/language/detector.py",
  },
  {
    id: "lexicon",
    title: "Lexicon",
    lane: "knowledge",
    answers: "What words exist, and what do they mean?",
    contributes: "Per-candidate lookups: possible parts of speech, semantic classes, forms.",
    detail:
      "SQLite, queried one word at a time. The dictionary is never injected into the model's context.",
    honest:
      "Built per language from Wiktionary the first time that language is chosen or detected. Until a language's dictionary has finished loading, every lexical feature reports 'no evidence' and contributes exactly zero rather than guessing.",
    module: "splm/linguistic/lexicon.py",
  },
  {
    id: "morphology",
    title: "Morphology",
    lane: "knowledge",
    answers: "Person, number, tense, gender, case, aspect, mood, polarity?",
    contributes: "Parser features normalised onto one fixed inventory across languages.",
    detail:
      "The same categories are extracted whether the language marks them with an ending, an auxiliary or a particle.",
    honest:
      "Vietnamese has no inflection at all, so its analyses are nearly empty. That is correct, not a failure — and it means morphology contributes nothing there.",
    module: "splm/linguistic/morphology.py",
  },
  {
    id: "grammar",
    title: "Grammar",
    lane: "knowledge",
    answers: "Which forms and constructions are valid?",
    contributes: "Agreement checks, article phonology, which word classes can open a slot.",
    detail: "Read from the language pack; no grammar rule is written in Python.",
    honest:
      "English marks very little, so agreement is often undeterminable. The scorer says so instead of passing the candidate by default.",
    module: "language_packs/<lang>/grammar.yaml",
  },
  {
    id: "syntax",
    title: "Syntax",
    lane: "knowledge",
    answers: "How do the words relate structurally?",
    contributes: "A Universal Dependencies parse, and cues that map relations to roles.",
    detail:
      "Stanza today, behind an interface: nothing downstream knows which parser produced the tree.",
    honest:
      "Parser errors propagate. On fragments especially, attachment is unreliable — and a wrong tree yields a wrong frame with no warning.",
    module: "splm/linguistic/parser.py",
  },
  {
    id: "roles",
    title: "Semantic roles",
    lane: "meaning",
    answers: "What part does each entity play?",
    contributes:
      "A probability distribution over universal roles for every constituent, with its evidence.",
    detail:
      "Roles are predicate-specific: the object of `meet` is a participant, the object of `deploy` is a patient. No fixed ARG0/ARG1 mapping is assumed.",
    honest:
      "Per-verb argument structure is hand-written for a few dozen verbs. Outside those, the generic relation prior does the work and accuracy drops.",
    module: "splm/linguistic/semantic_roles.py",
  },
  {
    id: "phrase",
    title: "Universal Phrase DNA",
    lane: "meaning",
    answers: "What does this sentence represent?",
    contributes:
      "A recursive, language-independent frame: who, does what, to what, where, when, how, why, under what conditions.",
    detail:
      "Stores relationships, never word order. The same frame is reachable from English, French or Vietnamese.",
    honest:
      "Content words stay language-specific. Cross-language comparison is therefore structural only — comparing meanings properly needs a cross-lingual concept inventory this POC does not have.",
    module: "splm/phrase/schema.py",
  },
  {
    id: "context",
    title: "Context graph",
    lane: "meaning",
    answers: "What has happened, who is involved, how do events relate?",
    contributes: "Entities and events across sentences, with pronouns resolved.",
    detail:
      "Built from frames, so it inherits their language independence. Resolution uses grammatical features and recency.",
    honest:
      "Confidence falls when several antecedents fit, and an unresolvable pronoun is left unresolved rather than guessed.",
    module: "splm/graph/context_graph.py",
  },
  {
    id: "slot",
    title: "Expected slot predictor",
    lane: "meaning",
    answers: "What kind of information comes next?",
    contributes:
      "A distribution over semantic slots — the prediction a plain language model does not make.",
    detail:
      "Language-pack priors combined with evidence from a dangling marker and from which slots are already filled. The trainable version learns the same mapping from data.",
    honest:
      "This is where SPLM's distinctive claim lives, and it has no base-model counterpart to compare against — so it is reported as a capability measurement, not as a win.",
    module: "splm/phrase/slot_predictor.py",
  },
  {
    id: "llm",
    title: "Base Transformer",
    lane: "model",
    answers: "Which tokens are statistically likely?",
    contributes: "Top-K candidates with their logits, from one forward pass.",
    detail:
      "Any Hugging Face causal LM; the model id lives in config and is never hard-coded. The same forward pass feeds both arms of every comparison.",
    honest:
      "The standard model is not semantics-free — it encodes meaning implicitly in its hidden states. SPLM adds an explicit representation that can be inspected and measured, which is a different claim from adding semantics.",
    module: "splm/model/base_llm.py",
  },
  {
    id: "scorer",
    title: "Linguistic scorer",
    lane: "model",
    answers: "Which candidates fit the meaning so far?",
    contributes:
      "A per-feature score and a logit adjustment for each candidate, with the reasons recorded.",
    detail:
      "Weighted sum today, a small trained network later, behind one interface. Features centre on neutral, so a feature with no evidence moves nothing.",
    honest:
      "Only the top-K are re-scored, and re-scoring down-ranks rather than removes. Adjustments are capped so a confident base model is not steamrolled.",
    module: "splm/model/candidate_scorer.py",
  },
  {
    id: "output",
    title: "Next token",
    lane: "output",
    answers: "What is actually produced?",
    contributes: "The argmax of the adjusted distribution.",
    detail:
      "Injected into ordinary decoding through a logits processor, so generation is unchanged apart from the scores.",
    honest:
      "The structural layer costs real time — typically a few hundred milliseconds per prediction on CPU, dominated by parsing. The Benchmark page shows the measured cost next to the measured benefit.",
    module: "splm/model/logits_processor.py",
  },
];

const LANES: { id: Stage["lane"]; label: string }[] = [
  { id: "input", label: "Input" },
  { id: "knowledge", label: "Explicit knowledge" },
  { id: "meaning", label: "Meaning" },
  { id: "model", label: "Transformer" },
  { id: "output", label: "Output" },
];

export default function ArchitecturePage() {
  const [selected, setSelected] = useState<Stage>(STAGES[9]);

  return (
    <div className="flex flex-col gap-4">
      <Panel title="The difference in one screen">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="hairline rounded-lg border bg-base-500/5 p-4">
            <h3 className="eyebrow text-base-400">Standard language model</h3>
            <p className="mt-2 text-xs leading-relaxed">
              Which token statistically comes next?
            </p>
            <div className="mt-3 flex flex-col gap-1">
              {["Previous tokens", "Transformer", "Probability over the vocabulary", "Next token"].map(
                (step) => (
                  <div
                    key={step}
                    className="hairline rounded border px-2.5 py-1.5 text-[11px]"
                  >
                    {step}
                  </div>
                ),
              )}
            </div>
          </div>

          <div className="rounded-lg border border-splm-500/25 bg-splm-500/5 p-4">
            <h3 className="eyebrow text-splm-400">Smart Phrase Language Model</h3>
            <p className="mt-2 text-xs leading-relaxed">
              What is happening? What is already known? What meaning is missing? Which
              semantic role comes next? Which candidates satisfy it? Combine that with
              the Transformer&apos;s probability.
            </p>
            <div className="mt-3 flex flex-col gap-1">
              {[
                "Previous tokens",
                "Language, lexicon, grammar, morphology, syntax",
                "Universal Phrase DNA",
                "Context graph",
                "Expected semantic slot",
                "Transformer candidates",
                "Linguistic scoring",
                "Adjusted probabilities",
                "Next token",
              ].map((step, index) => (
                <div
                  key={step}
                  className={`rounded border px-2.5 py-1.5 text-[11px] ${
                    index >= 1 && index <= 4
                      ? "border-splm-500/30 bg-splm-500/10 text-splm-300"
                      : "hairline"
                  }`}
                >
                  {step}
                </div>
              ))}
            </div>
          </div>
        </div>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
        <Panel title="Pipeline" hint="Select a stage to see what it contributes.">
          <div className="flex flex-col gap-3">
            {LANES.map((lane) => (
              <div key={lane.id}>
                <h3 className="eyebrow mb-1.5">{lane.label}</h3>
                <div className="flex flex-wrap gap-1.5">
                  {STAGES.filter((stage) => stage.lane === lane.id).map((stage) => (
                    <button
                      key={stage.id}
                      type="button"
                      onClick={() => setSelected(stage)}
                      className={`rounded-md border px-2.5 py-1.5 text-left text-[11px] font-medium transition-colors ${
                        selected.id === stage.id
                          ? "border-splm-500/50 bg-splm-500/12 text-splm-300"
                          : "hairline hover:bg-white/4"
                      }`}
                    >
                      {stage.title}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title={selected.title}>
          <div className="flex flex-col gap-3">
            <div>
              <h3 className="eyebrow">Answers</h3>
              <p className="mt-1 text-xs leading-relaxed">{selected.answers}</p>
            </div>
            <div>
              <h3 className="eyebrow">Contributes</h3>
              <p className="dim mt-1 text-[11px] leading-relaxed">{selected.contributes}</p>
            </div>
            <div>
              <h3 className="eyebrow">How</h3>
              <p className="dim mt-1 text-[11px] leading-relaxed">{selected.detail}</p>
            </div>
            <div className="rounded-md border border-warn-400/25 bg-warn-400/6 px-2.5 py-2">
              <h3 className="eyebrow text-warn-400">Limitation</h3>
              <p className="mt-1 text-[11px] leading-relaxed text-warn-400">
                {selected.honest}
              </p>
            </div>
            <div>
              <Pill tone="neutral">{selected.module}</Pill>
            </div>
          </div>
        </Panel>
      </div>

      <Panel title="What this project is trying to find out">
        <p className="dim text-xs leading-relaxed">
          Whether explicit linguistic structure helps a Transformer — not whether it
          does. Every component can be switched off, every claim is measured on
          identical input with the same model and hardware, and the cost is reported
          next to the benefit. Where the evidence does not support an improvement, the
          dashboard says &ldquo;no meaningful difference&rdquo; or &ldquo;base model
          better&rdquo;.
        </p>
      </Panel>
    </div>
  );
}
