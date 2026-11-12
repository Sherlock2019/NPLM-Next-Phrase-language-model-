"use client";

/**
 * ACM scene engine demo: /acm/scenario (car_sale) or /acm/scenario?scene=<id>.
 * Deep links: ?section=A..F opens a section, ?all=1 shows every section.
 * Reads public/demo/scene_<id>.json, written by the ACM scene engine (acm demo --json, which
 * ./start.sh runs). Static data: no API, key or model needed.
 */

import { useEffect, useState } from "react";
import { ErrorBox, Loading } from "@/components/ui";
import { SceneDemo } from "@/components/acm/script/SceneDemo";
import type { SceneBundle } from "@/lib/acm/scene";

/**
 * The scenes in ACM's scenes/ folder (bundled into public/demo by `acm demo --json`). Each is one
 * origin actor and one action; `where` is the world the action happens in (its WHERE).
 */
const SCENES: { id: string; label: string; actor: string; where: string }[] = [
  { id: "car_sale", label: "The car sale", actor: "Mark offers Sarah's car to Florence", where: "🏛️ economy" },
  { id: "iphone_gift", label: "The iPhone 18", actor: "Mark offers Sarah a new iPhone 18", where: "🏛️ economy" },
  { id: "beach_post", label: "The beach photo", actor: "Sarah posts Mark's sick-day photo on Facebook", where: "💻 digital" },
  { id: "park_ball", label: "The ball in the park", actor: "Leo throws a ball; a window breaks", where: "⚙️ physical" },
  { id: "factory_protest", label: "The protest", actor: "Florence joins a street protest", where: "🗳️ politics" },
  { id: "ev_purchase", label: "The electric car", actor: "Karim buys an electric car on a loan", where: "🏛️ economy" },
  { id: "job_loss", label: "The layoff", actor: "Claire lays Mark off", where: "🏭 business" },
  { id: "lottery_win", label: "The lottery win", actor: "Sarah tells Mark she won €1 million", where: "🏛️ economy" },
];

function ScenePicker({ current }: { current: string }) {
  return (
    <nav aria-label="Scenes" className="mb-4 flex flex-col gap-2">
      <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-cyan-500">
        Scenes · 1 actor · 1 action = consequences in cascade
      </p>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {SCENES.map((s) => (
          <li key={s.id}>
            <a href={`/acm/scenario?scene=${s.id}`} aria-current={s.id === current ? "page" : undefined}
              className={`panel-raised flex h-full flex-col gap-0.5 rounded-lg p-2.5 text-left ring-1 transition hover:ring-cyan-400 ${s.id === current ? "ring-2 ring-cyan-500" : "ring-black/5"}`}>
              <span className="text-[13px] font-semibold">{s.label}</span>
              <span className="dim text-[11.5px] leading-snug">{s.actor}</span>
              <span className="faint text-[10.5px]">WHERE: {s.where}</span>
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export default function ScenePage() {
  const [bundle, setBundle] = useState<SceneBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState({ section: 0, all: false });
  const [current, setCurrent] = useState("car_sale");

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const id = (q.get("scene") ?? "car_sale").replace(/[^a-z0-9_]/g, "");
    setCurrent(id);
    setView({ section: Math.max("ABCDEF".indexOf((q.get("section") ?? "A").toUpperCase()), 0), all: q.get("all") === "1" });
    fetch(`/demo/scene_${id}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`scene_${id}.json: ${r.status}`))))
      .then(setBundle)
      .catch((e: Error) => setError(`The scene could not be loaded (${e.message}). Generate it with \`acm scene bundle ${id} -o web/public/demo/scene_${id}.json\` or run ACM's ./start.sh.`));
  }, []);

  return (
    <>
      <ScenePicker current={current} />
      {error ? <ErrorBox error={error} /> : !bundle ? <Loading label="Loading the scene" /> : (
        <SceneDemo key={current} b={bundle} initialStage={view.section} initialAll={view.all} />
      )}
    </>
  );
}
