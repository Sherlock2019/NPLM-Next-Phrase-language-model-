"use client";

/**
 * Physics lab (mockup) for image and video input, in five stages (see SceneFlow):
 *   1. the scene: an image or a video
 *   2. computer vision recognises each object and classifies it with the object library of the
 *      recognised environment (kitchen, house, garden, street, mountain): mass, shape, texture,
 *      material, friction, fragility, rules; the environment goes into the physics engine
 *      (mock detector / tracker; matter.js stands in for a game engine such as Unreal Engine 5)
 *   3. the action: stated in text or seen in the image / video (e.g. a collision)
 *   4. the physics engine simulates the consequences; ACM places them on its rings
 *   5. the output: predicted frames (a side-view replay) + events; questions about any object
 */

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { buttonClass, buttonGhostClass, inputClass, Caveat } from "@/components/ui";
import { StatusTag } from "@/components/multimodal/Stages";
import type { SceneData } from "@/lib/multimodal/types";
import { behaviourFor, ENGINE_NAME, ENVIRONMENTS, environmentFor, RULES, type Environment } from "@/lib/acm/behaviours";
import { simulateLab, type LabAction, type LabResult, type LabScene } from "@/lib/acm/physics";
import {
  actionLabel, answerObjectQuestion, detect, eventChain, objectFacts, objectPresets, toLabScene,
  type Detection, type LlmPlan, type ObjAnswer, type ObjChain,
} from "@/lib/acm/objects";
import type { LlmAnswer } from "@/lib/multimodal/types";
import { ChatShell, DnaChips, LlmAnswerView } from "./Chat";
import { SceneFlow } from "./SceneFlow";

export interface LabHandle {
  run: () => Promise<void>;
}

const COLOUR: Record<string, string> = { blue: "#3b82f6", red: "#ef4444", green: "#22c55e", yellow: "#eab308" };
const fill = (o: { color?: string; cls: string }) => (o.color ? COLOUR[o.color] ?? o.color : o.cls === "pusher" ? "#334155" : "#94a3b8");
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

// -- 1. detector view (top-down) -----------------------------------------------------------------

function DetectorView({ scene, detections, scan, selected, onPick }: {
  scene: LabScene; detections: Detection[]; scan: number; selected: string; onPick: (id: string) => void;
}) {
  const S = 400;
  const [x0, y0, x1, y1] = scene.table;
  const W = (x1 + 0.3) * S, H = (y1 + 0.1) * S;
  const scanX = scan * W;
  return (
    <svg viewBox={`-10 -10 ${W + 20} ${H + 20}`} className="block h-auto w-full" role="img" aria-label="Detected objects, top-down view">
      <rect x={x1 * S} y={y0 * S} width={0.3 * S} height={(y1 - y0) * S} fill="var(--panel-raised)" />
      <text x={x1 * S + 6} y={16} fontSize={11} fill="var(--text-faint)">floor (assumed)</text>
      <rect x={x0 * S} y={y0 * S} width={(x1 - x0) * S} height={(y1 - y0) * S} fill="#d6b58a" fillOpacity={0.55} stroke="#7a5a32" strokeWidth={3} />
      {scene.objects.map((o) => o.cls === "pusher" ? (
        <rect key={o.id} x={(o.x - o.r) * S} y={(o.y - o.r * 1.4) * S} width={o.r * 2 * S} height={o.r * 2.8 * S} rx={5} fill={fill(o)} />
      ) : (
        <circle key={o.id} cx={o.x * S} cy={o.y * S} r={o.r * S} fill={fill(o)} stroke="#0f172a" strokeWidth={1.5} />
      ))}
      {detections.map((d) => {
        const shown = scan >= 1 || d.box[0] * S < scanX;
        if (!shown) return null;
        const pad = d.cls === "table" ? 0 : 6;
        const [bx0, by0, bx1, by1] = [d.box[0] * S - pad, d.box[1] * S - pad, d.box[2] * S + pad, d.box[3] * S + pad];
        const active = d.id === selected;
        const label = `${d.label} ${d.conf.toFixed(2)}${d.track ? ` #${d.track}` : ""}`;
        return (
          <g key={d.id} onClick={() => onPick(d.id)} className="cursor-pointer">
            <rect x={bx0} y={by0} width={bx1 - bx0} height={by1 - by0} fill="transparent" stroke={active ? "#f0abfc" : "#22d3ee"}
              strokeWidth={active ? 3 : 2} strokeDasharray={d.cls === "table" ? "8 5" : undefined} />
            <rect x={bx0} y={d.cls === "table" ? by1 - 18 : by0 - 18} width={label.length * 6.4 + 8} height={17} fill={active ? "#f0abfc" : "#22d3ee"} />
            <text x={bx0 + 4} y={d.cls === "table" ? by1 - 5 : by0 - 5} fontSize={11} fontWeight={700} fill="#0b0e12">{label}</text>
          </g>
        );
      })}
      {scan > 0 && scan < 1 && <line x1={scanX} x2={scanX} y1={-10} y2={H + 10} stroke="#22d3ee" strokeWidth={2} opacity={0.8} />}
    </svg>
  );
}

