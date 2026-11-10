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

export default function ScenePage() {
  const [bundle, setBundle] = useState<SceneBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState({ section: 0, all: false });

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const id = (q.get("scene") ?? "car_sale").replace(/[^a-z0-9_]/g, "");
    setView({ section: Math.max("ABCDEF".indexOf((q.get("section") ?? "A").toUpperCase()), 0), all: q.get("all") === "1" });
    fetch(`/demo/scene_${id}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`scene_${id}.json: ${r.status}`))))
      .then(setBundle)
      .catch((e: Error) => setError(`The scene could not be loaded (${e.message}). Generate it with \`acm scene bundle ${id} -o web/public/demo/scene_${id}.json\` or run ACM's ./start.sh.`));
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!bundle) return <Loading label="Loading the scene" />;
  return <SceneDemo b={bundle} initialStage={view.section} initialAll={view.all} />;
}
