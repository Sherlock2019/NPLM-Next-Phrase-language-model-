"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AdvantageCards } from "@/components/AdvantageCards";
import { CandidateComparison } from "@/components/CandidateComparison";
import { CandidateInspector } from "@/components/CandidateInspector";
import { ExpectedSlot } from "@/components/ExpectedSlot";
import { PhraseDna } from "@/components/PhraseDna";
import { SearchFunnel } from "@/components/SearchFunnel";
import { api, ApiError, ms } from "@/lib/api";
import {
  Caveat,
  ErrorBox,
  Field,
  Loading,
  Panel,
  Pill,
  buttonClass,
  buttonGhostClass,
  inputClass,
} from "@/components/ui";
import type { Candidate, ComparisonResponse, Preset } from "@/lib/types";

const DEFAULT_PROMPT = "The engineer deployed the application to AWS yesterday using";

export default function Playground() {
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [language, setLanguage] = useState("auto");
  const [style, setStyle] = useState("auto");
  const [topK, setTopK] = useState(100);
  const [target, setTarget] = useState("");
  const [demoMode, setDemoMode] = useState(false);

  const [result, setResult] = useState<ComparisonResponse | null>(null);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guards against an earlier request landing after a later one.
  const requestId = useRef(0);

  useEffect(() => {
    api
      .presets()
      .then((data) => setPresets(data.presets))
      .catch(() => setPresets([]));
  }, []);

  const run = useCallback(
    async (text: string, expected?: string) => {
      const id = ++requestId.current;
      setLoading(true);
      setError(null);
      try {
        const data = await api.compare({
          prompt: text,
          language: language === "auto" ? null : language,
          style: style === "auto" ? null : style,
          top_k: topK,
          display_k: 15,
          target: (expected ?? target).trim() || null,
        });
        if (id !== requestId.current) return;
        setResult(data);
        // Default the inspector to the candidate SPLM ranks first, which is the one
        // the reader is most likely asking about.
        setSelected(data.splm.candidates[0] ?? null);
      } catch (cause) {
        if (id !== requestId.current) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
        setResult(null);
      } finally {
        if (id === requestId.current) setLoading(false);
      }
    },
    [language, style, topK, target],
  );

  useEffect(() => {
    // One automatic run on first load so the page is never empty.
    void run(DEFAULT_PROMPT);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function applyPreset(preset: Preset) {
    setPrompt(preset.prompt);
    setLanguage(preset.language);
    void run(preset.prompt);
  }

  return (
    <div className="flex flex-col gap-4">
      <Hero />

      {/* Input ---------------------------------------------------------- */}
      <Panel
        title="Prompt"
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setDemoMode((value) => !value)}
              className={buttonGhostClass}
              title="Demo mode hides the engineering controls"
            >
              {demoMode ? "Research mode" : "Demo mode"}
            </button>
          </div>
        }
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run(prompt);
          }}
          className="flex flex-col gap-3"
        >
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={2}
            spellCheck={false}
            className={`${inputClass} resize-y font-mono text-sm leading-relaxed`}
            placeholder="Write an unfinished sentence, e.g. John will meet Sarah in"
          />

          {!demoMode && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Language">
                <select
                  value={language}
                  onChange={(event) => setLanguage(event.target.value)}
                  className={inputClass}
                >
                  <option value="auto">Auto-detect</option>
                  <option value="en">English</option>
                  <option value="fr">French</option>
                  <option value="vi">Vietnamese</option>
                </select>
              </Field>

              <Field label="Style">
                <select
                  value={style}
                  onChange={(event) => setStyle(event.target.value)}
                  className={inputClass}
                >
                  <option value="auto">Auto-detect</option>
                  {["casual", "business", "formal", "technical", "academic", "literary"].map(
                    (option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ),
                  )}
                </select>
              </Field>

              <Field label="Candidates re-scored (top-K)">
                <input
                  type="number"
                  min={5}
                  max={500}
                  value={topK}
                  onChange={(event) => setTopK(Number(event.target.value) || 100)}
                  className={inputClass}
                />
              </Field>

              <Field label="Expected continuation (optional)">
                <input
                  value={target}
                  onChange={(event) => setTarget(event.target.value)}
                  placeholder="e.g. Terraform"
                  className={inputClass}
                />
              </Field>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <button type="submit" className={buttonClass} disabled={loading}>
              {loading ? "Analysing…" : "Analyse & compare"}
            </button>
            <button
              type="button"
              className={buttonGhostClass}
              onClick={() => {
                setPrompt(DEFAULT_PROMPT);
                setTarget("");
                void run(DEFAULT_PROMPT);
              }}
            >
              Reset
            </button>

            {presets.length > 0 && (
              <div className="ml-auto flex flex-wrap items-center gap-1">
                <span className="faint mr-1 text-[10.5px] uppercase tracking-wide">
                  Presets
                </span>
                {presets
                  .filter((preset) => !demoMode || preset.language === "en")
                  .slice(0, demoMode ? 5 : 12)
                  .map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => applyPreset(preset)}
                      className="faint hairline rounded border px-2 py-1 text-[10.5px] transition-colors hover:text-[var(--text)]"
                      title={preset.prompt}
                    >
                      {preset.label}
                    </button>
                  ))}
              </div>
            )}
          </div>
        </form>
      </Panel>

      {error && <ErrorBox error={error} />}

      {loading && !result && (
        <Panel>
          <Loading label="Loading the parser and the base model (first run only)" />
        </Panel>
      )}

      {result && (
        <>
          <AdvantageCards result={result} />

          {/* Centrepiece: meaning, expectation and scoring, all at once. */}
          <div className="grid gap-4 xl:grid-cols-[1.15fr_1fr]">
            <Panel
              title="Phrase DNA"
              hint="What the sentence means so far. Dashed cards are information the text has not given."
            >
              <PhraseDna
                frame={result.phrase_frame}
                expectedSlot={result.expected_slots.top_slot}
              />
            </Panel>

            <Panel
              title="Expected next meaning"
              hint="Which kind of information SPLM expects next. A standard language model makes no such prediction."
            >
              <ExpectedSlot
                slots={result.expected_slots}
                frame={result.phrase_frame}
                text={result.prompt}
              />
            </Panel>
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.15fr_1fr]">
            <Panel
              title="Standard LLM vs SPLM"
              hint="One forward pass, two rankings. Click any candidate to see how it was scored."
              actions={
                <div className="flex items-center gap-1.5">
                  {result.changed_selection ? (
                    <Pill tone="splm">top choice changed</Pill>
                  ) : (
                    <Pill tone="neutral">same top choice</Pill>
                  )}
                </div>
              }
            >
              <CandidateComparison
                base={result.base.candidates}
                splm={result.splm.candidates}
                selected={selected?.token_id ?? null}
                onSelect={setSelected}
                limit={12}
              />
              {!result.changed_selection && (
                <Caveat>
                  SPLM re-ranked the candidates but did not change the top choice here.
                  That is a real outcome, not a failure to display one — the structural
                  effect shows in the ranking and in semantic focus.
                </Caveat>
              )}
            </Panel>

            <Panel
              title="Candidate score breakdown"
              hint="Every number is a feature the scorer actually used."
            >
              <CandidateInspector
                candidate={selected}
                expectedSlot={result.expected_slots.top_slot}
              />
            </Panel>
          </div>

          {!demoMode && (
            <div className="grid gap-4 xl:grid-cols-[1.15fr_1fr]">
              <Panel
                title="Next-word search"
                hint="How much of the vocabulary SPLM reasoned over, and at which stages."
              >
                <SearchFunnel search={result.search_space} focus={result.semantic_focus} />
              </Panel>

              <Panel title="Run detail" hint="For reproducing this exact result.">
                <RunDetail result={result} />
              </Panel>
            </div>
          )}

          {result.warnings.length > 0 && (
            <Panel title="Warnings">
              <ul className="flex flex-col gap-1.5">
                {result.warnings.map((warning, index) => (
                  <li key={index} className="text-[11px] leading-snug text-warn-400">
                    {warning}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}

function Hero() {
  return (
    <section className="panel relative overflow-hidden px-5 py-4">
      <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Understand meaning before predicting language
          </h1>
          <p className="dim mt-1.5 max-w-2xl text-xs leading-relaxed">
            A standard language model asks which token is statistically likely next.
            SPLM first asks what is happening, who is involved, and which kind of
            information is missing — then scores the same Transformer&apos;s candidates
            against that. Same model, same prompt, same hardware; only the structural
            layer differs.
          </p>
        </div>
        <FlowDiagram />
      </div>
    </section>
  );
}

/** The two pipelines side by side, so the difference reads in a few seconds. */
function FlowDiagram() {
  const baseSteps = ["Previous tokens", "Transformer", "Next-token probabilities"];
  const splmSteps = [
    "Previous tokens",
    "Language · lexicon · grammar",
    "Syntax · morphology",
    "Universal Phrase DNA",
    "Expected semantic slot",
    "Transformer candidates",
    "Linguistic scoring",
    "Adjusted probabilities",
  ];

  return (
    <div className="grid shrink-0 gap-3 sm:grid-cols-2 lg:w-[30rem]">
      <div className="flex flex-col gap-1">
        <span className="eyebrow text-base-400">Standard LLM</span>
        {baseSteps.map((step) => (
          <span
            key={step}
            className="hairline rounded border bg-base-500/6 px-2 py-1 text-[10.5px] leading-snug"
          >
            {step}
          </span>
        ))}
      </div>
      <div className="flex flex-col gap-1">
        <span className="eyebrow text-splm-400">SPLM</span>
        {splmSteps.map((step, index) => (
          <span
            key={step}
            className={`rounded border px-2 py-1 text-[10.5px] leading-snug ${
              index >= 1 && index <= 4
                ? "border-splm-500/30 bg-splm-500/8 text-splm-300"
                : "hairline border"
            }`}
          >
            {step}
          </span>
        ))}
      </div>
    </div>
  );
}

function RunDetail({ result }: { result: ComparisonResponse }) {
  const rows: [string, string][] = [
    ["Language", `${result.language}${result.style ? ` · ${result.style}` : ""}`],
    ["Config fingerprint", result.fingerprint],
    ["Slot predictor", result.expected_slots.backend],
    ["Slot-compatibility data", result.semantics_coverage],
    ["Frame completion", `${(result.frame_completion * 100).toFixed(0)}%`],
    ["Warm", result.warm ? "yes" : "no — includes loading"],
  ];

  return (
    <div className="flex flex-col gap-3">
      <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-2">
            <dt className="faint text-[11px]">{label}</dt>
            <dd className="num truncate text-[11px]" title={value}>
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <div className="hairline border-t pt-3">
        <h3 className="eyebrow mb-1.5">Time per prediction</h3>
        <div className="flex flex-col gap-1">
          {Object.entries(result.timings_ms).map(([stage, value]) => (
            <div key={stage} className="flex items-center gap-2">
              <span className="dim w-36 shrink-0 text-[11px]">
                {stage.replace(/_/g, " ")}
              </span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/6">
                <div
                  className="animate-bar h-full rounded-full bg-splm-500/70"
                  style={{
                    width: `${Math.min(100, (value / result.total_latency_ms) * 100)}%`,
                  }}
                />
              </div>
              <span className="num w-16 shrink-0 text-right text-[10.5px]">
                {ms(value)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <button
        type="button"
        className={buttonGhostClass}
        onClick={() => {
          void navigator.clipboard.writeText(
            JSON.stringify(
              {
                prompt: result.prompt,
                language: result.language,
                style: result.style,
                fingerprint: result.fingerprint,
                expected_slot: result.expected_slots.top_slot,
                timings_ms: result.timings_ms,
              },
              null,
              2,
            ),
          );
        }}
      >
        Copy experiment config
      </button>
    </div>
  );
}
