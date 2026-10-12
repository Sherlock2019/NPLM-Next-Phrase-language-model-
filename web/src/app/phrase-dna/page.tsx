"use client";

import { useCallback, useEffect, useState } from "react";
import { ExpectedSlot } from "@/components/ExpectedSlot";
import { PhraseDna } from "@/components/PhraseDna";
import { SemanticGraph } from "@/components/SemanticGraph";
import { api, ApiError } from "@/lib/api";
import {
  Empty,
  ErrorBox,
  Loading,
  Panel,
  Pill,
  buttonClass,
  inputClass,
} from "@/components/ui";
import type { AnalyzeResponse, DependencyToken } from "@/lib/types";

const DEFAULT =
  "John will meet Sarah in Paris tomorrow by train to discuss the contract.";

export default function PhraseDnaPage() {
  const [text, setText] = useState(DEFAULT);
  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"cards" | "graph" | "tree" | "raw">("cards");

  const run = useCallback(async (value: string) => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.analyze({ text: value }));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void run(DEFAULT);
  }, [run]);

  const frame = data?.phrase_frame ?? null;

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Sentence">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run(text);
          }}
          className="flex flex-col gap-3 sm:flex-row"
        >
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            className={`${inputClass} font-mono`}
            spellCheck={false}
          />
          <button type="submit" className={buttonClass} disabled={loading}>
            {loading ? "Parsing…" : "Parse"}
          </button>
        </form>
      </Panel>

      {error && <ErrorBox error={error} />}
      {loading && !data && (
        <Panel>
          <Loading label="Parsing" />
        </Panel>
      )}

      {data && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="splm">
              {data.language.code} · {(data.language.confidence * 100).toFixed(0)}%
            </Pill>
            {data.style && <Pill tone="neutral">style: {data.style}</Pill>}
            {data.entities.map((entity) => (
              <Pill key={`${entity.index}`} tone="warn">
                {entity.text}: {entity.type}
              </Pill>
            ))}
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
            <Panel
              title="Universal Phrase Frame"
              actions={
                <div className="flex gap-1">
                  {(["cards", "graph", "tree", "raw"] as const).map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => setView(option)}
                      className={`rounded px-2 py-1 text-[10.5px] font-medium capitalize transition-colors ${
                        view === option
                          ? "bg-splm-500/15 text-splm-300"
                          : "faint hover:text-[var(--text)]"
                      }`}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              }
            >
              {view === "cards" && (
                <PhraseDna frame={frame} expectedSlot={data.expected_slots.top_slot} />
              )}
              {view === "graph" && <SemanticGraph frame={frame} />}
              {view === "tree" && <DependencyTree tokens={data.dependencies} />}
              {view === "raw" && (
                <pre className="num max-h-[32rem] overflow-auto text-[10.5px] leading-relaxed">
                  {JSON.stringify(data.phrase_frame, null, 2)}
                </pre>
              )}
            </Panel>

            <div className="flex flex-col gap-4">
              <Panel title="Expected next meaning">
                <ExpectedSlot
                  slots={data.expected_slots}
                  frame={frame}
                  text={text}
                />
              </Panel>

              <Panel
                title="Morphology"
                hint="Parser features normalised onto SPLM's universal categories."
              >
                <MorphologyTable data={data} />
              </Panel>
            </div>
          </div>

          <Panel
            title="Raw Universal Dependencies"
            hint="The analysis every structural layer is built on."
          >
            <UdTable tokens={data.dependencies} />
          </Panel>
        </>
      )}
    </div>
  );
}

