"use client";

import type { DnaSortData } from "@/lib/speech";
import { Empty, Pill } from "@/components/ui";

/**
 * What the user said, sorted into Phrase DNA:
 * WHO · ACTION / STATUS · ON WHAT · FOR WHAT · WHERE · WHEN · WITH WHOM · HOW.
 *
 * A filled row shows the words the parser placed there. "?" (dashed) means the
 * predicate expects that information and the utterance did not give it; "—" means
 * it was not mentioned and is not expected. Words the parser placed nowhere are
 * listed as unsorted - never forced into a row.
 */
export function DnaSort({ sort, compact = false }: { sort: DnaSortData | null; compact?: boolean }) {
  if (!sort) return <Empty>No Phrase DNA: nothing was recognised.</Empty>;
  const rows = sort.categories.filter((c) => c.key !== "condition" || c.items.length > 0);
  const filled = rows.filter((c) => c.items.length > 0).length;
  const parsed = rows.some((c) => c.items.length > 0);

  return (
    <div className="flex flex-col gap-2">
      {!parsed && (
        <p className="text-[11px] text-warn-400">
          The parser placed nothing: check that a Stanza model is installed for “{sort.language}”
          (python scripts/download_resources.py --languages {sort.language || "en"}).
        </p>
      )}
      <div className={`grid gap-1.5 ${compact ? "" : "sm:grid-cols-2"}`}>
        {rows.map((category) => (
          <div
            key={category.key}
            className={`flex min-w-0 items-start gap-3 rounded-lg border px-3 py-2 ${
              category.items.length
                ? category.key === "action"
                  ? "border-splm-500/35 bg-splm-500/8"
                  : "hairline"
                : category.missing
                  ? "border-dashed border-warn-400/45 bg-warn-400/5"
                  : "border-dashed border-white/10"
            }`}
          >
            <span
              className={`eyebrow w-28 shrink-0 pt-0.5 ${
                category.key === "action" ? "text-splm-400" : category.missing ? "text-warn-400" : ""
              }`}
            >
              {category.key === "action" && sort.predicate_kind
                ? sort.predicate_kind === "action" ? "ACTION" : "STATUS"
                : category.label}
            </span>
            <span className="flex min-w-0 flex-1 flex-wrap gap-1.5">
              {category.items.length > 0 ? (
                category.items.map((item, index) => (
                  <span key={index} className="inline-flex min-w-0 flex-col">
                    <span className="truncate text-sm font-medium" title={item.text}>{item.text}</span>
                    <span className="faint text-[10px] uppercase tracking-wide">
                      {[item.role, item.entity_type].filter(Boolean).join(" · ").toLowerCase()}
                    </span>
                  </span>
                ))
              ) : (
                <span className="faint text-sm">{category.missing ? "?" : "—"}</span>
              )}
            </span>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <Pill tone="splm">{filled}/{rows.length} filled</Pill>
        {sort.intent && <Pill>{sort.intent}</Pill>}
        {sort.tense && <Pill>{sort.tense}</Pill>}
        {sort.modality && <Pill>{sort.modality}</Pill>}
        {sort.negation && <Pill tone="warn">negated</Pill>}
        {sort.unsorted.length > 0 && (
          <span className="faint text-[11px]">
            unsorted: <span className="text-[var(--text-dim)]">{sort.unsorted.join(" · ")}</span>
          </span>
        )}
      </div>

      {!compact && sort.clauses.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="eyebrow">Nested clauses</p>
          {sort.clauses.map((clause, index) => (
            <div key={index} className="panel-raised p-2.5">
              <DnaSort sort={clause} compact />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
