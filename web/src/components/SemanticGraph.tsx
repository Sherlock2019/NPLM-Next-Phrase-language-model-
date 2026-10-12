"use client";

import { useMemo, useState } from "react";
import { slotLabel } from "@/lib/api";
import type { FrameElement, PhraseFrame } from "@/lib/types";
import { Empty } from "./ui";

/**
 * The frame drawn as a semantic graph (spec section 32).
 *
 * The point of the picture is that the representation is a *graph*, not a sentence
 * template: relations radiate from the predicate, and nothing in the layout encodes
 * word order. Laid out radially and hand-drawn in SVG so node placement stays under
 * our control and the page carries no graph-library payload.
 */

interface Node {
  id: string;
  label: string;
  sub: string;
  x: number;
  y: number;
  kind: "predicate" | "element" | "nested";
  element?: FrameElement;
  frame?: PhraseFrame;
}

interface Edge {
  from: string;
  to: string;
  label: string;
}

const WIDTH = 720;
const HEIGHT = 420;

export function SemanticGraph({ frame }: { frame: PhraseFrame | null }) {
  const [selected, setSelected] = useState<Node | null>(null);

  const { nodes, edges } = useMemo(() => layout(frame), [frame]);

  if (!frame?.predicate) {
    return <Empty>No frame to draw.</Empty>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-auto w-full min-w-[560px]"
          role="img"
          aria-label="Semantic graph of the phrase frame"
        >
          {edges.map((edge, index) => {
            const from = nodes.find((n) => n.id === edge.from);
            const to = nodes.find((n) => n.id === edge.to);
            if (!from || !to) return null;
            const midX = (from.x + to.x) / 2;
            const midY = (from.y + to.y) / 2;
            return (
              <g key={index}>
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke="currentColor"
                  strokeWidth={1}
                  className="text-[var(--border)]"
                />
                <text
                  x={midX}
                  y={midY - 4}
                  textAnchor="middle"
                  className="fill-current text-[8px] uppercase tracking-wider"
                  style={{ fill: "var(--text-faint)" }}
                >
                  {edge.label}
                </text>
              </g>
            );
          })}

          {nodes.map((node) => {
            const isSelected = selected?.id === node.id;
            const radiusX = Math.max(38, node.label.length * 4.4);
            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onClick={() => setSelected(node)}
                className="cursor-pointer"
              >
                <rect
                  x={-radiusX}
                  y={-15}
                  width={radiusX * 2}
                  height={30}
                  rx={7}
                  className={
                    node.kind === "predicate"
                      ? "fill-splm-500/18 stroke-splm-500/55"
                      : isSelected
                        ? "fill-warn-400/15 stroke-warn-400/60"
                        : "stroke-[var(--border)]"
                  }
                  style={
                    node.kind !== "predicate" && !isSelected
                      ? { fill: "var(--panel-raised)" }
                      : undefined
                  }
                  strokeWidth={1}
                />
                <text
                  textAnchor="middle"
                  y={node.sub ? -1 : 4}
                  className="text-[11px] font-medium"
                  style={{ fill: "var(--text)" }}
                >
                  {node.label}
                </text>
                {node.sub && (
                  <text
                    textAnchor="middle"
                    y={9}
                    className="text-[7.5px] uppercase tracking-wider"
                    style={{ fill: "var(--text-faint)" }}
                  >
                    {node.sub}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {selected ? (
        <NodeInspector node={selected} />
      ) : (
        <p className="faint text-[11px]">Select a node to inspect it.</p>
      )}
    </div>
  );
}

function NodeInspector({ node }: { node: Node }) {
  const element = node.element;
  const rows: [string, string][] = [
    ["Type", node.kind],
    ["Value", node.label],
  ];
  if (element) {
    rows.push(
      ["Semantic role", element.semantic_role],
      ["Confidence", element.confidence.toFixed(2)],
      ["Head lemma", element.head_lemma],
      ["Linguistic source", element.deprel ?? "—"],
      ["Entity type", element.entity_type ?? "—"],
      [
        "Sentence span",
        element.token_indices.length
          ? `words ${Math.min(...element.token_indices)}–${Math.max(...element.token_indices)}`
          : "—",
      ],
    );
    if (element.alternatives.length) {
      rows.push([
        "Also considered",
        element.alternatives
          .map((alt) => `${alt.role} ${(alt.probability * 100).toFixed(0)}%`)
          .join(", "),
      ]);
    }
  }

  return (
    <dl className="panel-raised grid gap-x-4 gap-y-1 p-3 sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-2">
          <dt className="faint text-[11px]">{label}</dt>
          <dd className="truncate text-[11px]" title={value}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function layout(frame: PhraseFrame | null): { nodes: Node[]; edges: Edge[] } {
  if (!frame?.predicate) return { nodes: [], edges: [] };

  const nodes: Node[] = [];
  const edges: Edge[] = [];

  const centreX = WIDTH / 2;
  const centreY = HEIGHT / 2;

  nodes.push({
    id: "predicate",
    label: frame.predicate.lemma,
    sub: frame.predicate.type,
    x: centreX,
    y: centreY,
    kind: "predicate",
  });

  const entries: { slot: string; element: FrameElement }[] = [];
  for (const slot of [
    "subject",
    "objects",
    "recipients",
    "participants",
    "location",
    "destination",
    "source",
    "time",
    "manner",
    "instrument",
    "cause",
    "goal",
    "condition",
  ] as const) {
    for (const element of frame[slot]) entries.push({ slot, element });
  }

  // Distribute around the predicate. An ellipse keeps labels apart horizontally,
  // where the text is widest.
  const radiusX = Math.min(290, 130 + entries.length * 14);
  const radiusY = 150;

  entries.forEach((entry, index) => {
    const angle = (index / Math.max(entries.length, 1)) * Math.PI * 2 - Math.PI / 2;
    const id = `element-${index}`;
    nodes.push({
      id,
      label: entry.element.text || "?",
      sub: entry.element.semantic_role,
      x: centreX + Math.cos(angle) * radiusX,
      y: centreY + Math.sin(angle) * radiusY,
      kind: entry.element.frame ? "nested" : "element",
      element: entry.element,
      frame: entry.element.frame ?? undefined,
    });
    edges.push({ from: "predicate", to: id, label: slotLabel(entry.slot) });
  });

  return { nodes, edges };
}