// -- 3. side view of the simulation ---------------------------------------------------------------

function SideView({ scene, result, frame }: { scene: LabScene; result: LabResult | null; frame: number }) {
  const S = 200, XMIN = -0.25, XMAX = 2.6, ZMAX = 1.2;
  const X = (x: number) => (x - XMIN) * S;
  const Z = (z: number) => (ZMAX - z) * S;
  const f = result?.frames[Math.min(frame, (result?.frames.length ?? 1) - 1)];
  const [x0, , x1] = scene.table;
  const top = 0.75;
  const target = result && f ? Object.keys(f.poses).find((id) => result.final[id].moved > 0.01) : undefined;
  const trail = target && result ? result.frames.slice(0, frame + 1).map((fr) => `${X(fr.poses[target].x)},${Z(fr.poses[target].z)}`).join(" ") : "";
  return (
    <svg viewBox={`0 0 ${(XMAX - XMIN) * S} ${(ZMAX + 0.08) * S}`} className="block h-auto w-full" role="img" aria-label="Side view of the simulation">
      <line x1={0} x2={(XMAX - XMIN) * S} y1={Z(0)} y2={Z(0)} stroke="var(--text-faint)" strokeWidth={2} />
      <text x={6} y={Z(0) + 14} fontSize={10.5} fill="var(--text-faint)">floor_01 (assumed hard floor)</text>
      {!result?.supportRemoved && (
        <g>
          <rect x={X(x0)} y={Z(top)} width={(x1 - x0) * S} height={0.04 * S} fill="#b08550" stroke="#7a5a32" />
          {[x0 + 0.04, x1 - 0.08].map((lx) => <rect key={lx} x={X(lx)} y={Z(top - 0.04)} width={0.04 * S} height={(top - 0.04) * S} fill="#9a7444" opacity={0.7} />)}
          <line x1={X(x1)} x2={X(x1)} y1={Z(top + 0.35)} y2={Z(0)} stroke="#f59e0b" strokeDasharray="4 4" opacity={0.7} />
          <text x={X(x1) + 4} y={Z(top + 0.3)} fontSize={10} fill="#f59e0b">edge x = {x1} m</text>
          <text x={X(x0) + 6} y={Z(top) + 22} fontSize={10} fill="var(--text-faint)">table_01 · top 0.75 m (assumed)</text>
        </g>
      )}
      {trail && <polyline points={trail} fill="none" stroke="#c084fc" strokeWidth={1.5} strokeDasharray="3 3" />}
      {scene.objects.map((o) => {
        const beh = behaviourFor(o.cls);
        if (beh.movable !== "dynamic") return null;
        const p = f?.poses[o.id] ?? { x: o.x, z: top + beh.sizeM.h / 2, angle: 0 };
        const w = Math.max(beh.sizeM.w, 2 * o.r) * S, h = beh.sizeM.h * S;
        return (
          <g key={o.id} transform={`translate(${X(p.x)} ${Z(p.z)}) rotate(${(p.angle * 180) / Math.PI})`}>
            <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={3} fill={fill(o)} stroke="#0f172a" strokeWidth={1.2} />
            <path d={`M ${w / 2} ${-h / 4} q ${w * 0.35} ${h * 0.2} 0 ${h * 0.45}`} fill="none" stroke={fill(o)} strokeWidth={3} />
            <text y={-h / 2 - 5} textAnchor="middle" fontSize={10} fill="var(--text-dim)">{o.id}</text>
          </g>
        );
      })}
      {f?.hand && <rect x={X(f.hand.x) - 0.03 * S} y={Z(f.hand.z + 0.04)} width={0.06 * S} height={0.09 * S} rx={6} fill="#334155" opacity={0.9} />}
      {!f?.hand && scene.objects.filter((o) => o.cls === "pusher").map((o) => (
        <rect key={o.id} x={X(o.x) - 0.03 * S} y={Z(top + 0.09)} width={0.06 * S} height={0.09 * S} rx={6} fill="#334155" opacity={0.9} />
      ))}
      <text x={(XMAX - XMIN) * S - 8} y={16} textAnchor="end" fontSize={12} fontWeight={700} fill="var(--text-dim)">
        t = {(f?.t ?? 0).toFixed(2)} s
      </text>
    </svg>
  );
}

