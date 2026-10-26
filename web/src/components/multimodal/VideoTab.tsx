"use client";

/**
 * Video: the prediction checkpoint.
 *
 * Playback stops at T (before the push). "Predict Consequences" uses only the
 * frames up to T plus the explicitly supplied action parameters; frames after T
 * cannot be reached until a prediction exists. "Reveal Scripted Outcome" then
 * plays on and shows prediction and scripted outcome side by side. The outcome is
 * scripted synthetic motion - this demonstrates the workflow, not validation.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { buttonClass, buttonGhostClass, Caveat, ErrorBox } from "@/components/ui";
import type { ActionKey, DemoBundle, VideoScript } from "@/lib/multimodal/types";
import { ACTION_KEYS } from "@/lib/multimodal/types";
import { simulate } from "@/lib/multimodal/tabletop";
import { DEFAULT_FACTS, DemoUploadNotice, ManualFactsForm, manualScene, UploadField, useUpload } from "./Inputs";
import { manualCircles, manualMeaning } from "./manual";
import { Results, toSimAction, toSimScene, useStagedRun } from "./Results";
import { StatusTag } from "./Stages";
import { TabletopScene } from "./TabletopScene";

type Phase = "ready" | "to_checkpoint" | "at_checkpoint" | "revealing" | "revealed";

export function VideoTab({ demo, script, liveReason }: { demo: DemoBundle; script: VideoScript; liveReason: string }) {
  const flow = demo.flows.video;
  const T = script.checkpoint_s;
  const video = useRef<HTMLVideoElement>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [phase, setPhase] = useState<Phase>("ready");
  const [predicted, setPredicted] = useState(false);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [action, setAction] = useState<ActionKey>("push_edge");
  const upload = useUpload("video");
  const [facts, setFacts] = useState(DEFAULT_FACTS);
  const { stages, running, run, reset } = useStagedRun();
  const usingUpload = upload.file !== null;
  const manual = useMemo(() => manualScene(facts), [facts]);
  const manualAcm = useMemo(
    () => (usingUpload && manual.errors.length === 0 ? manualCircles(flow.scenarios, manual.sim, action) : null),
    [usingUpload, manual, flow.scenarios, action],
  );
  const stagesDone = stages.E === "done";
  const scenario = flow.scenarios[action];

  // Never let playback pass T before a prediction exists: later frames are evaluation data only.
  useEffect(() => {
    const el = video.current;
    if (!el) return;
    const onTime = () => {
      if (!predicted && el.currentTime > T) {
        el.pause();
        el.currentTime = T;
        setPhase("at_checkpoint");
      }
      setT(el.currentTime);
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = () => {
      setPlaying(false);
      if (phase === "revealing") setPhase("revealed");
    };
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("seeking", onTime);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onEnded);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("seeking", onTime);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onEnded);
    };
  }, [predicted, phase, T, usingUpload]);

  function restart() {
    const el = video.current;
    reset();
    setPredicted(false);
    setPhase("ready");
    if (el) {
      el.pause();
      el.currentTime = 0;
    }
  }

  function runVideoDemo() {
    restart();
    const el = video.current;
    if (!el) return;
    setPhase("to_checkpoint");
    void el.play().catch(() => setVideoError("The browser blocked playback; press Play."));
  }

  function predict() {
    if (running) return;
    const el = video.current;
    if (el && !usingUpload && el.currentTime > T + 0.05) return;
    if (run()) setPredicted(true);
  }

  function reveal() {
    const el = video.current;
    if (!el || !predicted) return;
    setPhase("revealing");
    el.currentTime = T;
    void el.play();
  }

  const atCheckpoint = usingUpload || (phase === "at_checkpoint" || (Math.abs(t - T) < 0.06 && !playing));
  const predictedResult = useMemo(() => simulate(toSimScene(flow.scene), toSimAction(scenario)), [flow.scene, scenario]);
  const duration = script.duration_s;
  const pct = (s: number) => `${(Math.min(s, duration) / duration) * 100}%`;
  const metrics = flow.comparison.metrics;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(320px,460px)_1fr]">
      <div className="panel flex flex-col gap-3 p-4">
        <div className="panel-raised overflow-hidden">
          <div className="bg-[#0f172a] px-3 py-1 text-[11px] font-semibold text-white">{script.title}</div>
          {usingUpload && upload.url ? (
            <video key={upload.url} src={upload.url} controls playsInline muted className="block w-full" aria-label="Your uploaded video (preview only, not analysed)" />
          ) : (
            <video
              ref={video}
              playsInline
              muted
              preload="auto"
              className="block w-full"
              aria-label="Synthetic demonstration video of a pusher pushing the blue cup off the table"
              onError={() => setVideoError("The sample video could not be loaded.")}
            >
              <source src="/demo/tabletop_push_synthetic.webm" type="video/webm" />
              <source src="/demo/tabletop_push_synthetic.mp4" type="video/mp4" />
            </video>
          )}
        </div>
        {videoError && <ErrorBox error={videoError} />}

        {!usingUpload && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className={buttonGhostClass} onClick={() => video.current?.play()} disabled={playing} aria-label="Play">
                Play
              </button>
              <button type="button" className={buttonGhostClass} onClick={() => video.current?.pause()} disabled={!playing} aria-label="Pause">
                Pause
              </button>
              <button type="button" className={buttonGhostClass} onClick={restart} aria-label="Restart">
                Restart
              </button>
              <span className="num ml-auto text-xs">t = {t.toFixed(2)} s</span>
            </div>
            <div aria-label="Timeline with extracted events" className="flex flex-col gap-1">
              <div
                className="relative h-10 cursor-pointer rounded bg-white/5"
                role="slider"
                tabIndex={0}
                aria-valuemin={0}
                aria-valuemax={duration}
                aria-valuenow={Number(t.toFixed(2))}
                aria-label="Video position"
                onKeyDown={(e) => {
                  const el = video.current;
                  if (!el) return;
                  if (e.key === "ArrowRight") el.currentTime = Math.min(predicted ? duration : T, el.currentTime + 0.25);
                  if (e.key === "ArrowLeft") el.currentTime = Math.max(0, el.currentTime - 0.25);
                }}
                onClick={(e) => {
                  const el = video.current;
                  if (!el) return;
                  const rect = e.currentTarget.getBoundingClientRect();
                  const target = ((e.clientX - rect.left) / rect.width) * duration;
                  el.currentTime = predicted ? target : Math.min(target, T);
                }}
              >
                {flow.timeline.map((ev) => (
                  <div
                    key={ev.id}
                    className="absolute top-1 h-3 rounded bg-fuchsia-500/50"
                    style={{ left: pct(ev.start_s), width: `calc(${pct(ev.end_s - ev.start_s)} + 2px)` }}
                    title={`${ev.predicate} ${ev.start_s}–${ev.end_s}s`}
                  />
                ))}
                {!predicted && <div className="absolute inset-y-0 right-0 bg-black/30" style={{ left: pct(T) }} title="locked until a prediction exists" />}
                <div className="absolute inset-y-0 w-0.5 bg-warn-400" style={{ left: pct(T) }} />
                <div className="absolute inset-y-0 w-0.5 bg-white" style={{ left: pct(t) }} />
                <span className="absolute bottom-0.5 text-[9px] text-warn-400" style={{ left: `calc(${pct(T)} + 3px)` }}>
                  T = {T}s checkpoint
                </span>
              </div>
              <ol className="flex flex-col gap-0.5 text-[11px]">
                {flow.timeline.map((ev) => (
                  <li key={ev.id} className="flex flex-wrap items-center gap-1.5">
                    <span className="num">{ev.start_s.toFixed(1)}–{ev.end_s.toFixed(1)} s</span>
                    <b>{ev.predicate}</b>
                    <span className="dim">{Object.entries(ev.roles).map(([r, v]) => `${r}=${v.join(",")}`).join(" ")}</span>
                    <span className="faint">cause: {ev.causal_attribution}</span>
                    {ev.start_s >= T && <StatusTag status="unknown" />}
                    {ev.start_s >= T && <span className="faint">after T — not used for prediction</span>}
                  </li>
                ))}
              </ol>
            </div>
          </>
        )}

        <UploadField kind="video" upload={upload} onChange={restart} />
        {usingUpload && (
          <>
            <DemoUploadNotice kind="video" />
            <ManualFactsForm facts={facts} onChange={(f) => { setFacts(f); reset(); }} />
            {manual.errors.length > 0 && <ErrorBox error={manual.errors.join("; ")} />}
          </>
        )}

        <label className="flex flex-col gap-1">
          <span className="eyebrow">Proposed action at T (explicitly supplied parameters)</span>
          <select className="hairline rounded-md border bg-[var(--panel-raised)] px-2.5 py-1.5 text-xs" value={action} onChange={(e) => { setAction(e.target.value as ActionKey); reset(); setPredicted(false); }}>
            {ACTION_KEYS.map((k) => (
              <option key={k} value={k}>
                {demo.action_labels[k]}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-wrap gap-2">
          {!usingUpload && (
            <button type="button" className={buttonClass} onClick={runVideoDemo} disabled={running}>
              Run Video Demo
            </button>
          )}
          <button type="button" className={buttonClass} onClick={predict} disabled={running || !atCheckpoint || (usingUpload && manual.errors.length > 0)}>
            Predict Consequences
          </button>
          {!usingUpload && (
            <button type="button" className={buttonGhostClass} onClick={reveal} disabled={!predicted || !stagesDone || phase === "revealing"}>
              Reveal Scripted Outcome
            </button>
          )}
          <button type="button" className={buttonGhostClass} onClick={restart}>
            Reset
          </button>
        </div>
        <p className="faint text-[11px]">
          {usingUpload
            ? "Prediction uses your manually supplied facts only."
            : !atCheckpoint
              ? "Run the video: it pauses at the checkpoint before the push, then Predict becomes available."
              : `Paused at T = ${T}s. The prediction will use frames up to ${T}s only.`}
        </p>
        <div className="flex flex-wrap gap-3 text-[11px]">
          <a className="underline" href="/demo/tabletop_push_synthetic.mp4" download>Download video (MP4)</a>
          <a className="underline" href="/demo/tabletop_push_synthetic.webm" download>WebM</a>
          <a className="underline" href="/demo/tabletop_video_extraction.json" download>event fixture</a>
          <a className="underline" href="/demo/tabletop_video_script.json" download>animation script</a>
        </div>
        <Caveat>
          Synthetic demonstration — scripted motion. The video shows events; it does not show why. Live video
          analysis: {liveReason}
        </Caveat>
      </div>

      <div className="flex flex-col gap-3">
        <Results
          stages={stages}
          input={
            <p className="text-xs leading-relaxed">
              {usingUpload ? (
                <>Your video <b>{upload.file!.name}</b> (not analysed) + manually supplied facts.</>
              ) : (
                <>
                  Synthetic video, frames <b>0 – {T} s</b> only (events replayed from a fixture, not live tracking). Decision
                  time T = {T} s. Action: {demo.action_labels[action]}.
                </>
              )}
            </p>
          }
          meaning={usingUpload ? manualMeaning(action, "video") : flow.meaning}
          meaningJson={usingUpload ? { manual_scene: manual.scene } : flow.meaning_json}
          scene={usingUpload ? manual.scene : flow.scene}
          sceneTag={usingUpload ? { text: "Manually supplied", tone: "assumed" } : { text: `Observed at T=${T}s`, tone: "observed" }}
          scenarios={flow.scenarios}
          selected={action}
          circles={usingUpload ? manualAcm?.circles ?? null : scenario.circles}
          acmJson={usingUpload ? { note: manualAcm?.note } : scenario.acm_json}
          circlesCaption={<p className="faint text-[11px]">{usingUpload ? manualAcm?.note : `For: ${scenario.label}. Actor pusher_01 is tracked in the frames up to T.`}</p>}
        />

        {!usingUpload && (phase === "revealing" || phase === "revealed") && (
          <section className="panel animate-rise p-4">
            <h3 className="mb-1 text-[13px] font-semibold">Predicted vs scripted outcome</h3>
            <p className="mb-3 text-[11px] text-warn-400">
              {flow.scripted_outcome.label}. This demonstrates the workflow, not independent validation of a learned
              model. {action !== "push_edge" && "The scripted video shows a push; compare with the push prediction."}
            </p>
            <div className="grid gap-3 lg:grid-cols-2">
              <TabletopScene
                entities={flow.scene.entities}
                table={[0, 0, 1.2, 0.8]}
                title="Predicted at T = 2.0 s (push)"
                tag={{ text: "Illustrative simulation", tone: "predicted" }}
                result={simulate(toSimScene(flow.scene), toSimAction(flow.scenarios.push_edge))}
              />
              <div className="flex flex-col gap-2">
                <TabletopScene
                  entities={flow.scripted_outcome.scene.entities}
                  table={[0, 0, 1.2, 0.8]}
                  title={`Scripted outcome at t = ${flow.scripted_outcome.t} s`}
                  tag={{ text: "Scripted outcome", tone: "scripted" }}
                  result={null}
                />
                <ul className="text-[11px]">
                  {flow.scripted_outcome.scene.relations.map((r) => (
                    <li key={r.subject}>
                      <StatusTag status={r.status} /> {r.subject} {r.relation} {r.object}
                      {r.subject === "blue_cup_01" && " — off the calibrated table plane: position not measurable"}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-4">
              <Metric label="Support state" value={metrics.support_state_accuracy === null ? "—" : `${metrics.support_state_accuracy * 100}% match`} />
              <Metric label="Fall events" value={`P ${metrics.fall_events.precision ?? "—"} · R ${metrics.fall_events.recall ?? "—"}`} />
              <Metric label="Position error" value={metrics.position_error_m.mean === null ? "—" : `${metrics.position_error_m.mean} m (n=${metrics.position_error_m.n})`} />
              <Metric label="Abstentions" value={`${metrics.abstentions.count} (landing position)`} />
            </div>
            <p className="faint mt-2 text-[11px]">{flow.comparison.notes.join(" ")} Predicted result in this browser: {predictedResult.events.filter((e) => e.kind !== "remains_supported").map((e) => `${e.kind}:${e.entity_id}`).join(", ") || "no change"}.</p>
          </section>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-raised px-3 py-2">
      <div className="eyebrow">{label}</div>
      <div className="num mt-1 text-sm font-semibold">{value}</div>
    </div>
  );
}
