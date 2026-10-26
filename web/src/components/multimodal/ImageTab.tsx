"use client";

import { useMemo, useState } from "react";
import { buttonClass, buttonGhostClass, inputClass, Caveat, ErrorBox } from "@/components/ui";
import type { ActionKey, DemoBundle } from "@/lib/multimodal/types";
import { ACTION_KEYS } from "@/lib/multimodal/types";
import { DEFAULT_FACTS, DemoUploadNotice, ManualFactsForm, manualScene, UploadField, useUpload } from "./Inputs";
import { manualCircles, manualMeaning } from "./manual";
import { Results, useStagedRun } from "./Results";

export function ImageTab({ demo, liveReason }: { demo: DemoBundle; liveReason: string }) {
  const flow = demo.flows.image;
  const upload = useUpload("image");
  const [annotated, setAnnotated] = useState(false);
  const [actionText, setActionText] = useState("Push the cup toward the edge.");
  const [action, setAction] = useState<ActionKey>("push_edge");
  const [facts, setFacts] = useState(DEFAULT_FACTS);
  const { stages, running, run, reset } = useStagedRun();
  const usingUpload = upload.file !== null;
  const manual = useMemo(() => manualScene(facts), [facts]);
  const manualAcm = useMemo(
    () => (usingUpload && manual.errors.length === 0 ? manualCircles(flow.scenarios, manual.sim, action) : null),
    [usingUpload, manual, flow.scenarios, action],
  );
  const canRun = !usingUpload || manual.errors.length === 0;
  const scenario = flow.scenarios[action];

  function loadExample() {
    upload.clear();
    setFacts(DEFAULT_FACTS);
    setActionText("Push the cup toward the edge.");
    setAction("push_edge");
    reset();
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(320px,420px)_1fr]">
      <div className="panel flex flex-col gap-3 p-4">
        <figure className="panel-raised overflow-hidden">
          {usingUpload && upload.url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={upload.url} alt="Your uploaded image (preview only, not analysed)" className="block max-h-72 w-full object-contain" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={annotated ? "/demo/tabletop_scene_annotated.svg" : "/demo/tabletop_scene.svg"}
              alt={annotated ? "Sample tabletop scene with demo-fixture boxes and relations" : "Sample tabletop scene: blue cup near the right edge, red cup near the center"}
              className="block w-full"
            />
          )}
          <figcaption className="faint hairline border-t px-3 py-1.5 text-[11px]">
            {usingUpload
              ? `Your upload: ${upload.file!.name} — preview only`
              : annotated
                ? "Annotated: boxes and relations are a Demo fixture, not live model detections."
                : "Built-in sample: schematic top-down illustration (synthetic)."}
          </figcaption>
        </figure>
        {!usingUpload && (
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={annotated} onChange={(e) => setAnnotated(e.target.checked)} />
            Show demo-fixture annotations (boxes and spatial relations)
          </label>
        )}
        <UploadField kind="image" upload={upload} onChange={reset} />
        {usingUpload && (
          <>
            <DemoUploadNotice kind="image" />
            <ManualFactsForm facts={facts} onChange={(f) => { setFacts(f); reset(); }} />
            {manual.errors.length > 0 && <ErrorBox error={manual.errors.join("; ")} />}
          </>
        )}
        <label className="flex flex-col gap-1">
          <span className="eyebrow">Proposed action (separate from what the image shows)</span>
          <input className={inputClass} value={actionText} onChange={(e) => { setActionText(e.target.value); reset(); }} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="faint text-[11px]">Action parameters used by the simulator (demo mode does not parse free text)</span>
          <select className={inputClass} value={action} onChange={(e) => { setAction(e.target.value as ActionKey); reset(); }}>
            {ACTION_KEYS.map((k) => (
              <option key={k} value={k}>
                {demo.action_labels[k]}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={buttonClass} disabled={!canRun || running} onClick={() => run()}>
            {running ? "Running…" : "Run Image Demo"}
          </button>
          <button type="button" className={buttonGhostClass} onClick={loadExample}>
            Load Example
          </button>
          <button type="button" className={buttonGhostClass} onClick={reset}>
            Reset
          </button>
        </div>
        <div className="flex flex-wrap gap-3 text-[11px]">
          <a className="underline" href="/demo/tabletop_scene.svg" download>Download sample image</a>
          <a className="underline" href="/demo/tabletop_scene_annotated.svg" download>annotated version</a>
          <a className="underline" href="/demo/tabletop_image_extraction.json" download>extraction fixture</a>
        </div>
        <Caveat>
          An image can establish “cup near edge”. It cannot establish that anyone pushed it, intends to, or owns it —
          those claims are rejected, not guessed. Live image analysis: {liveReason}
        </Caveat>
      </div>

      <Results
        stages={stages}
        input={
          <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <p className="text-xs leading-relaxed">
              {usingUpload ? (
                <>Your image <b>{upload.file!.name}</b> (not analysed) + manually supplied facts.</>
              ) : (
                <>Built-in image <b>tabletop_scene.svg</b>, extraction replayed from a fixture ({String((flow.input.replay as { name: string }).name)}) — not live inference.</>
              )}
              <br />
              Proposed action: “{actionText}” → {demo.action_labels[action]}
            </p>
          </div>
        }
        meaning={usingUpload ? manualMeaning(action, "image") : flow.meaning}
        meaningJson={usingUpload ? { manual_scene: manual.scene, note: "manually supplied" } : flow.meaning_json}
        scene={usingUpload ? manual.scene : flow.scene}
        sceneTag={usingUpload ? { text: "Manually supplied", tone: "assumed" } : { text: "Observed (fixture replay)", tone: "observed" }}
        scenarios={flow.scenarios}
        selected={action}
        circles={usingUpload ? manualAcm?.circles ?? null : scenario.circles}
        acmJson={usingUpload ? { note: manualAcm?.note } : scenario.acm_json}
        circlesCaption={<p className="faint text-[11px]">{usingUpload ? manualAcm?.note : `For: ${scenario.label}.`}</p>}
      />
    </div>
  );
}
