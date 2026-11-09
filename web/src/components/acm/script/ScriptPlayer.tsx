"use client";

/**
 * The 2D scene player and transcript.
 *
 * The drawing is computed from the engine's state at the selected step: actor and object
 * positions come from the scene's stage marks, held objects sit with their holder, and an
 * object offered to someone is drawn as a dashed arrow. The active event's actor and target
 * are highlighted. This is a 2D player, not a 3D or physics view.
 *
 * Voice: the browser's speech synthesis reads dialogue lines, only where the browser has it
 * (no button otherwise). Captions are always shown. Mute keeps stepping through the script
 * on a timer without sound. Playback never starts on its own.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { nameOf, type Scene, type SceneEvent, type State, type Step } from "@/lib/acm/scene";
import { Dot, SourceBadge, btn } from "./shared";

const W = 800, H = 400;

function layout(scene: Scene) {
  const marks = scene.location.marks.filter((m) => m.x !== null && m.y !== null);
  const xs = marks.map((m) => m.x as number), ys = marks.map((m) => m.y as number);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (x: number) => 70 + ((x - x0) / Math.max(x1 - x0, 1)) * (W - 140);
  const sy = (y: number) => 120 + ((y - y0) / Math.max(y1 - y0, 1)) * (H - 200);
  const at = (id: string | null | undefined) => {
    const m = marks.find((k) => k.id === id);
    return m ? { x: sx(m.x as number), y: sy(m.y as number) } : null;
  };
  return { marks, sx, sy, at };
}

const VERB_MARK: Record<string, string> = { pause: "⏸", gesture: "✋", offer: "→", place: "↓", take: "↑", move: "➜", hold: "✊" };

export function Player({ scene, state, event, colors, focus }: {
  scene: Scene; state: State; event: SceneEvent | null; colors: Record<string, string>; focus: string | null;
}) {
  const { marks, sx, sy, at } = layout(scene);
  const pos: Record<string, { x: number; y: number }> = {};
  const crowd: Record<string, number> = {};
  for (const a of scene.actors) {
    const p = at(state[a.id]?.position as string);
    if (!p) continue;
    const key = String(state[a.id]?.position);
    const n = (crowd[key] = (crowd[key] ?? -1) + 1);
    pos[a.id] = { x: p.x + n * 34, y: p.y };
  }
  const objPos: Record<string, { x: number; y: number; held: boolean }> = {};
  for (const o of scene.objects.filter((x) => x.kind === "physical")) {
    const holder = state[o.id]?.holder as string | null;
    if (holder && pos[holder]) objPos[o.id] = { x: pos[holder].x + 26, y: pos[holder].y + 6, held: true };
    else {
      const p = at(state[o.id]?.position as string);
      if (p) objPos[o.id] = { ...p, held: false };
    }
  }
  const lit = (id: string) => (focus ? focus === id : !event || !event.actor || event.actor === id || event.target === id);
  const minX = Math.min(...marks.map((m) => m.x as number)), maxX = Math.max(...marks.map((m) => m.x as number));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full rounded-lg bg-[var(--panel-raised)]" role="img"
      aria-label={`${scene.location.name}. ${event ? event.description : "Before the first event."}`}>
      <rect x={sx(minX) - 50} y={70} width={sx(maxX) - sx(minX) + 100} height={H - 110} rx={10} fill="var(--panel)" stroke="var(--border)" strokeWidth={2} />
      <text x={sx(minX) - 36} y={92} fontSize={12} fontWeight={700} fill="var(--text-faint)">{scene.location.name.toUpperCase()}{scene.location.city ? ` · ${scene.location.city.toUpperCase()}` : ""}</text>
      {marks.map((m) => {
        const on = event?.target === m.id;
        return (
          <g key={m.id}>
            <circle cx={sx(m.x as number)} cy={sy(m.y as number)} r={on ? 6 : 3} fill={on ? "#06b6d4" : "var(--text-faint)"} opacity={on ? 1 : 0.5} />
            <text x={sx(m.x as number)} y={sy(m.y as number) + 62} textAnchor="middle" fontSize={9.5} fill="var(--text-faint)">{m.label}</text>
          </g>
        );
      })}

      {/* objects at marks (not held) */}
      {scene.objects.filter((o) => objPos[o.id] && !objPos[o.id].held).map((o) => {
        const p = objPos[o.id];
        const big = typeof o.attributes.colour === "string";
        const fill = big ? (o.attributes.colour === "red" ? "#dc2626" : String(o.attributes.colour)) : "var(--panel-raised)";
        const on = event?.object === o.id || event?.target === o.id;
        const w = big ? 150 : 74, h = big ? 52 : 26;
        return (
          <g key={o.id} opacity={focus && !on ? 0.55 : 1}>
            <rect x={p.x - w / 2} y={p.y - h / 2 - (big ? 0 : 18)} width={w} height={h} rx={big ? 16 : 6} fill={fill}
              stroke={on ? "#06b6d4" : big ? "none" : "var(--border)"} strokeWidth={on ? 3 : 1.5} />
            {big && <><circle cx={p.x - 44} cy={p.y + 26} r={12} fill="#1f2937" /><circle cx={p.x + 44} cy={p.y + 26} r={12} fill="#1f2937" /></>}
            <text x={p.x} y={p.y + (big ? 4 : -14)} textAnchor="middle" fontSize={big ? 11.5 : 10} fontWeight={700} fill={big ? "#fff" : "var(--text)"}>{o.label}</text>
          </g>
        );
      })}

      {/* offers: dashed arrow from the object (or its holder) to the actor it is offered to */}
      {scene.objects.map((o) => {
        const to = state[o.id]?.offered_to as string | null;
        const from = objPos[o.id];
        if (!to || !from || !pos[to]) return null;
        return <path key={`offer-${o.id}`} d={`M${from.x} ${from.y - 30} Q ${(from.x + pos[to].x) / 2} ${Math.min(from.y, pos[to].y) - 110} ${pos[to].x - 6} ${pos[to].y - 52}`}
          fill="none" stroke="#06b6d4" strokeWidth={2.2} strokeDasharray="7 5" markerEnd="url(#acm-arrow)">
          <title>{`${o.label} offered to ${nameOf(scene, to)}`}</title>
        </path>;
      })}

      {scene.actors.map((a) => {
        const p = pos[a.id];
        if (!p) return null;
        const c = colors[a.id];
        const on = lit(a.id);
        const speaking = event?.actor === a.id && event.type === "dialogue";
        const acting = event?.actor === a.id;
        return (
          <g key={a.id} opacity={on ? 1 : 0.32}>
            {acting && <ellipse cx={p.x} cy={p.y + 34} rx={30} ry={7} fill={c} opacity={0.4} />}
            {event?.target === a.id && <circle cx={p.x} cy={p.y - 6} r={40} fill="none" stroke={c} strokeDasharray="4 4" strokeWidth={2} />}
            <circle cx={p.x} cy={p.y - 34} r={13} fill={c} stroke={acting ? "#fff" : "none"} strokeWidth={2} />
            <path d={`M${p.x - 16} ${p.y + 32} L${p.x - 13} ${p.y - 16} Q${p.x} ${p.y - 26} ${p.x + 13} ${p.y - 16} L${p.x + 16} ${p.y + 32} Z`} fill={c} />
            <text x={p.x} y={p.y + 50} textAnchor="middle" fontSize={13} fontWeight={800} fill={c}>{a.name}</text>
            {speaking && (
              <g>
                <rect x={p.x - 22} y={p.y - 82} width={44} height={24} rx={8} fill="var(--panel)" stroke={c} strokeWidth={2} />
                <text x={p.x} y={p.y - 65} textAnchor="middle" fontSize={13} fontWeight={800} fill={c}>“…”</text>
              </g>
            )}
            {acting && !speaking && event?.verb && VERB_MARK[event.verb] && (
              <text x={p.x + 22} y={p.y - 46} fontSize={18} fill={c}>{VERB_MARK[event.verb]}</text>
            )}
          </g>
        );
      })}

      {/* objects being held, drawn with their holder */}
      {scene.objects.filter((o) => objPos[o.id]?.held).map((o) => {
        const p = objPos[o.id];
        const on = event?.object === o.id || event?.target === o.id;
        return (
          <g key={o.id}>
            <rect x={p.x - 4} y={p.y - 10} width={56} height={18} rx={5} fill="var(--panel)" stroke={on ? "#06b6d4" : "var(--text-dim)"} strokeWidth={on ? 2.5 : 1.2} />
            <text x={p.x + 24} y={p.y + 3} textAnchor="middle" fontSize={9.5} fontWeight={700} fill="var(--text)">{o.label.replace(/^Car /, "")}</text>
          </g>
        );
      })}
      <defs>
        <marker id="acm-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="#06b6d4" />
        </marker>
      </defs>
    </svg>
  );
}

