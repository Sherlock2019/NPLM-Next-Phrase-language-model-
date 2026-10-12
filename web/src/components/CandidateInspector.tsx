"use client";

import { FEATURE_LABELS, percent, slotLabel } from "@/lib/api";
import type { Candidate } from "@/lib/types";
import { Bar, Empty, Pill } from "./ui";

/**
 * Per-candidate score breakdown (UI spec sections 10, 11, 27).
 *
 * Two honesty rules are visible in the markup:
 *
 * - A feature with no evidence is drawn greyed and labelled "no evidence", not as a
 *   neutral 50% score that looks like a judgement.
 * - A poor fit is described as *less compatible*, never impossible. The scorer
 *   implements no hard rules, so the UI must not imply one.
 */
export function CandidateInspector({
  candidate,
  expectedSlot,
}: {
  candidate: Candidate | null;
  expectedSlot?: string | null;
}) {
  if (!candidate) {
    return <Empty>Select a candidate to see how SPLM scored it.</Empty>;
  }

  const contributions = candidate.contributions.filter((c) => c.enabled);
  const positive = contributions.filter((c) => c.contribution > 0.001);
  const negative = contributions.filter((c) => c.contribution < -0.001);
  const boosted = candidate.delta_logit > 0.01;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-lg font-semibold tracking-tight">
            {candidate.word || candidate.token}
          </div>
          <div className="faint mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
            <span>token id {candidate.token_id}</span>
            <span>
              base #{candidate.base_rank} → SPLM #{candidate.splm_rank}
            </span>
            {candidate.pos_estimate.pos && (
              <span title={candidate.pos_estimate.basis ?? undefined}>
                read as {candidate.pos_estimate.pos}
              </span>
            )}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div
            className={`num text-xl font-semibold leading-none ${
              boosted ? "text-ok-400" : candidate.delta_logit < -0.01 ? "text-danger-400" : "faint"
            }`}
          >
            {candidate.delta_logit > 0 ? "+" : ""}
            {candidate.delta_logit.toFixed(2)}
          </div>
          <div className="faint mt-1 text-[10.5px]">logit adjustment</div>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-2">
        <div className="panel-raised px-2.5 py-2">
          <div className="eyebrow">Base</div>
          <div className="num mt-0.5 text-sm text-base-400">
            {percent(candidate.base_probability, 2)}
          </div>
        </div>
        <div className="panel-raised px-2.5 py-2">
          <div className="eyebrow">SPLM</div>
          <div className="num mt-0.5 text-sm text-splm-300">
            {percent(candidate.splm_probability, 2)}
          </div>
        </div>
      </div>

      {/* Feature scores ------------------------------------------------- */}
      <div className="flex flex-col gap-1.5">
        <h3 className="eyebrow">Feature scores</h3>
        {Object.entries(candidate.features).map(([name, value]) => {
          const informative = candidate.informative[name] ?? false;
          return (
            <div key={name} className="flex items-center gap-2.5">
              <span
                className={`w-32 shrink-0 truncate text-[11px] ${
                  informative ? "dim" : "faint"
                }`}
              >
                {FEATURE_LABELS[name] ?? name}
              </span>
              <Bar
                value={value}
                tone={informative ? (name === "llm" ? "base" : "splm") : "neutral"}
                height={5}
              />
              <span
                className={`num w-20 shrink-0 text-right text-[10.5px] ${
                  informative ? "" : "faint"
                }`}
              >
                {informative ? value.toFixed(2) : "no evidence"}
              </span>
            </div>
          );
        })}
      </div>

      {/* Contribution waterfall ----------------------------------------- */}
      <div className="flex flex-col gap-1.5">
        <h3 className="eyebrow">Contribution to the adjustment</h3>
        {contributions.filter((c) => Math.abs(c.contribution) > 0.001).length === 0 ? (
          <p className="faint text-[11px] leading-snug">
            No feature had evidence about this candidate, so SPLM left its logit
            unchanged. Its ranking here is the base model&apos;s alone.
          </p>
        ) : (
          <Waterfall
            contributions={contributions}
            total={candidate.delta_logit}
            baseLogit={candidate.base_logit}
          />
        )}
      </div>

      {/* Slot compatibility --------------------------------------------- */}
      {Object.keys(candidate.slot_compatibility).length > 0 && (
        <div className="flex flex-col gap-1.5">
          <h3 className="eyebrow">Slot compatibility</h3>
          {Object.entries(candidate.slot_compatibility)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([slot, value]) => (
              <div key={slot} className="flex items-center gap-2.5">
                <span
                  className={`w-32 shrink-0 truncate text-[11px] ${
                    slot === expectedSlot ? "text-warn-400" : "dim"
                  }`}
                >
                  {slotLabel(slot)}
                </span>
                <Bar
                  value={value}
                  tone={slot === expectedSlot ? "warn" : "neutral"}
                  height={5}
                />
                <span className="num w-20 shrink-0 text-right text-[10.5px]">
                  {value.toFixed(2)}
                </span>
              </div>
            ))}
        </div>
      )}

      {/* Reasons -------------------------------------------------------- */}
      <div className="hairline flex flex-col gap-2 border-t pt-3">
        <h3 className="eyebrow">
          {boosted ? "Raised because" : candidate.delta_logit < -0.01 ? "Lowered because" : "Findings"}
        </h3>
        {candidate.reasons.length === 0 ? (
          <p className="faint text-[11px]">
            The scorer recorded no specific finding for this candidate.
          </p>
        ) : (
          <ul className="flex flex-col gap-1">
            {candidate.reasons.map((reason, index) => (
              <li key={index} className="dim flex gap-2 text-[11px] leading-snug">
                <span
                  aria-hidden
                  className={index < positive.length ? "text-ok-400" : "text-warn-400"}
                >
                  ·
                </span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        )}

        {negative.length > 0 && (
          <p className="faint mt-1 text-[11px] leading-snug">
            Lower compatibility means a weaker fit for the expected meaning, not an
            impossible continuation — SPLM applies no hard rules, only scoring.
          </p>
        )}

        <div className="mt-1 flex flex-wrap gap-1.5">
          {candidate.lexical_status && (
            <Pill tone={candidate.lexical_status === "unknown" ? "neutral" : "ok"}>
              lexicon: {candidate.lexical_status.replace(/_/g, " ")}
            </Pill>
          )}
          {candidate.best_slot && (
            <Pill tone="splm">best fit: {slotLabel(candidate.best_slot)}</Pill>
          )}
        </div>
      </div>
    </div>
  );
}

/** Left-to-right waterfall from the base logit to the final SPLM logit. */
function Waterfall({
  contributions,
  total,
  baseLogit,
}: {
  contributions: { feature: string; contribution: number; informative: boolean }[];
  total: number;
  baseLogit: number;
}) {
  const active = contributions.filter((c) => Math.abs(c.contribution) > 0.001);
  const scale = Math.max(...active.map((c) => Math.abs(c.contribution)), 0.001);

  return (
    <div className="flex flex-col gap-1">
      <Row label="Base Transformer" value={baseLogit} scale={Math.max(Math.abs(baseLogit), scale)} tone="base" />
      {active
        .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
        .map((contribution) => (
          <Row
            key={contribution.feature}
            label={FEATURE_LABELS[contribution.feature] ?? contribution.feature}
            value={contribution.contribution}
            scale={scale}
            tone={contribution.contribution > 0 ? "up" : "down"}
          />
        ))}
      <div className="hairline mt-1 flex items-center gap-2.5 border-t pt-1.5">
        <span className="w-32 shrink-0 text-[11px] font-semibold">Final</span>
        <span className="flex-1" />
        <span className="num w-16 shrink-0 text-right text-[11px] font-semibold">
          {(baseLogit + total).toFixed(2)}
        </span>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  scale,
  tone,
}: {
  label: string;
  value: number;
  scale: number;
  tone: "base" | "up" | "down";
}) {
  const width = Math.min(100, (Math.abs(value) / scale) * 100);
  const colors = { base: "bg-base-500", up: "bg-ok-400", down: "bg-danger-400" };
  return (
    <div className="flex items-center gap-2.5">
      <span className="dim w-32 shrink-0 truncate text-[11px]">{label}</span>
      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-white/6">
        <div
          className={`animate-bar absolute inset-y-0 rounded-full ${colors[tone]}`}
          style={
            tone === "down"
              ? { right: "50%", width: `${width / 2}%` }
              : tone === "up"
                ? { left: "50%", width: `${width / 2}%` }
                : { left: 0, width: `${width}%` }
          }
        />
        {tone !== "base" && (
          <div className="absolute inset-y-0 left-1/2 w-px bg-white/20" />
        )}
      </div>
      <span
        className={`num w-16 shrink-0 text-right text-[10.5px] ${
          tone === "up" ? "text-ok-400" : tone === "down" ? "text-danger-400" : "faint"
        }`}
      >
        {value > 0 && tone !== "base" ? "+" : ""}
        {value.toFixed(2)}
      </span>
    </div>
  );
}
