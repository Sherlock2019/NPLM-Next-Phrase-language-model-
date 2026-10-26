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
  Stat,
  buttonClass,
  buttonGhostClass,
} from "@/components/ui";
import type { BenchmarkReport, BenchmarkSummary, MetricSummary } from "@/lib/types";

const VERDICTS: Record<string, { label: string; tone: "ok" | "neutral" | "danger" | "warn" }> = {
  splm_improved: { label: "MLM improved", tone: "ok" },
  no_meaningful_difference: { label: "No meaningful difference", tone: "neutral" },
  base_better: { label: "Base model better", tone: "danger" },
  insufficient_data: { label: "Insufficient data", tone: "warn" },
};

/**
 * Benchmark dashboard.
 *
 * The scientific-integrity rules of the brief are enforced here rather than left to
 * the reader: a four-state verdict computed from the interval and a paired test, a
 * sample count next to every figure, cost shown alongside benefit, and the run's own
 * caveats printed above its results instead of below them.
 */
export default function BenchmarkPage() {
  const [runs, setRuns] = useState<BenchmarkSummary[]>([]);
  const [report, setReport] = useState<BenchmarkReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [slotFilter, setSlotFilter] = useState<string>("all");

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.benchmarkResults();
      setRuns(data.results);
      if (data.results.length > 0) {
        setReport(await api.benchmarkResult(data.results[0].run_id));
      }
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  async function runBenchmark() {
    setRunning(true);
    setError(null);
    try {
      const fresh = await api.runBenchmark({ suite: "all" });
      setReport(fresh);
      await loadRuns();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setRunning(false);
    }
  }

  if (loading) {
    return (
      <Panel>
        <Loading label="Loading benchmark runs" />
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title="Benchmark runs"
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              className={buttonClass}
              onClick={() => void runBenchmark()}
              disabled={running}
            >
              {running ? "Running…" : "Run benchmark"}
            </button>
            <button type="button" className={buttonGhostClass} onClick={() => void loadRuns()}>
              Refresh
            </button>
          </div>
        }
      >
        {runs.length === 0 ? (
          <Empty>
            No benchmark runs yet. Run one here, or from the command line with{" "}
            <code className="num">python scripts/benchmark.py</code>. Nothing is shown
            until real results exist.
          </Empty>
        ) : (
          <div className="flex flex-col gap-1">
            {runs.slice(0, 8).map((summary) => (
              <button
                key={summary.run_id}
                type="button"
                onClick={() =>
                  void api.benchmarkResult(summary.run_id).then(setReport).catch(() => {})
                }
                className={`flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-md px-2 py-1.5 text-left text-[11px] transition-colors ${
                  report?.run_id === summary.run_id
                    ? "bg-splm-500/10 ring-1 ring-splm-500/30"
                    : "hover:bg-white/4"
                }`}
              >
                <span className="num font-medium">{summary.run_id}</span>
                <span className="faint">{summary.model}</span>
                <span className="faint">{summary.samples} samples</span>
                <span className="faint">{summary.dataset}</span>
                <span className="faint ml-auto num">{summary.fingerprint}</span>
              </button>
            ))}
          </div>
        )}
      </Panel>

      {error && <ErrorBox error={error} />}
      {running && (
        <Panel>
          <Loading label="Running every item through both systems" />
        </Panel>
      )}

      {report && (
        <>
          <Panel title="Run" hint={`${report.dataset} · ${report.samples} samples · ${report.skipped} skipped`}>
            <div className="flex flex-col gap-3">
              <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
                {(
                  [
                    ["Model", String(report.model.model_id ?? "—")],
                    ["Device", `${report.model.device ?? "—"} · ${report.model.dtype ?? "—"}`],
                    ["Languages", report.languages.join(", ")],
                    ["Fingerprint", report.fingerprint],
                    ["Timestamp", report.timestamp],
                    [
                      "Slot data coverage",
                      Object.entries(report.semantics_coverage)
                        .map(([code, level]) => `${code}: ${level}`)
                        .join(", "),
                    ],
                  ] as [string, string][]
                ).map(([label, value]) => (
                  <div key={label} className="flex items-baseline justify-between gap-2">
                    <dt className="faint text-[11px]">{label}</dt>
                    <dd className="num truncate text-[11px]" title={value}>
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>

              {report.caveats.length > 0 && (
                <div className="rounded-lg border border-warn-400/25 bg-warn-400/6 p-3">
                  <h3 className="eyebrow mb-1.5 text-warn-400">
                    Read these before the numbers
                  </h3>
                  <ul className="flex flex-col gap-1.5">
                    {report.caveats.map((caveat, index) => (
                      <li key={index} className="text-[11px] leading-snug text-warn-400">
                        {caveat}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </Panel>

          {/* Scorecard ------------------------------------------------- */}
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {report.slot_accuracy && (
              <Stat
                label="Expected slot accuracy"
                value={`${report.slot_accuracy.percent.toFixed(1)}%`}
                tone="splm"
                sub={`${report.slot_accuracy.successes}/${report.slot_accuracy.total} · MLM-only, no base equivalent`}
              />
            )}
            {report.slot_accuracy_top3 && (
              <Stat
                label="Slot accuracy (top-3)"
                value={`${report.slot_accuracy_top3.percent.toFixed(1)}%`}
                sub="reasonable ambiguity not scored as failure"
              />
            )}
            {report.comparisons.map((comparison) => (
              <Stat
                key={comparison.metric}
                label={comparison.metric}
                value={
                  <span className="flex items-baseline gap-1.5">
                    <span className="text-base-400">{comparison.base.percent}%</span>
                    <span aria-hidden className="faint text-sm">
                      →
                    </span>
                    <span className="text-splm-300">{comparison.splm.percent}%</span>
                  </span>
                }
                tone={
                  VERDICTS[comparison.verdict]?.tone === "ok"
                    ? "ok"
                    : VERDICTS[comparison.verdict]?.tone === "danger"
                      ? "danger"
                      : "neutral"
                }
                sub={`${comparison.difference_pp > 0 ? "+" : ""}${comparison.difference_pp} pp · n=${comparison.splm.total}`}
              />
            ))}
            {report.continuous.map((entry) => (
              <Stat
                key={String(entry.metric)}
                label={String(entry.metric)}
                value={
                  <span className="flex items-baseline gap-1.5">
                    <span className="text-base-400">
                      {Number(entry.base_mean).toFixed(entry.unit === "ms" ? 0 : 2)}
                    </span>
                    <span aria-hidden className="faint text-sm">
                      →
                    </span>
                    <span
                      className={
                        entry.improved ? "text-splm-300" : "text-warn-400"
                      }
                    >
                      {Number(entry.splm_mean).toFixed(entry.unit === "ms" ? 0 : 2)}
                    </span>
                  </span>
                }
                tone={entry.improved ? "ok" : "warn"}
                sub={`${String(entry.unit)} · ${entry.lower_is_better ? "lower" : "higher"} is better · n=${entry.samples}`}
              />
            ))}
          </div>

          {/* Verdicts --------------------------------------------------- */}
          {report.comparisons.length > 0 && (
            <Panel
              title="Base model vs MLM"
              hint="Verdicts come from the confidence interval and a paired test, not from the point estimate."
            >
              <div className="flex flex-col gap-3">
                {report.comparisons.map((comparison) => (
                  <ComparisonRow key={comparison.metric} comparison={comparison} />
                ))}
              </div>
            </Panel>
          )}

          {/* Slot accuracy by category ---------------------------------- */}
          {Object.keys(report.slot_by_category).length > 0 && (
            <Panel
              title="Expected slot accuracy by slot"
              hint="Where the semantic layer works and where it does not."
            >
              <div className="flex flex-col gap-1.5">
                {Object.entries(report.slot_by_category)
                  .sort((a, b) => b[1].percent - a[1].percent)
                  .map(([slot, stats]) => (
                    <div key={slot} className="flex items-center gap-2.5">
                      <span className="dim w-32 shrink-0 truncate text-[11px]">
                        {slotLabel(slot)}
                      </span>
                      <Bar
                        value={stats.percent / 100}
                        tone={stats.percent >= 70 ? "splm" : stats.percent >= 40 ? "warn" : "neutral"}
                      />
                      <span className="num w-24 shrink-0 text-right text-[10.5px]">
                        {stats.percent.toFixed(0)}%
                        <span className="faint ml-1">
                          ({stats.successes}/{stats.total})
                        </span>
                      </span>
                    </div>
                  ))}
              </div>
              <Caveat>
                Small per-slot samples. A slot with two or three items cannot support a
                conclusion on its own — the counts are shown so that is visible.
              </Caveat>
            </Panel>
          )}

          {/* Confusions ------------------------------------------------- */}
          {(report.slot_confusion?.common_errors ?? []).length > 0 && (
            <Panel title="Most common slot confusions">
              <div className="flex flex-col gap-1">
                {(report.slot_confusion.common_errors ?? []).map((error, index) => (
                  <div key={index} className="flex items-center gap-2 text-[11px]">
                    <span className="w-32 shrink-0 truncate">{slotLabel(error.true)}</span>
                    <span aria-hidden className="faint">
                      →
                    </span>
                    <span className="w-32 shrink-0 truncate text-warn-400">
                      {slotLabel(error.predicted)}
                    </span>
                    <span className="num faint">x{error.count}</span>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {/* Cross-language -------------------------------------------- */}
          {(report.multilingual as { mean_agreement?: Record<string, number> })
            ?.mean_agreement && (
            <Panel
              title="Cross-language structural consistency"
              hint={String(
                (report.multilingual as { metric_note?: string }).metric_note ?? "",
              )}
            >
              <div className="flex flex-col gap-2">
                {Object.entries(
                  (report.multilingual as { mean_agreement: Record<string, number> })
                    .mean_agreement,
                ).map(([pair, value]) => (
                  <div key={pair} className="flex items-center gap-3">
                    <span className="w-24 shrink-0 text-[11px] font-medium">{pair}</span>
                    <Bar value={value} tone={value >= 0.8 ? "splm" : "warn"} />
                    <span className="num w-14 shrink-0 text-right text-[11px]">
                      {percent(value, 0)}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {/* Per-item browser ------------------------------------------ */}
          <Panel
            title="Individual tests"
            hint="Including the ones MLM gets wrong."
            actions={
              <select
                value={slotFilter}
                onChange={(event) => setSlotFilter(event.target.value)}
                className="hairline rounded border bg-[var(--panel-raised)] px-2 py-1 text-[11px]"
              >
                <option value="all">All slots</option>
                {Object.keys(report.slot_by_category).map((slot) => (
                  <option key={slot} value={slot}>
                    {slotLabel(slot)}
                  </option>
                ))}
                <option value="errors">Slot mispredictions only</option>
              </select>
            }
          >
            <ItemTable items={report.items} filter={slotFilter} />
          </Panel>

          <Panel title="Headline">
            <ul className="flex flex-col gap-1.5">
              {report.headline.map((statement, index) => (
                <li key={index} className="dim text-[11px] leading-relaxed">
                  {statement}
                </li>
              ))}
            </ul>
          </Panel>
        </>
      )}
    </div>
  );
}

function ComparisonRow({ comparison }: { comparison: MetricSummary }) {
  const verdict = VERDICTS[comparison.verdict] ?? {
    label: comparison.verdict,
    tone: "neutral" as const,
  };

  return (
    <div className="panel-raised p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold">{comparison.metric}</h3>
        <Pill tone={verdict.tone}>{verdict.label}</Pill>
      </div>

      <div className="mt-2 flex flex-col gap-1.5">
        <ArmBar label="Base" stats={comparison.base} tone="base" />
        <ArmBar label="MLM" stats={comparison.splm} tone="splm" />
      </div>

      <p className="dim mt-2 text-[11px] leading-relaxed">{comparison.statement}</p>

      <dl className="faint mt-2 flex flex-wrap gap-x-4 gap-y-0.5 text-[10.5px]">
        <span>
          samples <span className="num">{comparison.splm.total}</span>
        </span>
        <span>
          disagreements{" "}
          <span className="num">
            {comparison.base_only_correct}/{comparison.splm_only_correct}
          </span>
        </span>
        <span>
          p{" "}
          <span className="num">
            {comparison.p_value === null ? "n/a" : comparison.p_value.toFixed(3)}
          </span>
        </span>
        <span>intervals {comparison.intervals_overlap ? "overlap" : "separate"}</span>
      </dl>
    </div>
  );
}

function ArmBar({
  label,
  stats,
  tone,
}: {
  label: string;
  stats: Record<string, number>;
  tone: "base" | "splm";
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="dim w-10 shrink-0 text-[11px]">{label}</span>
      <div className="relative flex-1">
        <Bar value={stats.value} tone={tone} />
        {/* Confidence interval, drawn as a bracket over the bar. */}
        <div
          className="absolute -top-0.5 h-[9px] border-x border-white/40"
          style={{
            left: `${stats.ci_low * 100}%`,
            width: `${Math.max(0.5, (stats.ci_high - stats.ci_low) * 100)}%`,
          }}
          title={`95% CI ${(stats.ci_low * 100).toFixed(1)}–${(stats.ci_high * 100).toFixed(1)}%`}
        />
      </div>
      <span className="num w-28 shrink-0 text-right text-[10.5px]">
        {stats.percent.toFixed(1)}%
        <span className="faint ml-1">
          ±{(((stats.ci_high - stats.ci_low) / 2) * 100).toFixed(1)}
        </span>
      </span>
    </div>
  );
}

function ItemTable({
  items,
  filter,
}: {
  items: Record<string, unknown>[];
  filter: string;
}) {
  const filtered = items.filter((item) => {
    if (filter === "all") return true;
    if (filter === "errors") return item.slot_correct === false;
    return item.expected_slot === filter;
  });

  if (filtered.length === 0) return <Empty>No matching tests.</Empty>;

  return (
    <div className="max-h-[28rem] overflow-auto">
      <table className="w-full text-left text-[11px]">
        <thead className="faint sticky top-0" style={{ background: "var(--panel)" }}>
          <tr className="hairline border-b">
            {["id", "lang", "prompt", "expected slot", "predicted", "target", "base", "splm"].map(
              (head) => (
                <th key={head} className="px-2 py-1.5 font-semibold uppercase tracking-wide">
                  {head}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {filtered.map((item, index) => {
            const slotCorrect = item.slot_correct as boolean | null;
            const baseCorrect = item.base_correct as boolean | null;
            const splmCorrect = item.splm_correct as boolean | null;
            return (
              <tr key={index} className="hairline border-b last:border-0">
                <td className="faint num px-2 py-1">{String(item.id)}</td>
                <td className="faint px-2 py-1">{String(item.language)}</td>
                <td className="max-w-[18rem] truncate px-2 py-1" title={String(item.prompt)}>
                  {String(item.prompt)}
                </td>
                <td className="px-2 py-1">
                  {item.expected_slot ? slotLabel(String(item.expected_slot)) : "—"}
                </td>
                <td
                  className={`px-2 py-1 ${
                    slotCorrect === false ? "text-danger-400" : slotCorrect ? "text-ok-400" : "faint"
                  }`}
                >
                  {item.predicted_slot ? slotLabel(String(item.predicted_slot)) : "—"}
                  {item.slot_confidence !== null && item.slot_confidence !== undefined && (
                    <span className="faint num ml-1">
                      {(Number(item.slot_confidence) * 100).toFixed(0)}%
                    </span>
                  )}
                </td>
                <td className="px-2 py-1">{item.target ? String(item.target) : "—"}</td>
                <td
                  className={`px-2 py-1 ${
                    baseCorrect === true ? "text-ok-400" : baseCorrect === false ? "text-danger-400" : "faint"
                  }`}
                >
                  {item.base_top ? String(item.base_top) : "—"}
                </td>
                <td
                  className={`px-2 py-1 ${
                    splmCorrect === true ? "text-ok-400" : splmCorrect === false ? "text-danger-400" : "faint"
                  }`}
                >
                  {item.splm_top ? String(item.splm_top) : "—"}
                  {item.target_base_rank !== null &&
                    item.target_splm_rank !== null &&
                    item.target_base_rank !== undefined && (
                      <span className="faint num ml-1">
                        #{String(item.target_base_rank)}→#{String(item.target_splm_rank)}
                      </span>
                    )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