// -- 4. answer rendering ----------------------------------------------------------------------

function ObjChainRow({ c }: { c: ObjChain }) {
  return (
    <li className="flex flex-col gap-1 rounded-md bg-white/3 px-2 py-1.5">
      <span className="flex flex-wrap items-center gap-1.5 text-[10.5px]">
        <span aria-hidden className="text-splm-300">→</span>
        <StatusTag status={c.basis} />
        <span className="faint">rule {c.rule}</span>
      </span>
      <DnaChips items={[["WHO", c.who], ["DOES", c.does], ["WITH", c.with_whom], ["WHERE", c.where], ["WHEN", c.when]]} />
      <span className="dim text-[11px]">{c.what}</span>
      <span className="num faint text-[10.5px]">↳ WHY: {c.why}</span>
    </li>
  );
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail ?? `${url} ${response.status}`);
  return data as T;
}

function ObjAnswerView({ a, llm, onReplay }: { a: ObjAnswer; llm: LlmAnswer; onReplay: (action: LabAction) => void }) {
  const worded = llm.error === undefined;
  return (
    <>
      <div className="flex flex-col gap-1">
        <span className="eyebrow">1 · Reading the question</span>
        <DnaChips items={a.reading} />
        <span className="faint text-[10.5px]">{a.parser}</span>
      </div>
      <LlmAnswerView llm={llm} step="2" />
      <div className="flex flex-col gap-1">
        <span className="eyebrow">{worded ? "3 · Facts (simulation + library)" : "2 · Answer (simulation + library)"}</span>
        <p className={worded ? "dim text-[12px] leading-relaxed" : "text-[13px] leading-relaxed"}>{a.answer}</p>
      </div>
      {a.props && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11.5px]">
          {a.props.map((p) => (
            <div key={p.label} className="contents">
              <dt className="faint">{p.label}</dt>
              <dd>{p.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {a.actionDna && (
        <div className="flex flex-col gap-1">
          <span className="eyebrow">3 · Action → consequences (simulated, Phrase DNA)</span>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded bg-fuchsia-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase">action</span>
            <DnaChips items={a.actionDna} tone="bg-fuchsia-500/10" />
          </div>
          {a.chains.length ? <ol className="flex flex-col gap-1">{a.chains.map((c, i) => <ObjChainRow key={i} c={c} />)}</ol>
            : <p className="faint text-[11.5px] italic">No event for this object: nothing acts on it.</p>}
          {a.action && (
            <button type="button" className={`${buttonGhostClass} self-start`} onClick={() => onReplay(a.action!)}>▶ replay this in the lab</button>
          )}
        </div>
      )}
    </>
  );
}

// -- intro --------------------------------------------------------------------------------------

/** How the image/video stage works: scene → recognise + libraries → action → simulate → frames. */
function LabIntro({ mode, env }: { mode: "image" | "video"; env: string }) {
  return (
    <div className="panel-raised flex flex-col gap-2.5 p-3">
      <p className="text-[13px] leading-relaxed">
        <b>How the {mode} stage works:</b> computer vision identifies each object{mode === "video" ? " (and tracks it over time)" : ""} and
        matches it to a library of objects with their physical properties; a physics engine then simulates the action and outputs what
        would happen next, and ACM predicts its consequences. This scene is recognised as <b>{env}</b>.
      </p>
      <SceneFlow />
      <p className="text-[11px] text-warn-400">
        Prototype: recognition is mocked (the objects come from the demo scene, and the environment is the library that matches them best),
        object properties are typical values for the class, not measurements, and only the demo&apos;s own objects (mug, table, floor, hand) can
        be simulated so far — the other library objects are listed but not yet simulated.
      </p>
    </div>
  );
}

// -- the lab ------------------------------------------------------------------------------------

const ACTIONS = [
  { key: "push+", label: "Push toward the edge (+x)" },
  { key: "push-", label: "Push toward the centre (−x)" },
  { key: "flick-", label: "Flick hard toward the centre" },
  { key: "drop", label: "Lift and drop" },
  { key: "remove", label: "Remove the table (support)" },
  { key: "none", label: "No action" },
] as const;

function buildAction(key: string, target: string, amount: number): LabAction {
  switch (key) {
    case "push+": return { kind: "push", target, dir: 1, distanceM: amount };
    case "push-": return { kind: "push", target, dir: -1, distanceM: amount };
    case "flick-": return { kind: "flick", target, dir: -1, speedMps: 2 };
    case "drop": return { kind: "drop", target, heightM: 0.3 };
    case "remove": return { kind: "remove_support" };
    default: return { kind: "none" };
  }
}

export const PhysicsLab = forwardRef<LabHandle, { scene: SceneData; mode: "image" | "video"; defaultTarget: string; actor: string }>(
  function PhysicsLab({ scene: sceneData, mode, defaultTarget, actor }, ref) {
    const scene = useMemo(() => toLabScene(sceneData), [sceneData]);
    const detections = useMemo(() => detect(sceneData, mode === "video"), [sceneData, mode]);
    const movers = scene.objects.filter((o) => behaviourFor(o.cls).movable === "dynamic");
    const env = useMemo(() => environmentFor(detections.map((d) => d.cls)), [detections]);
    const envLib = ENVIRONMENTS[env];
    const [scan, setScan] = useState(0);
    const [selected, setSelected] = useState(defaultTarget);
    const [target, setTarget] = useState(defaultTarget);
    const [actionKey, setActionKey] = useState<string>("push+");
    const [amount, setAmount] = useState(0.2);
    const [result, setResult] = useState<LabResult | null>(null);
    const [shownAction, setShownAction] = useState<LabAction | null>(null);
    const [frame, setFrame] = useState(0);
    const [playing, setPlaying] = useState(false);
    const [busy, setBusy] = useState(false);
    const raf = useRef<number | null>(null);
    const action = buildAction(actionKey, target, amount);

    function play(next: LabAction) {
      const r = simulateLab(scene, next);
      setResult(r);
      setShownAction(next);
      setFrame(0);
      setPlaying(true);
    }

    useEffect(() => {
      if (!playing || !result) return;
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      if (reduce) {
        setFrame(result.frames.length - 1);
        setPlaying(false);
        return;
      }
      const start = performance.now();
      const tick = (now: number) => {
        const t = (now - start) / 1000;
        const i = result.frames.findIndex((f) => f.t >= t);
        if (i === -1) {
          setFrame(result.frames.length - 1);
          setPlaying(false);
          return;
        }
        setFrame(i);
        raf.current = requestAnimationFrame(tick);
      };
      raf.current = requestAnimationFrame(tick);
      return () => { if (raf.current) cancelAnimationFrame(raf.current); };
    }, [playing, result]);

    async function run() {
      if (busy) return;
      setBusy(true);
      setResult(null);
      for (let i = 0; i <= 20; i++) {
        setScan(i / 20);
        await wait(45);
      }
      await wait(250);
      play(action);
      await wait(3000); // let the replay finish before the demo moves on
      setBusy(false);
    }
    useImperativeHandle(ref, () => ({ run }));

    const sel = detections.find((d) => d.id === selected);
    const beh = behaviourFor(sel?.cls ?? "cup");
    const timeNow = result?.frames[frame]?.t ?? 0;

    return (
      <section className="hairline flex flex-col gap-3 rounded-lg border p-3" aria-label="Physics lab">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h3 className="text-[14px] font-semibold">Physics lab — recognise + classify · properties · simulate · ask</h3>
          <span className="rounded bg-fuchsia-600 px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">mockup</span>
          <span className="faint text-[11px]">{ENGINE_NAME}</span>
        </div>

        <LabIntro mode={mode} env={envLib.label} />

        <div className="grid gap-3 lg:grid-cols-[minmax(280px,1fr)_minmax(260px,360px)]">
          <div className="panel-raised flex flex-col gap-1.5 p-2">
            <span className="eyebrow">1 · Recognise + classify objects {mode === "video" ? "+ track them (frame at T)" : ""}</span>
            <DetectorView scene={scene} detections={detections} scan={scan} selected={selected} onPick={setSelected} />
            <span className="text-[11.5px]">
              Environment recognised: <b>{envLib.label}</b> <span className="faint">({envLib.cues})</span> → objects classified with the{" "}
              <b>{envLib.label.toLowerCase()} library</b> ({envLib.objects.length} object types, each with mass, shape, texture, material).
            </span>
            <span className="faint text-[10.5px]">
              Mock {mode === "video" ? "recognition model + tracker (YOLO + ByteTrack style)" : "recognition model (YOLO style)"}: boxes and classes come from the fixture scene, not a model. Click a box to pick an object.
            </span>
            <details className="text-[11px]">
              <summary className="faint cursor-pointer">Object libraries per environment</summary>
              <div className="mt-1.5 flex flex-col gap-2">
                {(Object.entries(ENVIRONMENTS) as [Environment, (typeof ENVIRONMENTS)[Environment]][]).map(([key, lib]) => (
                  <div key={key}>
                    <span className={`font-semibold ${key === env ? "text-fuchsia-300" : ""}`}>{lib.label}{key === env ? " (this scene)" : ""}</span>
                    <span className="faint"> — {lib.cues}</span>
                    <table className="mt-0.5 w-full text-[10.5px]">
                      <thead className="faint text-left"><tr><th>object</th><th>mass</th><th>shape</th><th>texture</th><th>material</th></tr></thead>
                      <tbody>
                        {lib.objects.map((o) => (
                          <tr key={o.cls}><td>{o.label}</td><td>{o.massKg === null ? "static" : `${o.massKg} kg`}</td><td>{o.shape}</td><td>{o.texture}</td><td>{o.material}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
              </div>
            </details>
          </div>
          <div className="flex flex-col gap-2">
            <span className="eyebrow">2 · Library properties + behaviour</span>
            <ul className="flex flex-col gap-1">
              {detections.map((d) => (
                <li key={d.id}>
                  <button type="button" onClick={() => setSelected(d.id)}
                    className={`panel-raised flex w-full items-center gap-2 px-2 py-1 text-left text-[11.5px] ${d.id === selected ? "ring-2 ring-fuchsia-400/60" : ""}`}>
                    <span className="size-2.5 shrink-0 rounded-full" style={{ background: d.cls === "table" ? "#b08550" : fill(scene.objects.find((o) => o.id === d.id) ?? { cls: d.cls }) }} />
                    <span className="font-medium">{d.id}</span>
                    <span className="faint">{d.label} · {d.conf.toFixed(2)}{d.track ? ` · track #${d.track}` : ""}</span>
                    <span className="dim ml-auto">{behaviourFor(d.cls).movable}</span>
                  </button>
                </li>
              ))}
            </ul>
            {sel && (
              <div className="panel-raised flex flex-col gap-1 p-2 text-[11.5px]">
                <span className="font-semibold">{sel.id} → class “{beh.cls}”</span>
                <span className="dim">shape: {beh.shape} · texture: {beh.texture}</span>
                <span className="dim">{beh.material} · {beh.massKg ? `${beh.massKg} kg` : "static"} · μ {beh.friction} · e {beh.restitution}
                  {beh.fragile ? ` · fragile (break > ${beh.breakSpeed} m/s)` : ""}{beh.container ? " · container" : ""}</span>
                <ul className="flex flex-col gap-0.5">
                  {beh.rules.map((r) => <li key={r} className="faint text-[10.5px]"><b className="dim">{RULES[r].name}</b>: {RULES[r].law}</li>)}
                </ul>
                <span className="flex items-center gap-1.5"><StatusTag status="assumed" /><span className="faint text-[10.5px]">library values for the class, not measured</span></span>
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="eyebrow">3 · Simulate (side view: x along the push, height from the library)</span>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-0.5 text-[11px]">
              <span className="faint">object</span>
              <select className={inputClass} value={target} onChange={(e) => setTarget(e.target.value)}>
                {movers.map((o) => <option key={o.id} value={o.id}>{o.id}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-0.5 text-[11px]">
              <span className="faint">action</span>
              <select className={inputClass} value={actionKey} onChange={(e) => setActionKey(e.target.value)}>
                {ACTIONS.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
              </select>
            </label>
            {actionKey.startsWith("push") && (
              <label className="flex flex-col gap-0.5 text-[11px]">
                <span className="faint">distance {amount.toFixed(2)} m</span>
                <input type="range" min={0.02} max={0.5} step={0.01} value={amount} onChange={(e) => setAmount(Number(e.target.value))} />
              </label>
            )}
            <button type="button" className={buttonClass} disabled={busy} onClick={() => play(action)}>Simulate</button>
            <button type="button" className={buttonGhostClass} disabled={busy} onClick={run}>{busy ? "Running…" : "Detect + simulate"}</button>
          </div>
          <div className="grid gap-3 lg:grid-cols-[1fr_minmax(260px,360px)]">
            <div className="panel-raised p-2">
              <SideView scene={scene} result={result} frame={frame} />
              {result && (
                <input type="range" className="w-full" min={0} max={result.frames.length - 1} value={frame} aria-label="Scrub time"
                  onChange={(e) => { setPlaying(false); setFrame(Number(e.target.value)); }} />
              )}
            </div>
            <div className="flex flex-col gap-1">
              <span className="faint text-[11px]">{shownAction ? `If: ${actionLabel(shownAction)}` : "Press Simulate to run the engine."}</span>
              {result && (
                <ol className="flex max-h-72 flex-col gap-1 overflow-y-auto">
                  {result.events.map((e, i) => {
                    const c = eventChain(e);
                    return (
                      <li key={i} className={`flex items-start gap-1.5 text-[11px] leading-snug ${e.t > timeNow + 0.001 ? "opacity-35" : ""}`}>
                        <span className="num faint w-11 shrink-0">{e.t.toFixed(2)}s</span>
                        <StatusTag status={c.basis} />
                        <span><b>{e.id}</b> {c.does}<span className="faint"> — {e.detail}</span></span>
                      </li>
                    );
                  })}
                </ol>
              )}
            </div>
          </div>
        </div>

        <ChatShell
          key={selected}
          title={`4 · Ask about ${selected}`}
          hint="answers come from the simulation's events and the behaviour library's rules"
          presets={objectPresets(selected, sel?.cls ?? "cup")}
          placeholder="e.g. What if I push the blue cup 15 cm toward the edge? · Can the red cup break?"
          ask={async (q) => {
            // 1. the LLM reads the question into a plan (falls back to the keyword parser)
            const objects = [...scene.objects.map((o) => ({ id: o.id, cls: o.cls, color: o.color ?? null })), { id: "table_01", cls: "table", color: null }];
            let plan: LlmPlan | undefined;
            try {
              plan = await postJson<LlmPlan>("/api/acm/llm/plan", { question: q, objects, selected });
            } catch { plan = undefined; }
            // 2. the simulator + library compute the facts
            const a = answerObjectQuestion(q, scene, selected, shownAction ?? action, actor, plan);
            // 3. the LLM words the answer from those facts only
            let llm: LlmAnswer;
            try {
              llm = await postJson<LlmAnswer>("/api/acm/llm/answer", { question: q, facts: objectFacts(a) });
            } catch (e) { llm = { error: (e as Error).message }; }
            return <ObjAnswerView a={a} llm={llm} onReplay={(next) => play(next)} />;
          }}
        />
        <Caveat>
          Mockup: the detector, tracker and question parser are simulated; object properties are library assumptions; the side view
          reduces the scene to 2D. A production version would run a real detector and a game physics engine (e.g. Unreal Chaos) on the
          same scene and rules.
        </Caveat>
      </section>
    );
  },
);
