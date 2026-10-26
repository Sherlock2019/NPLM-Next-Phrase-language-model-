"use client";

/**
 * Uploads and manually supplied scene facts.
 *
 * Uploaded media is previewed only. Demo mode never analyses it and never shows a
 * built-in result as if it came from the upload. Object URLs are revoked when the
 * file changes or the component unmounts. Media is displayed with <img>/<video>,
 * so nothing embedded in it (an SVG script, a caption) is executed.
 */

import { useEffect, useState } from "react";
import { validateScene, type SimScene } from "@/lib/multimodal/tabletop";
import type { SceneData } from "@/lib/multimodal/types";
import { inputClass } from "@/components/ui";

export const UPLOAD_LIMITS = {
  image: { types: ["image/png", "image/jpeg", "image/webp", "image/svg+xml"], maxBytes: 10 * 1024 * 1024, label: "PNG, JPEG, WebP or SVG up to 10 MB" },
  video: { types: ["video/mp4", "video/webm"], maxBytes: 50 * 1024 * 1024, label: "MP4 or WebM up to 50 MB" },
} as const;

export function useUpload(kind: keyof typeof UPLOAD_LIMITS) {
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl); // released when the file changes or on unmount
  }, [file]);

  function choose(next: File | null) {
    setError(null);
    if (!next) {
      setFile(null);
      return;
    }
    const limit = UPLOAD_LIMITS[kind];
    if (!(limit.types as readonly string[]).includes(next.type)) {
      setError(`Unsupported file type ${next.type || "(unknown)"}. Allowed: ${limit.label}.`);
      return;
    }
    if (next.size > limit.maxBytes) {
      setError(`File is ${(next.size / 1024 / 1024).toFixed(1)} MB; the limit is ${limit.label}.`);
      return;
    }
    setFile(next);
  }

  return { file, url, error, choose, clear: () => choose(null) };
}

export function UploadField({
  kind,
  upload,
  onChange,
}: {
  kind: keyof typeof UPLOAD_LIMITS;
  upload: ReturnType<typeof useUpload>;
  onChange?: () => void;
}) {
  const limit = UPLOAD_LIMITS[kind];
  return (
    <div className="flex flex-col gap-1.5">
      <label className="flex flex-wrap items-center gap-2 text-xs">
        <span className="eyebrow">Upload your own {kind}</span>
        <input
          type="file"
          accept={limit.types.join(",")}
          className="text-[11px] file:mr-2 file:rounded file:border-0 file:bg-white/10 file:px-2 file:py-1 file:text-[11px]"
          onChange={(e) => {
            upload.choose(e.target.files?.[0] ?? null);
            onChange?.();
            e.target.value = "";
          }}
        />
        {upload.file && (
          <button type="button" className="dim text-[11px] underline" onClick={() => { upload.clear(); onChange?.(); }}>
            remove upload
          </button>
        )}
      </label>
      <span className="faint text-[10.5px]">{limit.label}. Stays in your browser; nothing is uploaded to a server.</span>
      {upload.error && <span className="text-[11px] text-danger-400">{upload.error}</span>}
    </div>
  );
}

export function DemoUploadNotice({ kind }: { kind: string }) {
  return (
    <div className="rounded-lg border border-warn-400/30 bg-warn-400/8 px-3 py-2 text-xs leading-relaxed text-warn-400">
      Automatic analysis of your {kind} is unavailable in demo mode. It is shown for preview only and has
      <b> not </b>been analysed. Run the built-in example, or supply the scene facts below by hand — they will be
      labelled <b>manually supplied</b>.
    </div>
  );
}

export interface ManualFacts {
  blue: [number, number];
  red: [number, number];
  radius: number;
}

export const DEFAULT_FACTS: ManualFacts = { blue: [1.05, 0.4], red: [0.55, 0.45], radius: 0.04 };

export function manualScene(f: ManualFacts): { scene: SceneData; sim: SimScene; errors: string[] } {
  const sim: SimScene = {
    table: [0, 0, 1.2, 0.8],
    objects: [
      { id: "blue_cup_01", x: f.blue[0], y: f.blue[1], r: f.radius },
      { id: "red_cup_01", x: f.red[0], y: f.red[1], r: f.radius },
    ],
  };
  const supplied = ["supplied:manual-entry"];
  const scene: SceneData = {
    timestamp_s: null,
    entities: [
      { id: "table_01", class: "table", attributes: {}, status: "assumed", position: null, radius_m: null, extent: [0, 0, 1.2, 0.8], evidence: supplied },
      { id: "blue_cup_01", class: "cup", attributes: { color: "blue" }, status: "assumed", position: f.blue, radius_m: f.radius, extent: null, evidence: supplied },
      { id: "red_cup_01", class: "cup", attributes: { color: "red" }, status: "assumed", position: f.red, radius_m: f.radius, extent: null, evidence: supplied },
    ],
    relations: [],
  };
  return { scene, sim, errors: validateScene(sim) };
}

export function ManualFactsForm({ facts, onChange }: { facts: ManualFacts; onChange: (f: ManualFacts) => void }) {
  const num = (value: string) => Number.parseFloat(value);
  const field = (label: string, value: number, set: (v: number) => void) => (
    <label className="flex flex-col gap-0.5">
      <span className="faint text-[10.5px]">{label}</span>
      <input
        type="number"
        step="0.01"
        className={`${inputClass} num w-24`}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => set(num(e.target.value))}
      />
    </label>
  );
  return (
    <fieldset className="panel-raised flex flex-col gap-2 px-3 py-2">
      <legend className="eyebrow px-1">Manually supplied scene facts (world metres, table 1.2 × 0.8 m)</legend>
      <div className="flex flex-wrap gap-3">
        {field("blue_cup_01 x (m)", facts.blue[0], (v) => onChange({ ...facts, blue: [v, facts.blue[1]] }))}
        {field("blue_cup_01 y (m)", facts.blue[1], (v) => onChange({ ...facts, blue: [facts.blue[0], v] }))}
        {field("red_cup_01 x (m)", facts.red[0], (v) => onChange({ ...facts, red: [v, facts.red[1]] }))}
        {field("red_cup_01 y (m)", facts.red[1], (v) => onChange({ ...facts, red: [facts.red[0], v] }))}
        {field("cup radius (m)", facts.radius, (v) => onChange({ ...facts, radius: v }))}
      </div>
    </fieldset>
  );
}
