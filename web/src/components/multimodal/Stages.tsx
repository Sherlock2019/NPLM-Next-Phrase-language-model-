"use client";

/** Result stages A-E and the pieces they show. Every status is a word, not only a colour. */

import { useState, type ReactNode } from "react";
import type { Circle, Meaning, MeaningField } from "@/lib/multimodal/types";

export type StageState = "idle" | "running" | "done" | "error";

const STATUS_STYLE: Record<string, string> = {
  observed: "bg-ok-400/12 text-ok-400 ring-ok-400/30",
  inferred: "bg-base-500/15 text-base-400 ring-base-500/30",
  assumed: "bg-warn-400/12 text-warn-400 ring-warn-400/30",
  predicted: "bg-fuchsia-500/12 text-fuchsia-400 ring-fuchsia-500/30",
  simulation: "bg-fuchsia-500/12 text-fuchsia-400 ring-fuchsia-500/30",
  unknown: "bg-white/5 text-[var(--text-dim)] ring-white/15",
  rule: "bg-splm-500/15 text-splm-300 ring-splm-500/30",
  observation: "bg-ok-400/12 text-ok-400 ring-ok-400/30",
  supplied: "bg-warn-400/12 text-warn-400 ring-warn-400/30",
};
const STATUS_WORD: Record<string, string> = {
  simulation: "simulated",
  rule: "rule-derived",
  observation: "observed",
};

export function StatusTag({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ring-1 ring-inset ${STATUS_STYLE[status] ?? STATUS_STYLE.unknown}`}
    >
      {STATUS_WORD[status] ?? status}
    </span>
  );
}

export function StageCard({
  letter,
  title,
  state,
  children,
  note,
}: {
  letter: string;
  title: string;
  state: StageState;
  children?: ReactNode;
  note?: ReactNode;
}) {
  const label: Record<StageState, string> = {
    idle: "waiting",
    running: "loading…",
    done: "complete",
    error: "error",
  };
  const dot: Record<StageState, string> = {
    idle: "bg-white/15",
    running: "bg-splm-400 animate-pulse-soft",
    done: "bg-ok-400",
    error: "bg-danger-400",
  };
  return (
    <section className="panel animate-rise" aria-busy={state === "running"} aria-live="polite">
      <header className="hairline flex items-center gap-3 border-b px-4 py-2.5">
        <span className="grid size-6 place-items-center rounded-md bg-splm-500/15 text-[11px] font-bold text-splm-300 ring-1 ring-splm-500/30">
          {letter}
        </span>
        <h3 className="flex-1 text-[13px] font-semibold">{title}</h3>
        <span className="flex items-center gap-1.5 text-[11px]">
          <span className={`size-2 rounded-full ${dot[state]}`} aria-hidden />
          <span className="dim">{label[state]}</span>
        </span>
      </header>
      {state === "done" && <div className="p-4">{children}</div>}
      {state === "idle" && <p className="faint px-4 py-3 text-xs">Not run yet.</p>}
      {state === "running" && <p className="dim px-4 py-3 text-xs">Loading this stage…</p>}
      {note && state === "done" && <div className="px-4 pb-3">{note}</div>}
    </section>
  );
}

const FIELDS: [keyof Meaning, string][] = [
  ["who", "WHO / actor"],
  ["action", "ACTION"],
  ["what", "WHAT / target"],
  ["to_whom", "TO WHOM"],
  ["where", "WHERE"],
  ["direction", "WHERE TO / direction"],
  ["when", "WHEN"],
  ["how", "HOW"],
  ["why", "WHY / purpose"],
];

export function MeaningView({ meaning }: { meaning: Meaning }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs font-medium">{meaning.evidence_kind}</p>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {FIELDS.map(([key, label]) => {
          const field = meaning[key] as MeaningField | undefined;
          if (!field) return null;
          return (
            <div key={key} className="panel-raised px-3 py-2">
              <div className="flex items-center gap-2">
                <span className="eyebrow flex-1">{label}</span>
                <StatusTag status={field.status} />
              </div>
              <div className="mt-1 text-[13px] font-medium">{field.value ?? "unknown"}</div>
              <div className="faint mt-0.5 text-[11px] leading-snug">{field.source}</div>
            </div>
          );
        })}
      </div>
      {meaning.observed_states && meaning.observed_states.length > 0 && (
        <div>
          <h4 className="eyebrow mb-1.5">Observed / stated states</h4>
          <ul className="flex flex-col gap-1">
            {meaning.observed_states.map((s, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 text-xs">
                <StatusTag status={s.status} />
                <span>{s.text}</span>
                <span className="faint text-[11px]">— {s.source}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {meaning.rejected_claims && meaning.rejected_claims.length > 0 && (
        <div>
          <h4 className="eyebrow mb-1.5">Claims the evidence cannot support (kept out)</h4>
          <ul className="flex flex-col gap-1">
            {meaning.rejected_claims.map((c, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 text-xs">
                <StatusTag status="unknown" />
                <span className="line-through decoration-white/30">{c.claim}</span>
                <span className="faint text-[11px]">— {c.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {meaning.unknowns && (
          <div>
            <h4 className="eyebrow mb-1.5">Unknowns</h4>
            <div className="flex flex-wrap gap-1.5">
              {meaning.unknowns.map((u) => (
                <span key={u} className="rounded bg-white/5 px-2 py-0.5 text-[11px] ring-1 ring-white/10">
                  {u}
                </span>
              ))}
            </div>
          </div>
        )}
        {meaning.evidence && (
          <div>
            <h4 className="eyebrow mb-1.5">Evidence sources</h4>
            <ul className="faint flex flex-col gap-0.5 text-[11px]">
              {meaning.evidence.slice(0, 8).map((e, i) => (
                <li key={i}>
                  <span className="font-semibold uppercase">{e.type}</span> · {e.ref}
                  {e.backend ? ` · ${e.backend}` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {(meaning.parse_note || meaning.notes?.length) && (
        <p className="faint text-[11px]">{[meaning.parse_note, ...(meaning.notes ?? [])].filter(Boolean).join(" · ")}</p>
      )}
    </div>
  );
}

export function CirclesView({ circles, caption }: { circles: Circle[]; caption?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      {caption}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {circles.map((circle) => (
          <div key={circle.key} className={`panel-raised p-3 ${circle.key === "wider" ? "md:col-span-2 xl:col-span-3" : ""}`}>
            <h4 className="eyebrow mb-2">{circle.title}</h4>
            {circle.rows.length === 0 ? (
              <p className="faint text-xs italic">{circle.empty}</p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {circle.rows.map((row, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs leading-snug">
                    <StatusTag status={row.basis} />
                    <span>
                      <b>{row.about}</b>: {row.text}
                      {row.needs && row.needs.length > 0 && (
                        <span className="faint"> — would need: {row.needs.join(", ")}</span>
                      )}
                      {row.reason && <span className="faint"> — {row.reason}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function JsonInspect({ label, data }: { label: string; data: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="panel-raised">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium hover:bg-white/4"
      >
        <span aria-hidden>{open ? "▾" : "▸"}</span>
        {label}
      </button>
      {open && (
        <pre className="num hairline max-h-96 overflow-auto border-t p-3 text-[11px] leading-relaxed">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
