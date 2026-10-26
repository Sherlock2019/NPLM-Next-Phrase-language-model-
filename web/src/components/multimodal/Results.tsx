"use client";

/**
 * Stages A-E shared by the Text, Image and Video tabs:
 * A input · B MLM meaning · C ACM consequences · D visual outcome · E alternatives.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { simulate, type SimAction, type SimResult, type SimScene } from "@/lib/multimodal/tabletop";
import type { ActionKey, Circle, Meaning, Scenario, SceneData } from "@/lib/multimodal/types";
import { ACTION_KEYS } from "@/lib/multimodal/types";
import { CirclesView, JsonInspect, MeaningView, StageCard, type StageState } from "./Stages";
import { TabletopScene } from "./TabletopScene";

export const STAGES = ["A", "B", "C", "D", "E"] as const;
export type StageKey = (typeof STAGES)[number];
export type StageMap = Record<StageKey, StageState>;
const IDLE: StageMap = { A: "idle", B: "idle", C: "idle", D: "idle", E: "idle" };

/** Reveal stages one after another; one run at a time; cancellable on reset or input change. */
export function useStagedRun() {
  const [stages, setStages] = useState<StageMap>(IDLE);
  const [running, setRunning] = useState(false);
  const timers = useRef<number[]>([]);
  const busy = useRef(false);

  const clear = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };

  const reset = useCallback(() => {
    clear();
    busy.current = false;
    setRunning(false);
    setStages(IDLE);
  }, []);

  const run = useCallback((onError?: () => string | null) => {
    if (busy.current) return false; // no duplicate concurrent runs
    busy.current = true;
    setRunning(true);
    clear();
    const problem = onError?.() ?? null;
    STAGES.forEach((key, i) => {
      timers.current.push(window.setTimeout(() => setStages((s) => ({ ...s, [key]: "running" })), i * 350));
      timers.current.push(
        window.setTimeout(() => {
          setStages((s) => ({ ...s, [key]: problem && key !== "A" ? "error" : "done" }));
          if (i === STAGES.length - 1) {
            busy.current = false;
            setRunning(false);
          }
        }, i * 350 + 300),
      );
    });
    return true;
  }, []);

  useEffect(() => () => clear(), []);
  return { stages, running, run, reset };
}

export function toSimScene(scene: SceneData): SimScene {
  const table = scene.entities.find((e) => e.class === "table")?.extent;
  if (!table) throw new Error("scene has no table extent");
  return {
    table,
    objects: scene.entities
      .filter((e) => e.class === "cup" && e.position)
      .map((e) => ({ id: e.id, x: e.position![0], y: e.position![1], r: e.radius_m ?? 0.04 })),
  };
}

export function toSimAction(scenario: Scenario | undefined): SimAction {
  const a = scenario?.action;
  if (!a) return { kind: "none" };
  if (a.predicate === "push")
    return {
      kind: "push",
      target: a.target,
      directionDeg: a.parameters.direction_deg.value,
      distanceM: a.parameters.distance.value,
    };
  return { kind: "move", target: a.target, to: [a.destination!.x, a.destination!.y] };
}

function eventsText(result: SimResult): string {
  const interesting = result.events.filter((e) => e.kind !== "remains_supported");
  if (interesting.length === 0) return "every object remains supported";
  return interesting.map((e) => `${e.kind.replace("_", " ")}: ${e.entity_id}`).join(" · ");
}

