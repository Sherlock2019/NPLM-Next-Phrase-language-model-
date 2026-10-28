"use client";

/**
 * Image / Video Chat: the image/video workflow on its own page.
 *   scene (image or video)  ->  recognise objects + build the world from the object libraries
 *   ->  the action  ->  simulate the consequences  ->  replay + ARM + chat about any object.
 * The physics lab does the work (components/acm/PhysicsLab.tsx); this page gives it full width
 * and lets you switch between the demo image and the demo video.
 */

import { useEffect, useState } from "react";
import { ErrorBox, Loading } from "@/components/ui";
import { PhysicsLab } from "@/components/acm/PhysicsLab";
import type { DemoBundle } from "@/lib/multimodal/types";

const SOURCES = [
  { key: "image", title: "Image", blurb: "A still picture of the scene: a blue cup near the table edge, a red cup farther in." },
  { key: "video", title: "Video", blurb: "A clip: a hand moves toward the blue cup and pushes it (scene at T = 2 s)." },
] as const;
type SourceKey = (typeof SOURCES)[number]["key"];

export default function SceneChatPage() {
  const [demo, setDemo] = useState<DemoBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<SourceKey>("image");

  useEffect(() => {
    // /acm/scene?source=video opens on the video (the home page links here)
    if (new URLSearchParams(window.location.search).get("source") === "video") setSource("video");
    fetch("/demo/demo_results.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`demo_results.json ${r.status}`))))
      .then(setDemo)
      .catch((e: Error) => setError(`Bundled demo material could not be loaded: ${e.message}`));
  }, []);

  return (
    <div className="flex flex-col gap-5">
      <header className="panel flex flex-col gap-2 p-5 sm:p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Image / Video Chat</h1>
        <p className="dim max-w-4xl text-[13.5px] leading-relaxed">
          From scene understanding to simulated consequences. Pick a scene, let the model recognise its objects and build the world from the
          object libraries, choose an action (or ask for one in the chat), and watch the physics engine simulate what would happen — then ask
          about any object.
        </p>
      </header>

      <div role="tablist" aria-label="Scene source" className="grid gap-3 sm:grid-cols-2">
        {SOURCES.map((s) => (
          <button key={s.key} type="button" role="tab" aria-selected={source === s.key} onClick={() => setSource(s.key)}
            className={`panel px-4 py-3 text-left transition-colors ${source === s.key ? "ring-2 ring-splm-500/60" : "hover:bg-white/4"}`}>
            <div className="text-[15px] font-semibold">{s.title}</div>
            <div className="faint mt-0.5 text-[12px]">{s.blurb}</div>
          </button>
        ))}
      </div>

      {error && <ErrorBox error={error} />}
      {!demo ? (
        !error && <Loading label="Loading the demo scenes" />
      ) : (
        <div className="flex flex-col gap-4">
          {source === "video" && (
            <section className="panel flex flex-col gap-2 p-3 sm:flex-row sm:items-start">
              <video controls playsInline muted preload="metadata" className="w-full max-w-md rounded-md"
                aria-label="Synthetic video: a pusher pushes the blue cup toward the edge">
                <source src="/demo/tabletop_push_synthetic.webm" type="video/webm" />
                <source src="/demo/tabletop_push_synthetic.mp4" type="video/mp4" />
              </video>
              <p className="dim text-[12.5px] leading-relaxed">
                The lab below works on the scene at <b>T = 2 s</b>, just before the push: the hand (pusher_01) is touching the blue cup.
                Synthetic clip with scripted motion; the objects are replayed from a fixture, not tracked live.
              </p>
            </section>
          )}
          <section className="panel p-3 sm:p-4">
            <PhysicsLab
              key={source}
              scene={source === "image" ? demo.flows.image.scene : demo.flows.video.scene}
              mode={source}
              defaultTarget="blue_cup_01"
              actor={source === "image" ? "you (proposed action)" : "pusher_01"}
            />
          </section>
        </div>
      )}
    </div>
  );
}
