"use client";

/**
 * Top-down tabletop scene in world metres, drawn as SVG.
 *
 * With a simulator result it animates the proposed movement, keeps a dashed ghost
 * of the initial position, draws the trajectory, and shows a fallen object as
 * "landing position unknown" - never at an invented spot on the floor.
 */

import { useEffect, useRef, useState } from "react";
import type { SimResult, Vec } from "@/lib/multimodal/tabletop";
import type { SceneEntity } from "@/lib/multimodal/types";

const S = 300; // px per metre
const PAD = 24;
const FLOOR_M = 0.32;
const COLOURS: Record<string, string> = { blue_cup_01: "#2563eb", red_cup_01: "#dc2626" };

export function TabletopScene({
  entities,
  table,
  result,
  title,
  tag,
  animate = true,
  replayKey = 0,
}: {
  entities: SceneEntity[];
  table: [number, number, number, number];
  result?: SimResult | null;
  title: string;
  tag: { text: string; tone: "observed" | "assumed" | "predicted" | "scripted" };
  animate?: boolean;
  replayKey?: number;
}) {
  const [progress, setProgress] = useState(result ? 0 : 1);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    if (!result) {
      setProgress(1);
      return;
    }
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (!animate || reduced) {
      setProgress(1);
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / 1800);
      setProgress(p);
      if (p < 1) frame.current = requestAnimationFrame(tick);
    };
    setProgress(0);
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, [result, animate, replayKey]);

  const [x0, y0, x1, y1] = table;
  const W = (x1 - x0 + FLOOR_M) * S + 2 * PAD;
  const H = (y1 - y0) * S + 2 * PAD + 22;
  const X = (x: number) => PAD + (x - x0) * S;
  const Y = (y: number) => PAD + (y - y0) * S;
  const tagStyle: Record<string, string> = {
    observed: "#166534",
    assumed: "#a16207",
    predicted: "#7e22ce",
    scripted: "#0f766e",
  };

  const items = entities.filter((e) => e.class !== "table" && e.position);
  return (
    <figure className="panel-raised overflow-hidden">
      <figcaption className="hairline flex flex-wrap items-center gap-2 border-b px-3 py-1.5">
        <span className="text-[11px] font-semibold">{title}</span>
        <span
          className="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white"
          style={{ background: tagStyle[tag.tone] }}
        >
          {tag.text}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={`${title}: ${tag.text}`}>
        <rect x={X(x1)} y={PAD} width={FLOOR_M * S} height={(y1 - y0) * S} fill="#cbd5e1" opacity={0.55} />
        <text x={X(x1) + 6} y={PAD + 14} fontSize={11} fill="#475569">
          floor (assumed)
        </text>
        <rect x={X(x0)} y={Y(y0)} width={(x1 - x0) * S} height={(y1 - y0) * S} fill="#e9d5b0" stroke="#7c5a2a" strokeWidth={3} />
        <text x={X(x0) + 6} y={Y(y0) + 14} fontSize={11} fill="#5b3f17">
          table_01 — support boundary
        </text>
        <defs>
          <marker id={`arrow-${title.replace(/\W/g, "")}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="#7e22ce" />
          </marker>
        </defs>
        {items.map((e) => {
          const [ex, ey] = e.position as Vec;
          const r = (e.radius_m ?? 0.04) * S;
          const isPusher = e.class === "pusher" || e.class === "person";
          const path = result?.path[e.id];
          const final = result ? result.final[e.id] : undefined;
          const fell = result && final === null;
          const end: Vec = path ? path[1] : [ex, ey];
          const moveP = fell ? Math.min(1, progress / 0.6) : progress;
          const cx = ex + (end[0] - ex) * (path ? moveP : 0);
          const cy = ey + (end[1] - ey) * (path ? moveP : 0);
          const dropP = fell ? Math.max(0, (progress - 0.6) / 0.4) : 0;
          const radius = r * (1 - 0.4 * dropP);
          const fill = COLOURS[e.id] ?? "#64748b";
          const marker = `url(#arrow-${title.replace(/\W/g, "")})`;
          if (isPusher)
            return (
              <g key={e.id}>
                <rect x={X(ex) - 0.04 * S} y={Y(ey) - 0.05 * S} width={0.08 * S} height={0.1 * S} rx={5} fill="#334155" />
                <text x={X(ex)} y={Y(ey) - 0.05 * S - 5} fontSize={10} textAnchor="middle" fill="#334155">
                  {e.id}
                </text>
              </g>
            );
          return (
            <g key={e.id}>
              {path && (
                <>
                  <circle cx={X(ex)} cy={Y(ey)} r={r} fill="none" stroke={fill} strokeDasharray="4 3" opacity={0.7} />
                  <line x1={X(ex)} y1={Y(ey)} x2={X(end[0])} y2={Y(end[1])} stroke="#7e22ce" strokeWidth={2} strokeDasharray="6 4" markerEnd={marker} />
                </>
              )}
              <circle cx={X(cx)} cy={Y(cy)} r={radius} fill={fill} fillOpacity={1 - 0.35 * dropP} stroke="#0f172a" strokeWidth={1.5} />
              <text x={X(cx)} y={Y(cy) + r + 12} fontSize={10} textAnchor="middle" fill="#0f172a">
                {e.id}
              </text>
              {fell && progress >= 1 && (
                <text x={X(x1) - 6} y={Y(cy) + r + 28} fontSize={10} fill="#7e22ce" fontWeight={600} textAnchor="end">
                  falls off the edge · landing position UNKNOWN
                </text>
              )}
            </g>
          );
        })}
        <text x={PAD} y={H - 6} fontSize={10} fill="#64748b">
          top-down · world metres (calibrated frame) · x {x0}–{x1} m
        </text>
      </svg>
    </figure>
  );
}
