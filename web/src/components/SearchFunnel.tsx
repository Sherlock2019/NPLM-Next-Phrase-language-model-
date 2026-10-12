"use client";

import { fullNumber, percent } from "@/lib/api";
import type { SearchSpace, SemanticFocus } from "@/lib/types";
import { Caveat, Empty, Pill } from "./ui";

/**
 * The next-word search funnel (metrics brief sections 2, 13, 19).
 *
 * The critical distinction, enforced by the backend and surfaced here: only stages
 * marked `hard` actually restrict what can be produced. Everything else re-scores
 * candidates without removing them, and is labelled **down-ranked**, not filtered.
 * Calling scoring "filtering" would overstate what this proof of concept does.
 */
export function SearchFunnel({
  search,
  focus,
}: {
  search: SearchSpace | null;
  focus?: SemanticFocus | null;
}) {
  if (!search || search.stages.length === 0) {
    return <Empty>No search-space data for this prediction.</Empty>;
  }

  const widest = Math.max(...search.stages.map((stage) => stage.count));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        {search.stages.map((stage, index) => {
          // Log scale: the vocabulary is three orders of magnitude above the rest,
          // so a linear funnel would collapse every later stage into a hairline.
          const width = Math.max(
            2,
            (Math.log10(stage.count + 1) / Math.log10(widest + 1)) * 100,
          );
          return (
            <div key={`${stage.name}-${index}`} className="group">
              <div className="flex items-baseline gap-2">
                <span className="num w-20 shrink-0 text-right text-[11px] font-medium">
                  {fullNumber(stage.count)}
                </span>
                <div className="min-w-0 flex-1">
                  <div
                    className={`animate-bar h-5 rounded-sm ${
                      stage.hard
                        ? "bg-splm-500/55"
                        : "bg-white/10 ring-1 ring-inset ring-white/10"
                    }`}
                    style={{ width: `${width}%` }}
                  />
                </div>
              </div>
              <div className="ml-[5.5rem] mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span className="text-[11px] font-medium">{stage.name}</span>
                <Pill tone={stage.hard ? "splm" : "neutral"}>{stage.label}</Pill>
                {stage.note && (
                  <span className="faint text-[10.5px] leading-snug">{stage.note}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="hairline grid gap-2 border-t pt-3 sm:grid-cols-2">
        <div className="panel-raised px-3 py-2">
          <div className="eyebrow">Output space actually restricted</div>
          <div className="num mt-0.5 text-lg font-semibold text-splm-300">
            {search.hard_reduction_percent.toFixed(1)}%
          </div>
          <div className="faint mt-1 text-[10.5px] leading-snug">
            {fullNumber(search.vocabulary_size)} tokens →{" "}
            {fullNumber(search.candidates_considered)} re-scored. A token outside the
            retrieved set keeps its original logit and so cannot be selected, which
            makes this a genuine restriction.
          </div>
        </div>

        {focus && focus.reportable ? (
          <div className="panel-raised px-3 py-2">
            <div className="eyebrow">Semantic focus on {focus.slot}</div>
            <div className="num mt-0.5 flex items-baseline gap-2 text-lg font-semibold">
              <span className="text-base-400">{percent(focus.base_mass, 0)}</span>
              <span aria-hidden className="faint text-sm">
                →
              </span>
              <span className="text-splm-300">{percent(focus.splm_mass, 0)}</span>
            </div>
            <div className="faint mt-1 text-[10.5px] leading-snug">
              probability mass on candidates compatible with the expected slot
              {focus.delta_percentage_points !== 0 && (
                <>
                  {" "}
                  (
                  <span
                    className={
                      focus.delta_percentage_points > 0 ? "text-ok-400" : "text-danger-400"
                    }
                  >
                    {focus.delta_percentage_points > 0 ? "+" : ""}
                    {focus.delta_percentage_points.toFixed(1)} pp
                  </span>
                  )
                </>
              )}
            </div>
          </div>
        ) : (
          <div className="panel-raised px-3 py-2">
            <div className="eyebrow">Semantic focus</div>
            <div className="faint mt-1 text-[11px] leading-snug">
              Not reportable for this prediction: too few candidates could be classified
              against the expected slot.
            </div>
          </div>
        )}
      </div>

      <Caveat>
        Stages after retrieval re-score candidates; they do not remove them. This is
        semantic down-ranking, not filtering — a candidate SPLM scores poorly can still
        be selected if the base model is confident enough.
      </Caveat>

      {focus?.coverage_note && <Caveat>{focus.coverage_note}.</Caveat>}
    </div>
  );
}
