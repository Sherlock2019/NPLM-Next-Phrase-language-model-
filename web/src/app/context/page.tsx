"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, fullNumber, percent } from "@/lib/api";
import {
  Caveat,
  Empty,
  ErrorBox,
  Loading,
  Panel,
  Pill,
  Stat,
  buttonClass,
  inputClass,
} from "@/components/ui";
import type { ContextResponse, GraphEdge, GraphNode } from "@/lib/types";

const DEFAULT = `John met Sarah in Paris.
She gave him a document.
He read it later.`;

/**
 * Context Graph: entities, events and how later sentences refer back to them.
 */
export default function ContextPage() {
  const [text, setText] = useState(DEFAULT);
  const [data, setData] = useState<ContextResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);

  const run = useCallback(async (value: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.context({ text: value });
      setData(result);
      setSelected(null);
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

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Discourse">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run(text);
          }}
          className="flex flex-col gap-3"
        >
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={4}
            spellCheck={false}
            className={`${inputClass} resize-y font-mono leading-relaxed`}
          />
          <button type="submit" className={`${buttonClass} self-start`} disabled={loading}>
            {loading ? "Building…" : "Build context graph"}
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
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Entities" value={data.nodes.filter((n) => n.kind !== "event" && n.kind !== "state").length} />
            <Stat label="Events" value={data.nodes.filter((n) => n.kind === "event" || n.kind === "state").length} />
            <Stat label="Relations" value={data.edges.length} />
            <Stat
              label="Serialised size"
              value={`${fullNumber(data.graph_token_count)} tok`}
              sub={
                data.raw_token_count
                  ? `raw text is ${fullNumber(data.raw_token_count)} tokens`
                  : data.token_count_note
              }
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <Panel title="Graph" hint="Click a node to inspect it.">
              <GraphView
                nodes={data.nodes}
                edges={data.edges}
                selected={selected}
                onSelect={setSelected}
              />
            </Panel>

            <div className="flex flex-col gap-4">
              <Panel
                title="Resolved references"
                hint="Matched on grammatical features and recency. Confidence falls when several antecedents fit."
              >
                {data.coreferences.length === 0 ? (
                  <Empty>No pronouns to resolve in this text.</Empty>
                ) : (
                  <div className="flex flex-col gap-2">
                    {data.coreferences.map((reference, index) => (
                      <div key={index} className="panel-raised px-3 py-2">
                        <div className="flex items-baseline gap-2">
                          <span className="text-[11px] font-medium">
                            {reference.mention}
                          </span>
                          <span aria-hidden className="faint">
                            →
                          </span>
                          <span
                            className={`text-[11px] ${
                              reference.resolved_label ? "text-splm-300" : "text-warn-400"
                            }`}
                          >
                            {reference.resolved_label ?? "unresolved"}
                          </span>
                          <span className="num faint ml-auto text-[10.5px]">
                            {reference.resolved_label
                              ? percent(reference.confidence, 0)
                              : ""}
                          </span>
                        </div>
                        {reference.alternatives.length > 0 && (
                          <div className="faint mt-1 text-[10.5px]">
                            other candidates: {reference.alternatives.join(", ")}
                          </div>
                        )}
                        {!reference.resolved_label && (
                          <div className="faint mt-1 text-[10.5px] leading-snug">
                            No antecedent matched its features. Left unresolved rather
                            than guessed.
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Panel>

              {selected && (
                <Panel title="Node">
                  <dl className="grid gap-y-1">
                    {(
                      [
                        ["Label", selected.label],
                        ["Kind", selected.kind],
                        ["Entity type", selected.entity_type ?? "—"],
                        ["Lemma", selected.lemma ?? "—"],
                        ["First seen", `sentence ${selected.sentence_index + 1}`],
                        ["Mentions", selected.mentions.join(", ") || "—"],
                      ] as [string, string][]
                    ).map(([label, value]) => (
                      <div key={label} className="flex items-baseline justify-between gap-3">
                        <dt className="faint text-[11px]">{label}</dt>
                        <dd className="truncate text-[11px]">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </Panel>
              )}
            </div>
          </div>

          <Panel title="Context efficiency">
            <div className="flex flex-col gap-2">
              <p className="dim text-[11px] leading-relaxed">
                Raw text: {fullNumber(data.raw_token_count)} tokens. The same content
                serialised from the graph: {fullNumber(data.graph_token_count)} tokens.
              </p>
              <Caveat>
                Both figures use the same tokenizer, so they are comparable. This is not
                a claim that the graph is a lossless replacement for the text — it keeps
                predicates, roles and entities, and discards everything else. On short
                passages the serialised graph is often <em>larger</em> than the original,
                which is exactly what this measurement is for.
              </Caveat>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}

/** Events on a spine, their participants hanging off, ordered by sentence. */
function GraphView({
  nodes,
  edges,
  selected,
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selected: GraphNode | null;
  onSelect: (node: GraphNode) => void;
}) {
  const layout = useMemo(() => {
    const events = nodes.filter((n) => n.kind === "event" || n.kind === "state");
    const positions = new Map<string, { x: number; y: number }>();

    const rowHeight = 130;
    const height = Math.max(events.length * rowHeight + 60, 200);

    events.forEach((event, index) => {
      positions.set(event.id, { x: 130, y: 60 + index * rowHeight });
      const related = edges.filter((edge) => edge.source === event.id);
      related.forEach((edge, position) => {
        if (positions.has(edge.target)) return;
        const spread = related.length;
        positions.set(edge.target, {
          x: 380 + (position % 2) * 190,
          y: 60 + index * rowHeight + (position - (spread - 1) / 2) * 34,
        });
      });
    });

    nodes.forEach((node, index) => {
      if (!positions.has(node.id)) {
        positions.set(node.id, { x: 380, y: 30 + index * 30 });
      }
    });

    return { positions, height, width: 720 };
  }, [nodes, edges]);

  if (nodes.length === 0) return <Empty>No graph produced.</Empty>;

  return (
    <div className="overflow-auto">
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="h-auto w-full"
        style={{ minWidth: 560 }}
      >
        {edges.map((edge, index) => {
          const from = layout.positions.get(edge.source);
          const to = layout.positions.get(edge.target);
          if (!from || !to) return null;
          return (
            <g key={index}>
              <line
                x1={from.x + 60}
                y1={from.y}
                x2={to.x - 60}
                y2={to.y}
                stroke="currentColor"
                strokeWidth={1}
                className="text-[var(--border)]"
              />
              <text
                x={(from.x + to.x) / 2}
                y={(from.y + to.y) / 2 - 4}
                textAnchor="middle"
                className="text-[7.5px] uppercase tracking-wider"
                style={{ fill: "var(--text-faint)" }}
              >
                {edge.relation}
              </text>
            </g>
          );
        })}

        {nodes.map((node) => {
          const position = layout.positions.get(node.id);
          if (!position) return null;
          const isEvent = node.kind === "event" || node.kind === "state";
          const isSelected = selected?.id === node.id;
          const width = Math.max(56, node.label.length * 4.6);
          return (
            <g
              key={node.id}
              transform={`translate(${position.x}, ${position.y})`}
              onClick={() => onSelect(node)}
              className="cursor-pointer"
            >
              <rect
                x={-width}
                y={-13}
                width={width * 2}
                height={26}
                rx={isEvent ? 6 : 13}
                className={
                  isEvent
                    ? "fill-splm-500/16 stroke-splm-500/50"
                    : isSelected
                      ? "fill-warn-400/15 stroke-warn-400/60"
                      : "stroke-[var(--border)]"
                }
                style={!isEvent && !isSelected ? { fill: "var(--panel-raised)" } : undefined}
                strokeWidth={1}
              />
              <text
                textAnchor="middle"
                y={4}
                className="text-[10.5px] font-medium"
                style={{ fill: "var(--text)" }}
              >
                {node.label}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <Pill tone="splm">events and states</Pill>
        <Pill tone="neutral">entities, places and times</Pill>
      </div>
    </div>
  );
}
