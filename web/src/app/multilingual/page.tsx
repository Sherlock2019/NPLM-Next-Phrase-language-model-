"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, percent } from "@/lib/api";
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
import type { MultilingualResponse } from "@/lib/types";

const SETS: { label: string; texts: Record<string, string> }[] = [
  {
    label: "Meeting in Paris",
    texts: {
      en: "John will meet Sarah in Paris tomorrow.",
      fr: "John rencontrera Sarah à Paris demain.",
      vi: "Ngày mai John sẽ gặp Sarah ở Paris.",
    },
  },
  {
    label: "Located in Paris",
    texts: {
      en: "John is in Paris.",
      fr: "John est à Paris.",
      vi: "John đang ở Paris.",
    },
  },
  {
    label: "Full frame",
    texts: {
      en: "John will meet Sarah in Paris tomorrow by train to negotiate the contract.",
      fr: "John rencontrera Sarah à Paris demain en train pour négocier le contrat.",
      vi: "Ngày mai John sẽ gặp Sarah ở Paris, đi bằng tàu để đàm phán hợp đồng.",
    },
  },
];

const NAMES: Record<string, string> = { en: "English", fr: "French", vi: "Vietnamese" };

/**
 * Multilingual Lab: the same meaning, three languages, one representation.
 *
 * The claim being tested is that Phrase DNA is language-independent. So the page
 * shows each language's own frame, the normalised structure, and a measured
 * agreement score — including where the languages disagree.
 */