/** Dependency arcs drawn above the sentence, the way treebank tools show them. */
function DependencyTree({ tokens }: { tokens: DependencyToken[] }) {
  if (tokens.length === 0) return <Empty>No dependency parse.</Empty>;

  const gap = 92;
  const width = Math.max(tokens.length * gap + 40, 400);
  const baseline = 170;

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} 210`} className="h-auto w-full" style={{ minWidth: width }}>
        {tokens.map((token) => {
          if (token.head === 0) return null;
          const fromX = 30 + (token.index - 1) * gap;
          const toX = 30 + (token.head - 1) * gap;
          const distance = Math.abs(token.index - token.head);
          const height = Math.min(140, 34 + distance * 26);
          const midX = (fromX + toX) / 2;
          return (
            <g key={token.index}>
              <path
                d={`M ${fromX} ${baseline - 22} C ${fromX} ${baseline - height}, ${toX} ${baseline - height}, ${toX} ${baseline - 22}`}
                fill="none"
                stroke="currentColor"
                strokeWidth={1}
                className="text-splm-500/45"
              />
              <text
                x={midX}
                y={baseline - height + 12}
                textAnchor="middle"
                className="text-[8.5px]"
                style={{ fill: "var(--text-faint)" }}
              >
                {token.deprel}
              </text>
            </g>
          );
        })}

        {tokens.map((token) => {
          const x = 30 + (token.index - 1) * gap;
          return (
            <g key={`t-${token.index}`}>
              <text
                x={x}
                y={baseline}
                textAnchor="middle"
                className="text-[11px] font-medium"
                style={{ fill: "var(--text)" }}
              >
                {token.text}
              </text>
              <text
                x={x}
                y={baseline + 13}
                textAnchor="middle"
                className="text-[8.5px] uppercase tracking-wide"
                style={{ fill: "var(--text-faint)" }}
              >
                {token.upos}
              </text>
              {token.head === 0 && (
                <text
                  x={x}
                  y={baseline + 26}
                  textAnchor="middle"
                  className="text-[8px] uppercase tracking-wider"
                  style={{ fill: "var(--color-splm-400)" }}
                >
                  root
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function UdTable({ tokens }: { tokens: DependencyToken[] }) {
  if (tokens.length === 0) return <Empty>No dependency parse.</Empty>;
  return (
    <div className="overflow-x-auto">
      <table className="num w-full text-left text-[11px]">
        <thead className="faint">
          <tr className="hairline border-b">
            {["#", "form", "lemma", "upos", "feats", "head", "deprel", "entity"].map((head) => (
              <th key={head} className="px-2 py-1.5 font-semibold uppercase tracking-wide">
                {head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tokens.map((token) => (
            <tr key={token.index} className="hairline border-b last:border-0">
              <td className="faint px-2 py-1">{token.index}</td>
              <td className="px-2 py-1 font-medium">{token.text}</td>
              <td className="dim px-2 py-1">{token.lemma}</td>
              <td className="px-2 py-1 text-splm-300">{token.upos}</td>
              <td className="faint max-w-[14rem] truncate px-2 py-1">
                {Object.entries(token.feats)
                  .map(([key, value]) => `${key}=${value}`)
                  .join("|") || "—"}
              </td>
              <td className="faint px-2 py-1">{token.head}</td>
              <td className="px-2 py-1 text-warn-400">{token.deprel}</td>
              <td className="faint px-2 py-1">{token.entity_type ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MorphologyTable({ data }: { data: AnalyzeResponse }) {
  const entries = Object.entries(data.morphology);
  if (entries.length === 0) return <Empty>No morphological analysis.</Empty>;

  return (
    <div className="flex max-h-80 flex-col gap-1.5 overflow-y-auto">
      {entries.map(([index, analysis]) => {
        const skip = new Set(["form", "lemma", "pos", "extras", "unmapped"]);
        const features = Object.entries(analysis).filter(
          ([key, value]) => !skip.has(key) && value !== null && value !== undefined,
        );
        return (
          <div key={index} className="panel-raised px-2.5 py-1.5">
            <div className="flex items-baseline gap-2">
              <span className="text-[11px] font-medium">{String(analysis.form)}</span>
              <span className="faint text-[10.5px]">{String(analysis.pos)}</span>
              <span className="faint ml-auto text-[10.5px]">
                {String(analysis.lemma)}
              </span>
            </div>
            {features.length > 0 && (
              <div className="faint mt-1 flex flex-wrap gap-x-2.5 gap-y-0.5 text-[10.5px]">
                {features.map(([key, value]) => (
                  <span key={key}>
                    {key}: <span className="text-[var(--text-dim)]">{String(value)}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
