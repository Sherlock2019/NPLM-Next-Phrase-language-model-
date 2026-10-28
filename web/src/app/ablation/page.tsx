"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, percent, slotLabel } from "@/lib/api";
import {
  Bar,
  Caveat,
  Empty,
  ErrorBox,
  Loading,
  Panel,
  Pill,
  Toggle,
  buttonClass,
  buttonGhostClass,
  inputClass,
} from "@/components/ui";
import type { AblationRun } from "@/lib/types";

const FEATURES: { key: string; label: string; hint: string }[] = [
  { key: "lexicon", label: "Dictionary", hint: "Is the candidate a possible word?" },
  { key: "morphology", label: "Morphology", hint: "Person, number, tense, agreement" },
  { key: "grammar", label: "Grammar", hint: "Valid forms and constructions" },
  { key: "syntax", label: "Syntax", hint: "Can it continue the structure?" },
  { key: "semantics", label: "Semantic roles", hint: "Does it fit the role?" },
  { key: "phrase_structure", label: "Phrase DNA", hint: "Does it fit the expected slot?" },
  { key: "context_graph", label: "Context graph", hint: "Consistent with the discourse?" },
  { key: "style", label: "Style", hint: "Right register?" },
];

const DEFAULT_PROMPT = "John will meet Sarah in";

/**
 * Ablation Lab: which components actually contribute (spec section 39).
 *
 * The cumulative ladder is the one that answers the research question. The manual
 * switches are for probing a single feature.
 */