const captionMs = (text: string) => 1400 + text.split(/\s+/).length * 320;

export function ScriptPlayer({ scene, events, steps, colors, focus, label }: {
  scene: Scene; events: SceneEvent[]; steps: Step[]; colors: Record<string, string>; focus: string | null; label?: string;
}) {
  const [i, setI] = useState(0);
  const [speech, setSpeech] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const token = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mutedRef = useRef(false);

  useEffect(() => { setSpeech(typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window); }, []);
  const halt = useCallback(() => {
    token.current += 1;
    if (timer.current) clearTimeout(timer.current);
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
  }, []);
  useEffect(() => halt, [halt]);

  const run = useCallback((k: number, tok: number) => {
    if (tok !== token.current) return;
    if (k >= events.length) { setPlaying(false); return; }
    setI(k);
    const e = events[k];
    const next = (ms: number) => { if (tok === token.current) timer.current = setTimeout(() => run(k + 1, tok), ms); };
    if (!e.dialogue || mutedRef.current) { next(captionMs(e.dialogue ?? e.description)); return; }
    const u = new SpeechSynthesisUtterance(e.dialogue);
    const order = Math.max(scene.actors.findIndex((a) => a.id === e.actor), 0);
    const voices = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith("en"));
    if (voices.length) u.voice = voices[order % voices.length];
    u.pitch = [0.85, 1.2, 1.05][order % 3];
    u.onend = () => next(400);
    u.onerror = (ev) => {
      if (ev.error === "interrupted" || ev.error === "canceled") return;
      setNote("Speech is unavailable right now; continuing with captions only.");
      mutedRef.current = true; setMuted(true); next(captionMs(e.dialogue ?? ""));
    };
    window.speechSynthesis.speak(u);
  }, [events, scene.actors]);

  const playFrom = (k: number) => { halt(); setPlaying(true); run(k, token.current); };
  const go = (k: number) => { const n = Math.min(Math.max(k, 0), events.length - 1); if (playing) playFrom(n); else setI(n); };

  const e = events[i];
  const state = steps[i + 1]?.state ?? steps[steps.length - 1].state;

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex flex-col gap-2">
          <Player scene={scene} state={state} event={e} colors={colors} focus={focus} />
          <div aria-live="polite" className="panel-raised px-4 py-3 text-[14px]">
            <span className="faint mr-2 text-[10.5px] font-bold uppercase tracking-wider">Event {i + 1} / {events.length}</span>
            {e.dialogue ? (
              <><b style={{ color: colors[e.actor ?? ""] }}>{nameOf(scene, e.actor)}:</b> “{e.dialogue}”</>
            ) : (
              <span className="italic">{e.description}</span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label={`${label ?? "Scene"} controls`}>
            <button type="button" className={btn} disabled={i === 0} onClick={() => go(i - 1)}>← Previous</button>
            <button type="button" className={btn} disabled={i >= events.length - 1} onClick={() => go(i + 1)}>Next →</button>
            <button type="button" className={btn} onClick={() => (playing ? playFrom(0) : setI(0))}>↺ Replay</button>
            {speech ? (
              <>
                {playing
                  ? <button type="button" className={btn} onClick={() => { halt(); setPlaying(false); }}>⏸ Pause</button>
                  : <button type="button" className={`${btn} border-cyan-400 bg-cyan-400/10`} onClick={() => playFrom(i >= events.length - 1 ? 0 : i)}>▶ Play with voice</button>}
                <button type="button" className={btn} aria-pressed={muted} onClick={() => { mutedRef.current = !mutedRef.current; setMuted(mutedRef.current); if (playing) playFrom(i); }}>
                  {muted ? "🔇 Muted (captions)" : "🔊 Mute"}
                </button>
              </>
            ) : (
              <span className="faint text-[12px]">Voice playback is not available in this browser; the transcript is complete.</span>
            )}
          </div>
          {speech && <p className="faint text-[11.5px]">Voice: your browser’s built-in speech synthesis reading the script. No generated voices and no lip-sync.</p>}
          {note && <p className="text-[12px] text-amber-500">{note}</p>}
        </div>

        <ol className="flex max-h-[520px] flex-col gap-1 overflow-y-auto pr-1" aria-label={`${label ?? "Scene"} timeline and transcript`}>
          {events.map((ev, k) => {
            const c = ev.actor ? colors[ev.actor] : "var(--text-faint)";
            const dim = focus && ev.actor !== focus && ev.target !== focus;
            return (
              <li key={ev.id}>
                <button type="button" onClick={() => go(k)} aria-current={k === i ? "step" : undefined}
                  className={`flex w-full items-start gap-2 rounded-lg border-l-4 px-3 py-2 text-left transition-colors ${k === i ? "bg-cyan-400/10" : "hover:bg-[var(--panel-raised)]"} ${dim ? "opacity-40" : ""}`}
                  style={{ borderColor: c }}>
                  <span className="num faint w-6 shrink-0 pt-0.5 text-[11px]">{ev.order}</span>
                  <span className="min-w-0 text-[13px]">
                    {ev.dialogue ? (
                      <><b style={{ color: c }}>{nameOf(scene, ev.actor).toUpperCase()}:</b> “{ev.dialogue}”</>
                    ) : (
                      <span className="italic">{ev.description}</span>
                    )}
                    <span className="faint mt-0.5 flex flex-wrap gap-x-2 text-[10.5px]">
                      <span>{ev.type}{ev.verb ? ` · ${ev.verb}` : ""}{ev.target ? ` → ${nameOf(scene, ev.target)}` : ""}</span>
                      {ev.effects.length > 0 && <span>changes: {ev.effects.map((x) => `${nameOf(scene, x.subject)}.${x.attribute}`).join(", ")}</span>}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>
      <p className="faint flex flex-wrap items-center gap-2 text-[11.5px]">
        <SourceBadge s={events[0]?.source ?? "authored_demo"} />
        {events[0]?.source === "generated_inference" ? "Generated text; its events do not change the scene state." : "The script is illustrative demo content."}
        <span className="flex items-center gap-1"><Dot color="#06b6d4" /> dashed arrow = an object being offered</span>
      </p>
    </div>
  );
}
