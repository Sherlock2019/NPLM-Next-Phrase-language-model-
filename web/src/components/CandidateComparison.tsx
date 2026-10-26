"use client";

import { percent } from "@/lib/api";
import type { Candidate } from "@/lib/types";
import { Bar, Empty } from "./ui";

/**
 * Base model versus MLM, side by side (UI spec sections 4, 9).
 *
 * Both columns come from one forward pass, so the difference between them is the
 * re-scoring layer alone. Rank movement is shown per row; clicking a row opens the
 * inspector for that candidate.
 */
export function CandidateComparison({
  base,
  splm,
  selected,
  onSelect,
  limit = 10,
}: {
  base: Candidate[];
  splm: Candidate[];
  selected?: number | null;
  onSelect?: (candidate: Candidate) => void;
  limit?: number;
}) {
  if (base.length === 0) return <Empty>No candidates returned.</Empty>;

  const maxBase = Math.max(...base.map((c) => c.base_probability), 0.0001);
  const maxSplm = Math.max(...splm.map((c) => c.splm_probability), 0.0001);

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Column
        title="Standard LLM"
        subtitle="next-token probability"
        tone="base"
        candidates={base.slice(0, limit)}
        max={maxBase}
        valueOf={(c) => c.base_probability}
        rankOf={(c) => c.base_rank}
        selected={selected}
        onSelect={onSelect}
      />
      <Column
        title="MLM"
        subtitle="phrase-aware, re-scored"
        tone="splm"
        candidates={splm.slice(0, limit)}
        max={maxSplm}
        valueOf={(c) => c.splm_probability}
        rankOf={(c) => c.splm_rank}
        showMovement
        selected={selected}
        onSelect={onSelect}
      />
    </div>
  );
}

function Column({
  title,
  subtitle,
  tone,
  candidates,
  max,
  valueOf,
  rankOf,
  showMovement = false,
  selected,
  onSelect,
}: {
  title: string;
  subtitle: string;
  tone: "base" | "splm";
  candidates: Candidate[];
  max: number;
  valueOf: (c: Candidate) => number;
  rankOf: (c: Candidate) => number;
  showMovement?: boolean;
  selected?: number | null;
  onSelect?: (candidate: Candidate) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <h3
          className={`text-xs font-semibold ${
            tone === "splm" ? "text-splm-300" : "text-base-400"
          }`}
        >
          {title}
        </h3>
        <span className="faint text-[10.5px]">{subtitle}</span>
      </div>

      <div className="flex flex-col">
        {candidates.map((candidate) => {
          const value = valueOf(candidate);
          const isSelected = selected === candidate.token_id;
          return (
            <button
              key={`${candidate.token_id}-${title}`}
              type="button"
              onClick={() => onSelect?.(candidate)}
              className={`animate-rise group flex items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors ${
                isSelected ? "bg-splm-500/10 ring-1 ring-splm-500/30" : "hover:bg-white/4"
              }`}
            >
              <span className="num faint w-6 shrink-0 text-[10.5px]">
                #{rankOf(candidate)}
              </span>

              <span
                className="min-w-0 flex-1 truncate text-xs font-medium"
                title={candidate.token}
              >
                {candidate.word || (
                  <span className="faint italic">
                    {renderInvisible(candidate.token)}
                  </span>
                )}
              </span>

              {showMovement && candidate.rank_change !== 0 && (
                <span
                  className={`num shrink-0 text-[10.5px] font-semibold ${
                    candidate.rank_change > 0 ? "text-ok-400" : "text-danger-400"
                  }`}
                  title={`base #${candidate.base_rank} → MLM #${candidate.splm_rank}`}
                >
                  {candidate.rank_change > 0 ? "↑" : "↓"}
                  {Math.abs(candidate.rank_change)}
                </span>
              )}

              <span className="w-20 shrink-0">
                <Bar value={value / max} tone={tone} height={5} />
              </span>

              <span className="num w-12 shrink-0 text-right text-[11px]">
                {percent(value, 1)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Whitespace and control tokens have no visible word; name them instead. */
function renderInvisible(token: string): string {
  if (token === "Ċ" || token.includes("\n")) return "newline";
  if (token.trim() === "" || token === "Ġ") return "space";
  return token;
}