export default function AblationPage() {
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [target, setTarget] = useState("Paris");
  const [features, setFeatures] = useState<Record<string, boolean>>(
    Object.fromEntries(FEATURES.map((feature) => [feature.key, true])),
  );
  const [runs, setRuns] = useState<AblationRun[]>([]);
  const [expectedSlot, setExpectedSlot] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (options: { cumulative: boolean; custom?: Record<string, boolean> }) => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.ablation({
          prompt,
          target: target.trim() || null,
          display_k: 8,
          cumulative: options.cumulative,
          features: options.cumulative ? undefined : options.custom,
        });
        setRuns(data.runs);
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : String(cause));
        setRuns([]);
      } finally {
        setLoading(false);
      }
    },
    [prompt, target],
  );

  useEffect(() => {
    // Also fetch the expected slot so the ladder can be read in context.
    api
      .compare({ prompt: DEFAULT_PROMPT, display_k: 1 })
      .then((data) => setExpectedSlot(data.expected_slots.top_slot))
      .catch(() => setExpectedSlot(null));
    void run({ cumulative: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <section className="panel flex flex-col gap-2 p-4" aria-label="What this page is for">
        <h1 className="text-[17px] font-semibold">What is the Ablation page for?</h1>
        <p className="text-[13px] leading-relaxed">
          It checks <b>which parts of MLM actually help</b>. MLM sits on top of a small language model and re-scores its next-word
          guesses with layers of linguistic knowledge: the Phrase DNA slot it expects next (WHO, WHERE, WHEN…), grammar, syntax,
          morphology, semantic roles, the lexicon, style and context. “Ablation” means switching those layers off, one at a time or
          cumulatively, and comparing the results on the <b>same prompt, same model and same forward pass</b>, so any difference comes
          from the layer alone.
        </p>
        <ul className="dim flex list-disc flex-col gap-0.5 pl-5 text-[12.5px] leading-snug">
          <li><b>The ladder</b> (default): language model only → + grammar → + syntax → + Phrase DNA → + Phrase DNA and grammar → everything.
            Read it top to bottom: where does the expected word (e.g. “Paris” after “John will meet Sarah in”) start ranking higher?</li>
          <li><b>Manual switches</b>: turn single features on or off to probe one of them.</li>
          <li>If a layer changes nothing, the page shows that too: MLM is a hypothesis under test, and this is where it is tested.</li>
        </ul>
        <p className="faint text-[11.5px]">
          ARM does not need this page: ARM uses MLM&apos;s meaning (Phrase DNA), not its next-word predictions. It is kept for checking MLM itself.
        </p>
      </section>
      <Panel
        title="Ablation"
        hint="Same prompt, same model, same forward pass — only the scoring layers differ."
      >
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              className={`${inputClass} font-mono sm:flex-1`}
              spellCheck={false}
            />
            <input
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              placeholder="expected word"
              className={`${inputClass} sm:w-44`}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={buttonClass}
              disabled={loading}
              onClick={() => void run({ cumulative: true })}
            >
              Run the ladder
            </button>
            <button
              type="button"
              className={buttonGhostClass}
              disabled={loading}
              onClick={() => void run({ cumulative: false, custom: features })}
            >
              Run this configuration
            </button>
            {expectedSlot && (
              <span className="ml-auto self-center">
                <Pill tone="warn">expected slot: {slotLabel(expectedSlot)}</Pill>
              </span>
            )}
          </div>

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((feature) => (
              <Toggle
                key={feature.key}
                checked={features[feature.key] ?? true}
                onChange={(next) =>
                  setFeatures((current) => ({ ...current, [feature.key]: next }))
                }
                label={feature.label}
                hint={feature.hint}
              />
            ))}
          </div>
        </div>
      </Panel>

      {error && <ErrorBox error={error} />}
      {loading && <Panel><Loading label="Running configurations" /></Panel>}

      {runs.length > 0 && !loading && (
        <>
          <Panel
            title="Contribution by configuration"
            hint="What each layer adds, measured on this prompt."
          >
            <LadderTable runs={runs} target={target} />
            <Caveat>
              One prompt. Whether a layer helps in general is a benchmark question, not
              something a single example can settle — see the Benchmark page.
            </Caveat>
          </Panel>

          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {runs.map((entry) => (
              <Panel key={entry.label} title={entry.label}>
                <RunDetail run={entry} />
              </Panel>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function LadderTable({ runs, target }: { runs: AblationRun[]; target: string }) {
  const hasTarget = runs.some((entry) => entry.target?.found);
  const maxProbability = Math.max(
    ...runs.map((entry) => entry.top_probability ?? 0),
    0.0001,
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]">
        <thead className="faint">
          <tr className="hairline border-b">
            <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Configuration</th>
            <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Top choice</th>
            <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Confidence</th>
            {hasTarget && (
              <>
                <th className="px-2 py-1.5 text-right font-semibold uppercase tracking-wide">
                  {target || "target"} rank
                </th>
                <th className="px-2 py-1.5 text-right font-semibold uppercase tracking-wide">
                  boost
                </th>
              </>
            )}
            <th className="px-2 py-1.5 text-right font-semibold uppercase tracking-wide">
              Focus
            </th>
            <th className="px-2 py-1.5 text-right font-semibold uppercase tracking-wide">
              Latency
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((entry) => (
            <tr key={entry.label} className="hairline border-b last:border-0">
              <td className="px-2 py-1.5 font-medium">{entry.label}</td>
              <td className="px-2 py-1.5">{entry.top_token ?? "—"}</td>
              <td className="px-2 py-1.5">
                <div className="flex items-center gap-2">
                  <span className="w-20">
                    <Bar
                      value={(entry.top_probability ?? 0) / maxProbability}
                      tone="splm"
                      height={5}
                    />
                  </span>
                  <span className="num">{percent(entry.top_probability, 1)}</span>
                </div>
              </td>
              {hasTarget && (
                <>
                  <td className="num px-2 py-1.5 text-right">
                    {entry.target?.found ? `#${entry.target.splm_rank}` : "—"}
                  </td>
                  <td className="num px-2 py-1.5 text-right">
                    {entry.target?.boost_logits !== null &&
                    entry.target?.boost_logits !== undefined
                      ? `${entry.target.boost_logits > 0 ? "+" : ""}${entry.target.boost_logits.toFixed(2)}`
                      : "—"}
                  </td>
                </>
              )}
              <td className="num px-2 py-1.5 text-right">
                {entry.semantic_focus
                  ? percent(entry.semantic_focus.splm_mass, 0)
                  : "—"}
              </td>
              <td className="num px-2 py-1.5 text-right">
                {entry.latency_ms.toFixed(0)} ms
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunDetail({ run }: { run: AblationRun }) {
  const enabled = Object.entries(run.features).filter(([, value]) => value);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1">
        {enabled.length === 0 ? (
          <Pill tone="base">base model only</Pill>
        ) : (
          enabled.map(([key]) => (
            <Pill key={key} tone="splm">
              {key.replace(/_/g, " ")}
            </Pill>
          ))
        )}
      </div>

      {run.candidates.length === 0 ? (
        <Empty>No candidates.</Empty>
      ) : (
        <div className="flex flex-col gap-1">
          {run.candidates.slice(0, 6).map((candidate) => (
            <div key={candidate.token} className="flex items-center gap-2">
              <span className="num faint w-6 shrink-0 text-[10.5px]">
                #{candidate.splm_rank}
              </span>
              <span className="min-w-0 flex-1 truncate text-[11px]">
                {candidate.word || candidate.token}
              </span>
              {candidate.base_rank !== candidate.splm_rank && (
                <span
                  className={`num shrink-0 text-[10px] ${
                    candidate.base_rank > candidate.splm_rank
                      ? "text-ok-400"
                      : "text-danger-400"
                  }`}
                >
                  {candidate.base_rank > candidate.splm_rank ? "↑" : "↓"}
                  {Math.abs(candidate.base_rank - candidate.splm_rank)}
                </span>
              )}
              <span className="num w-12 shrink-0 text-right text-[10.5px]">
                {percent(candidate.probability, 1)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
