"use client";

import { useCallback, useEffect, useState } from "react";
import { CandidateInspector } from "@/components/CandidateInspector";
import { api, ApiError, FEATURE_LABELS, percent, slotLabel } from "@/lib/api";
import {
  Bar,
  Caveat,
  Empty,
  ErrorBox,
  Loading,
  Panel,
  Pill,
  buttonClass,
  inputClass,
} from "@/components/ui";
import type { Candidate, ComparisonResponse } from "@/lib/types";

const DEFAULT = "John will meet Sarah in";

/**
 * Prediction Inspector: every candidate, every feature, and where the ranking moved.
 */
export default function InspectorPage() {
  const [prompt, setPrompt] = useState(DEFAULT);
  const [target, setTarget] = useState("Paris");
  const [result, setResult] = useState<ComparisonResponse | null>(null);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (text: string, expected: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.compare({
        prompt: text,
        display_k: 40,
        target: expected.trim() || null,
      });
      setResult(data);
      setSelected(data.splm.candidates[0] ?? null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void run(DEFAULT, "Paris");
  }, [run]);

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Prediction">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run(prompt, target);
          }}
          className="flex flex-col gap-3 sm:flex-row"
        >
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
          <button type="submit" className={buttonClass} disabled={loading}>
            {loading ? "Scoring…" : "Inspect"}
          </button>
        </form>
      </Panel>

      {error && <ErrorBox error={error} />}
      {loading && !result && (
        <Panel>
          <Loading />
        </Panel>
      )}

      {result && (
        <>
          {result.target && <TargetPanel result={result} />}

          <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <Panel
              title="All re-scored candidates"
              hint={`Expected slot: ${slotLabel(result.expected_slots.top_slot)}. Click a row for its breakdown.`}
            >
              <CandidateTable
                candidates={result.splm.candidates}
                selected={selected}
                onSelect={setSelected}
                expectedSlot={result.expected_slots.top_slot}
              />
            </Panel>

            <Panel title="Breakdown">
              <CandidateInspector
                candidate={selected}
                expectedSlot={result.expected_slots.top_slot}
              />
            </Panel>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Panel
              title="Rank uplift"
              hint="Candidates whose position moved most under re-scoring."
            >
              <RankUplift result={result} />
            </Panel>

            <Panel
              title="Probability mass by meaning"
              hint="Each candidate grouped by the slot it best fits."
            >
              <MassByCategory result={result} />
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}

function TargetPanel({ result }: { result: ComparisonResponse }) {
  const target = result.target!;
  if (!target.found) {
    return (
      <Panel title="Expected word">
        <p className="text-[11px] leading-relaxed text-warn-400">
          &ldquo;{target.target}&rdquo; was not among the {result.splm.candidates.length}{" "}
          re-scored candidates, so no rank can be reported. MLM only re-scores the
          top-K; a word outside that set is unaffected either way.
        </p>
      </Panel>
    );
  }

  const improvement = target.rank_improvement ?? 0;
  const tone = improvement > 0 ? "ok" : improvement < 0 ? "danger" : "neutral";

  return (
    <Panel title="Expected word">
      <div className="flex flex-wrap items-center gap-6">
        <div>
          <div className="text-lg font-semibold">{target.target}</div>
          <div className="faint mt-0.5 text-[11px]">matched {target.matched_token}</div>
        </div>
        <div className="flex items-center gap-4">
          <div>
            <div className="eyebrow">Base rank</div>
            <div className="num mt-0.5 text-lg text-base-400">#{target.base_rank}</div>
          </div>
          <span aria-hidden className="faint text-lg">
            →
          </span>
          <div>
            <div className="eyebrow">MLM rank</div>
            <div className="num mt-0.5 text-lg text-splm-300">#{target.splm_rank}</div>
          </div>
        </div>
        <div>
          <div className="eyebrow">Movement</div>
          <div className="mt-0.5">
            <Pill tone={tone}>
              {improvement > 0
                ? `up ${improvement}`
                : improvement < 0
                  ? `down ${Math.abs(improvement)}`
                  : "unchanged"}
            </Pill>
          </div>
        </div>
        <div>
          <div className="eyebrow">Score boost</div>
          <div className="num mt-0.5 text-lg">
            {(target.boost_logits ?? 0) > 0 ? "+" : ""}
            {(target.boost_logits ?? 0).toFixed(2)}
            <span className="faint ml-1 text-[11px]">logits</span>
          </div>
        </div>
      </div>
      <Caveat>
        One prompt cannot establish that MLM helps. Aggregate evidence, with sample
        counts and significance, lives on the Benchmark page.
      </Caveat>
    </Panel>
  );
}

function CandidateTable({
  candidates,
  selected,
  onSelect,
  expectedSlot,
}: {
  candidates: Candidate[];
  selected: Candidate | null;
  onSelect: (candidate: Candidate) => void;
  expectedSlot: string;
}) {
  const features = ["llm", "phrase_slot", "grammar", "syntax", "semantic"] as const;

  return (
    <div className="max-h-[30rem] overflow-auto">
      <table className="w-full text-left text-[11px]">
        <thead className="faint sticky top-0 z-10" style={{ background: "var(--panel)" }}>
          <tr className="hairline border-b">
            <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Token</th>
            <th className="px-2 py-1.5 text-right font-semibold uppercase tracking-wide">
              Base
            </th>
            <th className="px-2 py-1.5 text-right font-semibold uppercase tracking-wide">
              MLM
            </th>
            <th className="px-2 py-1.5 text-right font-semibold uppercase tracking-wide">
              Δ
            </th>
            {features.map((feature) => (
              <th
                key={feature}
                className="px-2 py-1.5 text-right font-semibold uppercase tracking-wide"
                title={FEATURE_LABELS[feature]}
              >
                {FEATURE_LABELS[feature].split(" ")[0].slice(0, 6)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => {
            const isSelected = selected?.token_id === candidate.token_id;
            return (
              <tr
                key={candidate.token_id}
                onClick={() => onSelect(candidate)}
                className={`hairline cursor-pointer border-b last:border-0 ${
                  isSelected ? "bg-splm-500/8" : "hover:bg-white/4"
                }`}
              >
                <td className="px-2 py-1">
                  <span className="font-medium">{candidate.word || candidate.token}</span>
                  <span className="faint num ml-1.5">#{candidate.splm_rank}</span>
                </td>
                <td className="num px-2 py-1 text-right text-base-400">
                  {percent(candidate.base_probability, 1)}
                </td>
                <td className="num px-2 py-1 text-right text-splm-300">
                  {percent(candidate.splm_probability, 1)}
                </td>
                <td
                  className={`num px-2 py-1 text-right ${
                    candidate.delta_logit > 0
                      ? "text-ok-400"
                      : candidate.delta_logit < 0
                        ? "text-danger-400"
                        : "faint"
                  }`}
                >
                  {candidate.delta_logit > 0 ? "+" : ""}
                  {candidate.delta_logit.toFixed(2)}
                </td>
                {features.map((feature) => {
                  const informative = candidate.informative[feature];
                  return (
                    <td
                      key={feature}
                      className={`num px-2 py-1 text-right ${informative ? "" : "faint"}`}
                      title={informative ? undefined : "no evidence available"}
                    >
                      {informative ? candidate.features[feature].toFixed(2) : "–"}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RankUplift({ result }: { result: ComparisonResponse }) {
  const changes = result.ranking_changes ?? [];
  if (changes.length === 0) return <Empty>No candidate changed rank.</Empty>;

  const widest = Math.max(...changes.map((change) => Math.abs(change.change)), 1);

  return (
    <div className="flex flex-col gap-1">
      {changes.slice(0, 14).map((change) => (
        <div key={change.token} className="flex items-center gap-2">
          <span className="w-24 shrink-0 truncate text-[11px] font-medium">
            {change.word || change.token}
          </span>
          <span className="num faint w-20 shrink-0 text-[10.5px]">
            #{change.base_rank} → #{change.splm_rank}
          </span>
          <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-white/6">
            <div
              className={`animate-bar absolute inset-y-0 rounded-full ${
                change.change > 0 ? "bg-ok-400" : "bg-danger-400"
              }`}
              style={
                change.change > 0
                  ? { left: "50%", width: `${(change.change / widest) * 50}%` }
                  : { right: "50%", width: `${(Math.abs(change.change) / widest) * 50}%` }
              }
            />
            <div className="absolute inset-y-0 left-1/2 w-px bg-white/20" />
          </div>
          <span
            className={`num w-10 shrink-0 text-right text-[10.5px] ${
              change.change > 0 ? "text-ok-400" : "text-danger-400"
            }`}
          >
            {change.change > 0 ? "+" : ""}
            {change.change}
          </span>
        </div>
      ))}
    </div>
  );
}

function MassByCategory({ result }: { result: ComparisonResponse }) {
  const mass = result.mass_by_category;
  if (!mass) return <Empty>No classification available.</Empty>;

  const slots = Array.from(
    new Set([...Object.keys(mass.base), ...Object.keys(mass.splm)]),
  ).sort((a, b) => (mass.splm[b] ?? 0) - (mass.splm[a] ?? 0));

  return (
    <div className="flex flex-col gap-2">
      {slots.slice(0, 8).map((slot) => (
        <div key={slot} className="flex items-center gap-2.5">
          <span className="dim w-32 shrink-0 truncate text-[11px]">{slotLabel(slot)}</span>
          <div className="flex flex-1 flex-col gap-1">
            <Bar value={mass.base[slot] ?? 0} tone="base" height={5} />
            <Bar value={mass.splm[slot] ?? 0} tone="splm" height={5} />
          </div>
          <span className="num w-24 shrink-0 text-right text-[10.5px]">
            <span className="text-base-400">{percent(mass.base[slot] ?? 0, 0)}</span>
            <span className="faint mx-1">→</span>
            <span className="text-splm-300">{percent(mass.splm[slot] ?? 0, 0)}</span>
          </span>
        </div>
      ))}

      {(mass.unclassified_base > 0 || mass.unclassified_splm > 0) && (
        <Caveat>
          {percent(mass.unclassified_splm, 0)} of MLM&apos;s probability mass sits on
          candidates no slot could be determined for. The classifier runs on seed
          gazetteers, so unclassified means &ldquo;unknown&rdquo;, not
          &ldquo;irrelevant&rdquo;.
        </Caveat>
      )}
    </div>
  );
}
