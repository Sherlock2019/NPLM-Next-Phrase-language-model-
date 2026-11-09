"use client";

import { useState } from "react";
import { buttonClass, buttonGhostClass, inputClass, Caveat } from "@/components/ui";
import type { ActionKey, DemoBundle, Meaning, Scenario, SceneData } from "@/lib/multimodal/types";
import { ACTION_KEYS } from "@/lib/multimodal/types";
import { ErrorBox } from "@/components/ui";
import { Results, useStagedRun } from "./Results";

const EXAMPLES = {
  tabletop: "tabletop",
  sale: "sale",
} as const;
type Example = keyof typeof EXAMPLES;

interface LiveResult {
  meaning: Meaning;
  meaning_json: unknown;
  scenario: Scenario;
  scene: SceneData;
}

export function TextTab({ demo, live, liveReason }: { demo: DemoBundle; live: boolean; liveReason: string }) {
  const tabletopText = demo.flows.text.input.text as string;
  const sale = demo.flows.sale;
  const saleText = [...sale.input.context, sale.input.text].join(" ");
  const [example, setExample] = useState<Example>("tabletop");
  const [text, setText] = useState(tabletopText);
  const [action, setAction] = useState<ActionKey>("push_edge");
  const [liveResult, setLiveResult] = useState<LiveResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { stages, running, run, reset } = useStagedRun();

  const exampleText = example === "tabletop" ? tabletopText : saleText;
  const isExample = text.trim() === exampleText;
  const canRun = live ? text.trim().length > 0 && example === "tabletop" : isExample;

  function changed() {
    reset();
    setLiveResult(null);
    setError(null);
  }

  function load(next: Example) {
    setExample(next);
    setText(next === "tabletop" ? tabletopText : saleText);
    changed();
  }

  async function runDemo() {
    if (running || !canRun) return;
    setError(null);
    if (!live) {
      run();
      return;
    }
    try {
      const response = await fetch("/api/multimodal/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, action }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.detail ?? `${response.status}`);
      setLiveResult(body as LiveResult);
      run();
    } catch (e) {
      setError(`Live run failed: ${(e as Error).message}`);
    }
  }

  const flow = demo.flows.text;
  const isSale = example === "sale";
  const scenarios = liveResult ? { ...flow.scenarios, [action]: liveResult.scenario } : flow.scenarios;
  const meaning = isSale ? sale.meaning : liveResult?.meaning ?? flow.meaning;
  const scenario = scenarios[action];

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(320px,420px)_1fr]">
      <div className="panel flex flex-col gap-3 p-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Load example">
          <button type="button" className={buttonGhostClass} aria-pressed={example === "tabletop"} onClick={() => load("tabletop")}>
            Load Example: tabletop push
          </button>
          <button type="button" className={buttonGhostClass} aria-pressed={example === "sale"} onClick={() => load("sale")}>
            Load Example: car sale (ACM rules)
          </button>
        </div>
        <label className="flex flex-col gap-1">
          <span className="eyebrow">Text input</span>
          <textarea
            className={`${inputClass} min-h-28 text-[13px] leading-relaxed`}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              changed();
            }}
          />
        </label>
        {!live && !isExample && (
          <p className="text-[11px] text-warn-400">
            Edited text cannot be parsed in demo mode (no parser model). Load the example again, or switch to Live
            when the MLM parser is available.
          </p>
        )}
        {!isSale && (
          <fieldset className="flex flex-col gap-1.5">
            <legend className="eyebrow mb-1">Proposed action</legend>
            {ACTION_KEYS.map((k) => (
              <label key={k} className="flex items-center gap-2 text-xs">
                <input type="radio" name="text-action" checked={action === k} onChange={() => { setAction(k); changed(); }} />
                {k === "none" ? "Do nothing" : k === "push_edge" ? "Push the blue cup toward the edge" : "Move the blue cup toward the center"}
              </label>
            ))}
          </fieldset>
        )}
        {isSale && (
          <p className="dim text-[11px]">
            Context: “{sale.input.context.join("” “")}” — action: “{sale.input.text}”. Ownership and payment changes are
            rule-derived consequences.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="button" className={buttonClass} disabled={!canRun || running} onClick={runDemo}>
            {running ? "Running…" : "Run Text Demo"}
          </button>
          <button type="button" className={buttonGhostClass} onClick={() => { changed(); }}>
            Reset
          </button>
          <a className={buttonGhostClass} href="/demo/tabletop_text.txt" download>
            Download Example Material
          </a>
        </div>
        {live ? (
          <Caveat>Live: the MLM parser and ACM run on your text. Positions are still assumed — text gives no geometry.</Caveat>
        ) : (
          <Caveat>
            Demo: frames are built by MLM&apos;s phrase builder from hand-written parse trees; consequences come from
            ACM and the tabletop simulator. {liveReason && `Live text: ${liveReason}`}
          </Caveat>
        )}
        {error && <ErrorBox error={error} />}
      </div>

      <Results
        stages={stages}
        input={
          <blockquote className="border-l-2 border-splm-500/50 pl-3 text-[13px] leading-relaxed">
            {text}
            <footer className="faint mt-1 text-[11px]">Evidence type: text — it states a plan; it shows nothing.</footer>
          </blockquote>
        }
        meaning={meaning}
        meaningJson={isSale ? sale.meaning_json : liveResult?.meaning_json ?? flow.meaning_json}
        scene={isSale ? null : liveResult?.scene ?? flow.scene}
        sceneTag={{ text: "Positions assumed (text has no geometry)", tone: "assumed" }}
        scenarios={isSale ? null : scenarios}
        selected={action}
        circles={isSale ? sale.circles : scenario?.circles ?? null}
        acmJson={isSale ? sale.acm_json : scenario?.acm_json}
        circlesCaption={
          <p className="faint text-[11px]">
            {isSale
              ? sale.note
              : `For: ${scenario?.label}. Simulated changes come from the constrained tabletop simulator; rule-derived ones from ACM's packs.`}
          </p>
        }
        noScene={isSale ? "No physical scene: this example shows ACM's rule-derived ownership and payment consequences, not tabletop physics." : undefined}
      />
    </div>
  );
}
