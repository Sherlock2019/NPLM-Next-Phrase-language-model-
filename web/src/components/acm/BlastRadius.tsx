"use client";

/**
 * ACM's blast radius: concentric rings from the actor out to the earth.
 *
 * A ring is filled only when ACM reported something there. An empty ring reads
 * "No supporting evidence" - it is never drawn as "no impact". Every row carries
 * its basis as a word (rule-derived, simulated, unknown, generic).
 */

import { useState } from "react";
import type { Ring } from "@/lib/multimodal/types";
import { StatusTag } from "@/components/multimodal/Stages";

const PALETTE = [
  "#f5b942", "#3dd6c6", "#a78bfa", "#bef264", "#86efac",
  "#67e8f9", "#93c5fd", "#c4b5fd", "#60a5fa", "#34d399",
];

export function RingDiagram({ rings, highlight, onPick }: { rings: Ring[]; highlight?: string | null; onPick?: (key: string) => void }) {
  const size = 340;
  const c = size / 2;
  const step = (c - 12) / rings.length;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="mx-auto block w-full max-w-[340px]" role="img" aria-label="Blast radius rings">
      {[...rings].reverse().map((ring, ri) => {
        const i = rings.length - 1 - ri;
        const r = step * (i + 1) + 4;
        const filled = ring.rows.length > 0;
        const active = highlight === ring.key;
        return (
          <g key={ring.key} onClick={() => onPick?.(ring.key)} className="cursor-pointer">
            <circle
              cx={c}
              cy={c}
              r={r}
              fill={filled ? PALETTE[i] : "transparent"}
              fillOpacity={filled ? (active ? 0.55 : 0.28) : 0}
              stroke={active ? "#fff" : filled ? PALETTE[i] : "var(--border)"}
              strokeWidth={active ? 2.5 : 1.2}
              strokeDasharray={filled ? undefined : "3 3"}
            >
              <title>{`${ring.title}: ${filled ? `${ring.rows.length} consequence(s)` : ring.empty}`}</title>
            </circle>
          </g>
        );
      })}
      {rings.map((ring, i) => {
        const r = step * (i + 1) + 4;
        const y = c - r + step / 2 + 3;
        const filled = ring.rows.length > 0;
        return (
          <text
            key={ring.key}
            x={c}
            y={i === 0 ? c + 4 : y}
            textAnchor="middle"
            fontSize={i === 0 ? 10 : 9}
            fontWeight={filled ? 700 : 400}
            fill={filled ? "var(--text)" : "var(--text-faint)"}
            pointerEvents="none"
          >
            {ring.title}
            {filled ? ` · ${ring.rows.length}` : ""}
          </text>
        );
      })}
    </svg>
  );
}

export function BlastRadius({ rings, caption }: { rings: Ring[]; caption?: string }) {
  const [pick, setPick] = useState<string | null>(null);
  const shown = pick ? rings.filter((r) => r.key === pick) : rings;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(240px,340px)_1fr]">
      <div className="flex flex-col gap-2">
        <RingDiagram rings={rings} highlight={pick} onPick={(k) => setPick(pick === k ? null : k)} />
        <p className="faint text-center text-[10.5px]">
          Filled ring = ACM predicted something there · dashed = no supporting evidence. Click a ring to focus it.
        </p>
        {caption && <p className="faint text-center text-[10.5px]">{caption}</p>}
      </div>
      <ol className="flex flex-col gap-1.5">
        {pick && (
          <li>
            <button type="button" className="dim text-[11px] underline" onClick={() => setPick(null)}>
              show all rings
            </button>
          </li>
        )}
        {shown.map((ring) => (
          <li key={ring.key} className="panel-raised px-3 py-2">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-[12.5px] font-semibold">{ring.title}</span>
              {ring.extent && <span className="dim text-[11px]">{ring.extent}</span>}
              {ring.question && <span className="faint text-[10.5px]">— {ring.question}</span>}
            </div>
            {ring.rows.length === 0 ? (
              <p className="faint mt-0.5 text-[11.5px] italic">{ring.empty}</p>
            ) : (
              <ul className="mt-1 flex flex-col gap-1">
                {ring.rows.map((row, i) => (
                  <li key={i} className="flex items-start gap-2 text-[12px] leading-snug">
                    <StatusTag status={row.basis} />
                    <span>
                      <b>{row.about}</b>: {row.text}
                      {row.direction && <span className="dim"> ({row.direction === "+" ? "▲ helps" : row.direction === "-" ? "▼ harms" : "● changes"})</span>}
                      {row.needs && row.needs.length > 0 && <span className="faint"> — would need: {row.needs.join(", ")}</span>}
                      {row.reason && <span className="faint"> — {row.reason}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
