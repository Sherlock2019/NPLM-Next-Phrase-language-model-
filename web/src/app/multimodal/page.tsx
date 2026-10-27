"use client";

/**
 * TEXT / IMAGE / VIDEO -> MLM -> ACM -> VISUAL CONSEQUENCES.
 *
 * Demo mode replays bundled fixtures through results computed by the real
 * pipeline (`acm demo --json`). Live mode is offered per tab only when
 * /api/multimodal/status reports that tab's backends as available.
 */

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ErrorBox, Loading } from "@/components/ui";
import { ImageTab } from "@/components/multimodal/ImageTab";
import { TextTab } from "@/components/multimodal/TextTab";
import { VideoTab } from "@/components/multimodal/VideoTab";
import { HowItWorks } from "@/components/acm/HowItWorks";
import type { DemoBundle, LiveStatus, VideoScript } from "@/lib/multimodal/types";

const TABS = [
  { key: "text", title: "Text → MLM → ACM", blurb: "A sentence states a plan." },
  { key: "image", title: "Image → MLM → ACM", blurb: "A picture shows a scene." },
  { key: "video", title: "Video → MLM → ACM", blurb: "A clip shows events over time." },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function MultimodalPage() {
  const [demo, setDemo] = useState<DemoBundle | null>(null);
  const [script, setScript] = useState<VideoScript | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [statusNote, setStatusNote] = useState("checking…");
  const [mode, setMode] = useState<"demo" | "live">("demo");
  const [tab, setTab] = useState<TabKey>("text");
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    Promise.all([
      fetch("/demo/demo_results.json").then((r) => (r.ok ? r.json() : Promise.reject(new Error(`demo_results.json: ${r.status}`)))),
      fetch("/demo/tabletop_video_script.json").then((r) => (r.ok ? r.json() : Promise.reject(new Error(`video script: ${r.status}`)))),
    ])
      .then(([bundle, videoScript]) => {
        setDemo(bundle as DemoBundle);
        setScript(videoScript as VideoScript);
      })
      .catch((e: Error) => setLoadError(`Bundled demo material could not be loaded: ${e.message}`));
    fetch("/api/multimodal/status")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((s: LiveStatus) => {
        setStatus(s);
        setStatusNote("");
      })
      .catch(() => setStatusNote("the MLM API is not reachable, so no live backend is available"));
  }, []);

  const liveFor = (key: TabKey) => mode === "live" && Boolean(status?.live[key]);
  const reasonFor = (key: TabKey) => status?.reasons[key] ?? statusNote;
  const anyLive = Boolean(status && Object.values(status.live).some(Boolean));

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = TABS[(index + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length].key;
    setTab(next);
    tabRefs.current[next]?.focus();
  }

  return (
    <div className="flex flex-col gap-5">
      <div
        className="sticky top-[60px] z-30 flex flex-wrap items-center gap-2 rounded-lg bg-fuchsia-700 px-3 py-2 text-xs font-semibold text-white shadow"
        role="status"
      >
        {mode === "demo" || !liveFor(tab) ? (
          <span>Demo mode — example extraction and simulated consequences</span>
        ) : (
          <span>Live mode — MLM parser and ACM running on your input (positions still assumed)</span>
        )}
        <span className="ml-auto font-normal opacity-90">Fixture playback is not live YOLO, Qwen or MLM inference.</span>
      </div>

      <header className="flex flex-wrap items-end gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold tracking-tight">Multimodal consequences</h1>
          <p className="dim mt-1 text-[13px]">
            Observe → Understand meaning (MLM) → Evaluate consequences (ACM) → Visualize. Text, images and video become
            one shared MLM meaning; ACM reads that meaning, not a vision model&apos;s prose.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="panel-raised flex p-0.5" role="radiogroup" aria-label="Demo or live mode">
            {(["demo", "live"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={mode === m}
                disabled={m === "live" && !anyLive}
                onClick={() => setMode(m)}
                className={`rounded px-3 py-1 text-xs font-semibold capitalize disabled:cursor-not-allowed disabled:opacity-40 ${
                  mode === m ? "bg-splm-500 text-ink-950" : "dim"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          <span className="faint max-w-xs text-right text-[10.5px]">
            {anyLive
              ? `Live available for: ${Object.entries(status!.live).filter(([, v]) => v).map(([k]) => k).join(", ")}`
              : `Live disabled: ${statusNote || "no live backend available"}`}
          </span>
        </div>
      </header>

      <div role="tablist" aria-label="Input type" className="grid gap-3 sm:grid-cols-3">
        {TABS.map((t, i) => (
          <button
            key={t.key}
            ref={(el) => {
              tabRefs.current[t.key] = el;
            }}
            role="tab"
            id={`tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`panel-${t.key}`}
            tabIndex={tab === t.key ? 0 : -1}
            onClick={() => setTab(t.key)}
            onKeyDown={(e) => onTabKey(e, i)}
            className={`panel px-4 py-3 text-left transition-colors ${tab === t.key ? "ring-2 ring-splm-500/60" : "hover:bg-white/4"}`}
          >
            <div className="text-[14px] font-semibold">{t.title}</div>
            <div className="faint mt-0.5 text-[11.5px]">{t.blurb}</div>
            <div className="mt-1.5 text-[10.5px]">
              {mode === "live" && status?.live[t.key] ? (
                <span className="text-ok-400">LIVE available</span>
              ) : (
                <span className="text-warn-400">DEMO · built-in example</span>
              )}
            </div>
          </button>
        ))}
      </div>

      <HowItWorks key={tab} inputs={[tab === "text" ? "phrase" : tab]} page="multimodal" />

      {loadError && <ErrorBox error={loadError} />}
      {!demo || !script ? (
        !loadError && <Loading label="Loading bundled examples" />
      ) : (
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
          {tab === "text" && <TextTab demo={demo} live={liveFor("text")} liveReason={reasonFor("text")} />}
          {tab === "image" && <ImageTab demo={demo} liveReason={reasonFor("image")} />}
          {tab === "video" && <VideoTab demo={demo} script={script} liveReason={reasonFor("video")} />}
        </div>
      )}
    </div>
  );
}
