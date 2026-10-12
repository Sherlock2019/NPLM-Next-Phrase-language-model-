"use client";

import { ms, percent, signedPp, slotLabel } from "@/lib/api";
import type { ComparisonResponse } from "@/lib/types";
import { Stat } from "./ui";

/**
 * The four headline observations for a single prediction, plus its cost.
 *
 * These are per-prediction *observations*, not benchmark results. One prompt cannot
 * establish that SPLM helps, so nothing here is worded as a win — the Benchmark page
 * is where aggregated evidence and significance live.
 */
export function AdvantageCards({ result }: { result: ComparisonResponse }) {
  const focus = result.semantic_focus;
  const target = result.target;
  const search = result.search_space;
  const slots = result.expected_slots;

  const focusImproved = (focus?.delta_percentage_points ?? 0) > 0;
  const rankImproved = (target?.rank_improvement ?? 0) > 0;

  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
      <Stat
        label="Expected slot"
        value={slotLabel(slots.top_slot)}
        tone="warn"
        sub={`${percent(slots.confidence, 0)} · ${slots.confidence_label} confidence`}
      />

      {focus && focus.reportable ? (
        <Stat
          label="Semantic focus"
          value={signedPp(focus.delta_percentage_points)}
          tone={focusImproved ? "ok" : focus.delta_percentage_points < 0 ? "danger" : "neutral"}
          sub={
            <>
              {percent(focus.base_mass, 0)} → {percent(focus.splm_mass, 0)} of probability
              mass on {focus.slot}-compatible candidates
            </>
          }
        />
      ) : (
        <Stat
          label="Semantic focus"
          value="—"
          sub="too few candidates classifiable to report"
        />
      )}

      {target ? (
        target.found ? (
          <Stat
            label="Correct word rank"
            value={
              <>
                #{target.base_rank} → #{target.splm_rank}
              </>
            }
            tone={rankImproved ? "ok" : (target.rank_improvement ?? 0) < 0 ? "danger" : "neutral"}
            sub={
              target.rank_improvement === 0
                ? `"${target.target}" did not move`
                : `"${target.target}" moved ${Math.abs(target.rank_improvement ?? 0)} ${
                    rankImproved ? "up" : "down"
                  }`
            }
          />
        ) : (
          <Stat
            label="Correct word rank"
            value="not found"
            tone="warn"
            sub={`"${target.target}" was not among the re-scored candidates`}
          />
        )
      ) : (
        <Stat
          label="Correct word rank"
          value="—"
          sub="enter an expected continuation to measure rank movement"
        />
      )}

      <Stat
        label="Search space"
        value={search ? `${search.hard_reduction_percent.toFixed(1)}%` : "—"}
        tone="splm"
        sub={
          search
            ? `${search.candidates_considered} of ${search.vocabulary_size.toLocaleString()} tokens re-scored`
            : undefined
        }
      />

      <Stat
        label="SPLM overhead"
        value={ms(result.splm_overhead_ms)}
        tone={result.splm_overhead_ms > result.total_latency_ms / 2 ? "warn" : "neutral"}
        sub={
          <>
            {ms(result.total_latency_ms)} total
            {!result.warm && " · cold call, includes loading"}
          </>
        }
      />
    </div>
  );
}
