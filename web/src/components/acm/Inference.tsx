"use client";

/** Pieces of the inference explorer: answers, reasoning chain, who-is-affected graph. */

import { useEffect, useState } from "react";
import type { InferenceAnswer, InferenceItem } from "@/lib/multimodal/types";

const KIND_STYLE: Record<string, { label: string; tone: string }> = {
  actor: { label: "actor", tone: "text-amber-300 ring-amber-400/30 bg-amber-400/10" },
  impacted: { label: "impacted", tone: "text-teal-300 ring-teal-400/30 bg-teal-400/10" },
  goal: { label: "someone's goal", tone: "text-violet-300 ring-violet-400/30 bg-violet-400/10" },
  place: { label: "place", tone: "text-lime-300 ring-lime-400/30 bg-lime-400/10" },
  layer: { label: "wider layer", tone: "text-sky-300 ring-sky-400/30 bg-sky-400/10" },
  limits: { label: "limits", tone: "text-[var(--text-dim)] ring-white/15 bg-white/5" },
  negated: { label: "negated", tone: "text-warn-400 ring-warn-400/30 bg-warn-400/10" },
  state: { label: "state", tone: "text-warn-400 ring-warn-400/30 bg-warn-400/10" },
  none: { label: "none", tone: "text-[var(--text-dim)] ring-white/15 bg-white/5" },
};

const STATUS_COLOUR: Record<string, string> = {
  advanced: "#58c07a", enabled: "#58c07a", blocked: "#e0685f", at_risk: "#e0a94a",
  hindered: "#e0a94a", unaffected: "#737d8f", no_evidence: "#737d8f",
};

/** Types out an answer once, the way the demo "speaks" it; respects reduced motion. */
function Typed({ text, play }: { text: string; play: boolean }) {
  const [n, setN] = useState(play ? 0 : text.length);
  useEffect(() => {
    if (!play || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setN(text.length);
      return;
    }
    setN(0);
    const id = window.setInterval(() => setN((v) => (v >= text.length ? (window.clearInterval(id), v) : v + 3)), 16);
    return () => window.clearInterval(id);
  }, [text, play]);
  return <span>{text.slice(0, n)}{n < text.length && <span className="animate-pulse-soft">▍</span>}</span>;
}

export function AnswerCard({ qa, open, onToggle, typing }: { qa: InferenceAnswer; open: boolean; onToggle: () => void; typing: boolean }) {
  const style = KIND_STYLE[qa.kind] ?? KIND_STYLE.none;
  return (
    <li className="panel-raised">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-white/4">
        <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ring-1 ring-inset ${style.tone}`}>
          {style.label}
        </span>
        <span className="flex-1 text-[13px] font-medium">{qa.question}</span>
        <span aria-hidden className="faint">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="hairline border-t px-3 py-2">
          <p className="text-[13.5px] leading-relaxed" style={qa.status ? { color: STATUS_COLOUR[qa.status] } : undefined}>
            <Typed text={qa.answer} play={typing} />
          </p>
          {qa.why.length > 0 && (
            <details className="mt-1.5" open>
              <summary className="faint cursor-pointer text-[11px]">why ACM says this</summary>
              <ul className="mt-1 flex flex-col gap-0.5">
                {qa.why.map((w, i) => (
                  <li key={i} className="num dim text-[11px] leading-snug">↳ {w}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </li>
  );
}

export function ReasoningChain({ item, active }: { item: InferenceItem; active: number }) {
  return (
    <ol className="flex flex-col">
      {item.reasoning.map((step, i) => (
        <li key={step.step} className="flex gap-3">
          <div className="flex flex-col items-center">
            <span className={`grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-bold ring-1 transition-colors ${
              i <= active ? "bg-splm-500 text-ink-950 ring-splm-400" : "bg-white/5 text-[var(--text-faint)] ring-white/15"}`}>
              {i + 1}
            </span>
            {i < item.reasoning.length - 1 && <span className={`w-px flex-1 ${i < active ? "bg-splm-500" : "bg-white/10"}`} />}
          </div>
          <div className={`pb-3 transition-opacity ${i <= active ? "opacity-100" : "opacity-40"}`}>
            <div className="text-[12.5px] font-semibold">{step.step.replace(/^\d+\.\s*/, "")}</div>
            <div className="num dim text-[11.5px] leading-snug">{step.detail}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

const NODE_FILL: Record<string, string> = {
  action: "#21a98c", actor: "#f5b942", impacted: "#3dd6c6", environment: "#bef264", goal: "#a78bfa", layer: "#60a5fa",
};

export function EntityGraph({ item }: { item: InferenceItem }) {
  const W = 600, H = 400, cx = W / 2, cy = H / 2;
  const others = item.graph.nodes.filter((n) => n.id !== "action");
  const pos = new Map<string, [number, number]>([["action", [cx, cy]]]);
  others.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(others.length, 1) - Math.PI / 2;
    const r = n.kind === "layer" ? 165 : 130;
    pos.set(n.id, [cx + r * 1.55 * Math.cos(a), cy + r * Math.sin(a)]);
  });
  const edges = item.graph.edges.reduce<Record<string, typeof item.graph.edges>>((acc, e) => {
    (acc[e.to] ??= []).push(e);
    return acc;
  }, {});
  const clip = (s: string, n = 34) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="Who the action affects">
      {Object.entries(edges).map(([to, list]) => {
        const [x2, y2] = pos.get(to)!;
        const e = list[0];
        const colour = e.status ? STATUS_COLOUR[e.status] : e.basis === "simulation" ? "#c084fc" : "#4d5666";
        const mx = (cx + x2) / 2, my = (cy + y2) / 2;
        return (
          <g key={to}>
            <line x1={cx} y1={cy} x2={x2} y2={y2} stroke={colour} strokeWidth={e.status ? 2.5 : 1.5} strokeDasharray={e.basis === "relation" ? "5 4" : undefined} />
            <text x={mx} y={my - 4} textAnchor="middle" fontSize={11.5} fill="var(--text-dim)" paintOrder="stroke" stroke="var(--panel)" strokeWidth={3}>
              {clip(list.map((x) => x.label).join(" · "))}
            </text>
          </g>
        );
      })}
      {item.graph.nodes.map((n) => {
        const [x, y] = pos.get(n.id)!;
        const isAction = n.id === "action";
        const label = isAction ? `${n.label}${n.concept ? ` → ${n.concept}` : ""}` : n.label;
        const w = Math.min(210, Math.max(76, label.length * 7.6 + 20));
        return (
          <g key={n.id}>
            <rect x={x - w / 2} y={y - 16} width={w} height={32} rx={isAction ? 16 : 8}
              fill={NODE_FILL[n.kind] ?? "#64748b"} fillOpacity={isAction ? 0.95 : 0.22} stroke={NODE_FILL[n.kind] ?? "#64748b"} />
            <text x={x} y={y + 4.5} textAnchor="middle" fontSize={13} fontWeight={isAction ? 700 : 600} fill={isAction ? "#0b0e12" : "var(--text)"}>
              {clip(label, 30)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