export default function MultilingualPage() {
  const [texts, setTexts] = useState<Record<string, string>>(SETS[0].texts);
  const [data, setData] = useState<MultilingualResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (value: Record<string, string>) => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.multilingual(value));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void run(SETS[0].texts);
  }, [run]);

  const languages = Object.keys(texts);

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title="Equivalent sentences"
        hint="Each language is parsed with its own grammar, then mapped onto the same universal frame."
        actions={
          <div className="flex gap-1">
            {SETS.map((set) => (
              <button
                key={set.label}
                type="button"
                onClick={() => {
                  setTexts(set.texts);
                  void run(set.texts);
                }}
                className="faint hairline rounded border px-2 py-1 text-[10.5px] transition-colors hover:text-[var(--text)]"
              >
                {set.label}
              </button>
            ))}
          </div>
        }
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run(texts);
          }}
          className="flex flex-col gap-2"
        >
          {languages.map((code) => (
            <div key={code} className="flex items-center gap-2">
              <span className="eyebrow w-20 shrink-0">{NAMES[code] ?? code}</span>
              <input
                value={texts[code]}
                onChange={(event) =>
                  setTexts((current) => ({ ...current, [code]: event.target.value }))
                }
                className={`${inputClass} font-mono`}
                spellCheck={false}
              />
            </div>
          ))}
          <button type="submit" className={`${buttonClass} self-start`} disabled={loading}>
            {loading ? "Analysing…" : "Compare"}
          </button>
        </form>
      </Panel>

      {error && <ErrorBox error={error} />}
      {loading && !data && (
        <Panel>
          <Loading />
        </Panel>
      )}

      {data && (
        <>
          <Panel
            title="Cross-language semantic consistency"
            hint={data.metric}
          >
            {Object.keys(data.agreement).length === 0 ? (
              <Empty>
                Not enough languages parsed to compare. Install the missing parser
                models with{" "}
                <code className="num">python scripts/download_resources.py</code>.
              </Empty>
            ) : (
              <div className="flex flex-col gap-2">
                {Object.entries(data.agreement).map(([pair, value]) => {
                  const [left, right] = pair.split("-");
                  return (
                    <div key={pair} className="flex items-center gap-3">
                      <span className="w-40 shrink-0 text-[11px] font-medium">
                        {NAMES[left] ?? left} ↔ {NAMES[right] ?? right}
                      </span>
                      <Bar value={value} tone={value >= 0.8 ? "splm" : "warn"} />
                      <span className="num w-14 shrink-0 text-right text-[11px]">
                        {percent(value, 0)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
            <Caveat>
              This measures <em>structural</em> agreement only. Content words are
              excluded because comparing them across languages needs a cross-lingual
              concept inventory, which this proof of concept does not have. A high score
              means the frames have the same shape, not that they mean the same thing.
            </Caveat>
          </Panel>

          <div className="grid gap-4 lg:grid-cols-3">
            {languages.map((code) => {
              const entry = data.languages[code];
              if (!entry) return null;
              return (
                <Panel key={code} title={NAMES[code] ?? code}>
                  <div className="flex flex-col gap-3">
                    <p className="text-xs leading-relaxed">{entry.text}</p>

                    <div className="flex flex-wrap gap-1.5">
                      {entry.token_count !== null && (
                        <Pill tone="neutral">{entry.token_count} tokenizer tokens</Pill>
                      )}
                      <Pill tone={entry.parsed ? "ok" : "danger"}>
                        {entry.parsed ? "parsed" : "not parsed"}
                      </Pill>
                    </div>

                    {entry.warnings.length > 0 && (
                      <div className="rounded-md border border-warn-400/25 bg-warn-400/6 px-2.5 py-2 text-[10.5px] leading-snug text-warn-400">
                        {entry.warnings.join(" · ")}
                      </div>
                    )}

                    {entry.frame ? (
                      <FrameSummary frame={entry.frame} />
                    ) : (
                      <Empty>No frame produced.</Empty>
                    )}
                  </div>
                </Panel>
              );
            })}
          </div>

          <Panel
            title="Normalised universal frame"
            hint="What survives translation: the structure, not the words."
          >
            <SignatureTable data={data} />
          </Panel>
        </>
      )}
    </div>
  );
}

function FrameSummary({ frame }: { frame: Record<string, unknown> }) {
  const predicate = frame.predicate as { type?: string; lemma?: string; sense?: string } | undefined;
  const slots = Object.entries(frame).filter(
    ([key, value]) =>
      Array.isArray(value) &&
      value.length > 0 &&
      !["children", "unresolved_slots"].includes(key),
  ) as [string, { text: string; role: string }[]][];

  return (
    <div className="flex flex-col gap-1.5">
      {predicate && (
        <div className="panel-raised flex items-baseline gap-2 px-2.5 py-1.5">
          <span className="eyebrow text-splm-400">{predicate.type}</span>
          <span className="text-[11px] font-medium">{predicate.lemma}</span>
          {predicate.sense && (
            <span className="faint text-[10.5px]">({predicate.sense})</span>
          )}
        </div>
      )}
      {slots.map(([slot, elements]) => (
        <div key={slot} className="flex items-baseline gap-2 px-0.5">
          <span className="faint w-24 shrink-0 text-[10.5px] uppercase tracking-wide">
            {elements[0]?.role ?? slot}
          </span>
          <span className="truncate text-[11px]">
            {elements.map((element) => element.text).join(", ")}
          </span>
        </div>
      ))}
      {typeof frame.tense === "string" && (
        <div className="faint px-0.5 text-[10.5px]">tense: {frame.tense}</div>
      )}
    </div>
  );
}

function SignatureTable({ data }: { data: MultilingualResponse }) {
  const languages = Object.keys(data.languages).filter(
    (code) => data.languages[code].signature,
  );
  if (languages.length === 0) return <Empty>No signatures to compare.</Empty>;

  const keys = ["predicate_type", "predicate_sense", "tense", "modality", "negation", "depth"];

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]">
        <thead className="faint">
          <tr className="hairline border-b">
            <th className="px-2 py-1.5 font-semibold uppercase tracking-wide">Field</th>
            {languages.map((code) => (
              <th key={code} className="px-2 py-1.5 font-semibold uppercase tracking-wide">
                {NAMES[code] ?? code}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => {
            const values = languages.map((code) => {
              const signature = data.languages[code].signature as Record<string, unknown>;
              return signature?.[key];
            });
            const agree = new Set(values.map((value) => JSON.stringify(value))).size === 1;
            return (
              <tr key={key} className="hairline border-b last:border-0">
                <td className="faint px-2 py-1">{key.replace(/_/g, " ")}</td>
                {values.map((value, index) => (
                  <td
                    key={index}
                    className={`num px-2 py-1 ${agree ? "" : "text-warn-400"}`}
                  >
                    {value === null || value === undefined ? "—" : String(value)}
                  </td>
                ))}
              </tr>
            );
          })}

          <tr className="hairline border-b last:border-0">
            <td className="faint px-2 py-1">roles</td>
            {languages.map((code) => {
              const signature = data.languages[code].signature as Record<string, unknown>;
              const roles = (signature?.roles as string[]) ?? [];
              return (
                <td key={code} className="px-2 py-1 text-[10.5px]">
                  {roles.join(", ") || "—"}
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