export function Results({
  stages,
  input,
  meaning,
  meaningJson,
  scene,
  sceneTag,
  scenarios,
  selected,
  circles,
  circlesCaption,
  acmJson,
  noScene,
}: {
  stages: StageMap;
  input: ReactNode;
  meaning: Meaning | null;
  meaningJson: unknown;
  scene: SceneData | null;
  sceneTag: { text: string; tone: "observed" | "assumed" };
  scenarios: Record<string, Scenario> | null;
  selected: ActionKey;
  circles: Circle[] | null;
  circlesCaption?: ReactNode;
  acmJson: unknown;
  noScene?: string;
}) {
  const sim = useMemo(() => (scene ? toSimScene(scene) : null), [scene]);
  const results = useMemo(() => {
    if (!sim || !scenarios) return null;
    return Object.fromEntries(
      ACTION_KEYS.map((k) => [k, simulate(sim, toSimAction(scenarios[k]))]),
    ) as Record<ActionKey, SimResult>;
  }, [sim, scenarios]);
  const scenario = scenarios?.[selected];
  const [replay, setReplay] = useState(0);
  const table = sim?.table ?? [0, 0, 1.2, 0.8];

  return (
    <div className="flex flex-col gap-3">
      <StageCard letter="A" title="Input" state={stages.A}>
        {input}
      </StageCard>

      <StageCard
        letter="B"
        title="MLM — structured meaning"
        state={stages.B}
        note={<JsonInspect label="Inspect MLM JSON" data={meaningJson} />}
      >
        {meaning && <MeaningView meaning={meaning} />}
      </StageCard>

      <StageCard
        letter="C"
        title="ACM — consequences (six circles)"
        state={stages.C}
        note={<JsonInspect label="Inspect ACM JSON" data={acmJson} />}
      >
        {circles ? (
          <CirclesView circles={circles} caption={circlesCaption} />
        ) : (
          <div className="text-xs">{circlesCaption ?? "No ACM result for this input."}</div>
        )}
      </StageCard>

      <StageCard letter="D" title="Visual outcome — initial vs predicted" state={stages.D}>
        {noScene ? (
          <p className="dim text-xs">{noScene}</p>
        ) : (
          scene &&
          results && (
            <div className="flex flex-col gap-3">
              <div className="grid gap-3 lg:grid-cols-2">
                <TabletopScene entities={scene.entities} table={table} title="Initial state" tag={sceneTag} result={null} />
                <TabletopScene
                  entities={scene.entities}
                  table={table}
                  title={`Predicted: ${scenario?.label ?? selected}`}
                  tag={{ text: "Illustrative simulation", tone: "predicted" }}
                  result={results[selected]}
                  replayKey={replay}
                />
              </div>
              <div className="flex flex-wrap items-center gap-3 text-xs">
                <button type="button" className="dim hairline rounded-md border px-2.5 py-1 hover:text-[var(--text)]" onClick={() => setReplay((n) => n + 1)}>
                  Replay animation
                </button>
                <span>
                  <b>Predicted:</b> {eventsText(results[selected])}
                </span>
              </div>
              {scenario && (
                <details className="panel-raised px-3 py-2 text-xs">
                  <summary className="cursor-pointer font-medium">Assumptions and unknowns behind this prediction</summary>
                  <ul className="mt-2 flex flex-col gap-1">
                    {scenario.assumptions.map((a) => (
                      <li key={a.name}>
                        <b className="text-warn-400">ASSUMED</b> {a.name}
                        {a.value !== undefined && a.value !== null ? ` = ${String(a.value)} ${a.unit ?? ""}` : ""} — {a.reason}
                      </li>
                    ))}
                    {scenario.unknowns.map((u) => (
                      <li key={u}>
                        <b className="dim">UNKNOWN</b> {u}
                      </li>
                    ))}
                  </ul>
                  <p className="faint mt-2">
                    Backend: {scenario.backend.name}@{scenario.backend.version} — a constrained simulator, not general physical
                    understanding. A picture of a prediction is not evidence that it is right.
                  </p>
                </details>
              )}
            </div>
          )
        )}
      </StageCard>

      <StageCard letter="E" title="Alternative actions — same initial state" state={stages.E}>
        {noScene ? (
          <p className="dim text-xs">{noScene}</p>
        ) : (
          scene &&
          results &&
          scenarios && (
            <div className="grid gap-3 lg:grid-cols-3">
              {ACTION_KEYS.map((k) => (
                <div key={k} className="flex flex-col gap-1.5">
                  <TabletopScene
                    entities={scene.entities}
                    table={table}
                    title={scenarios[k]?.label ?? k}
                    tag={{ text: "Illustrative simulation", tone: "predicted" }}
                    result={results[k]}
                  />
                  <p className="text-[11px]">
                    <b>Outcome:</b> {eventsText(results[k])}
                  </p>
                </div>
              ))}
            </div>
          )
        )}
      </StageCard>
    </div>
  );
}
