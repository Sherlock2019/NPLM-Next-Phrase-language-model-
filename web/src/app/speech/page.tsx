"use client";

/**
 * Speech Lab: talk to the model.
 *
 *   microphone -> Whisper ASR -> (Phrase DNA validation) -> base LLM | NPLM -> TTS -> speaker
 *
 * Everything shown is returned by /api/speech/turn for this recording: the transcript
 * and n-best, the Phrase DNA sort, the answer and its audio, and per-stage timings.
 * "Compare all" runs the three modes on the same recognition result.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { DnaSort } from "@/components/speech/DnaSort";
import { ApiError, ms } from "@/lib/api";
import {
  LANGUAGE_LABELS,
  MODE_LABELS,
  blobToBase64,
  speechApi,
  type SpeechBenchmarkReport,
  type SpeechLanguage,
  type SpeechMode,
  type SpeechStatus,
  type SpeechTurn,
  type TurnResponse,
} from "@/lib/speech";
import {
  Caveat,
  Empty,
  ErrorBox,
  Loading,
  Panel,
  Pill,
  Stat,
  buttonClass,
  buttonGhostClass,
  inputClass,
} from "@/components/ui";

const MODES: SpeechMode[] = ["base", "nplm", "nplm_validated"];
const EXAMPLES: Record<SpeechLanguage, string> = {
  en: "Book a meeting with Sarah tomorrow.",
  fr: "Jean rencontrera Sarah à Paris demain.",
  vi: "Ngày mai John sẽ gặp Sarah ở Hà Nội.",
};

export default function SpeechLabPage() {
  const [status, setStatus] = useState<SpeechStatus | null>(null);
  const [warming, setWarming] = useState(false);
  const [language, setLanguage] = useState<SpeechLanguage | "auto">("en");
  const [mode, setMode] = useState<SpeechMode | "compare">("nplm_validated");
  const [text, setText] = useState(EXAMPLES.en);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TurnResponse | null>(null);
  const [view, setView] = useState<SpeechMode>("nplm_validated");
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const secure = typeof window === "undefined" || window.isSecureContext;
  const micSupported = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  useEffect(() => {
    speechApi.status().then(setStatus).catch((cause) =>
      setStatus({ available: false, reason: cause instanceof ApiError ? cause.message : String(cause), provenance: [] }),
    );
  }, []);

  const warm = useCallback(async () => {
    setWarming(true);
    try {
      setStatus(await speechApi.status(true));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setWarming(false);
    }
  }, []);

  const send = useCallback(
    async (payload: { audio_base64?: string; text?: string }) => {
      setBusy(true);
      setError(null);
      try {
        const response = await speechApi.turn({
          ...payload,
          mode,
          language: language === "auto" ? null : language,
        });
        setResult(response);
        setView(mode === "compare" ? "nplm_validated" : mode);
        speechApi.status().then(setStatus).catch(() => undefined);
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : String(cause));
      } finally {
        setBusy(false);
      }
    },
    [language, mode],
  );

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"].find(
        (t) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t),
      );
      const instance = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      chunks.current = [];
      instance.ondataavailable = (event) => event.data.size > 0 && chunks.current.push(event.data);
      instance.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks.current, { type: instance.mimeType || "audio/webm" });
        if (blob.size > 0) await send({ audio_base64: await blobToBase64(blob) });
      };
      instance.start();
      recorder.current = instance;
      setRecording(true);
      setSeconds(0);
      timer.current = setInterval(() => setSeconds((s) => {
        if (s + 1 >= 30) recorder.current?.state === "recording" && recorder.current.stop();
        return s + 1;
      }), 1000);
    } catch (cause) {
      setError(`Microphone unavailable: ${cause instanceof Error ? cause.message : String(cause)}`);
    }
  }, [send]);

  const stop = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    if (recorder.current?.state === "recording") recorder.current.stop();
    setRecording(false);
  }, []);

  const turns = result?.turns ?? {};
  const shown = turns[view] ?? Object.values(turns)[0] ?? null;

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title="Speech Lab · talk to the model"
        hint="Whisper (speech → text) → Phrase DNA → base LLM or NPLM → MMS-TTS (text → speech). All models run locally from Hugging Face checkpoints."
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="eyebrow">Language</span>
              <select
                className={inputClass}
                value={language}
                onChange={(event) => {
                  const next = event.target.value as SpeechLanguage | "auto";
                  setLanguage(next);
                  if (next !== "auto") setText(EXAMPLES[next]);
                }}
              >
                <option value="auto">Auto (Whisper detects)</option>
                {(Object.keys(LANGUAGE_LABELS) as SpeechLanguage[]).map((code) => (
                  <option key={code} value={code}>{LANGUAGE_LABELS[code]}</option>
                ))}
              </select>
            </label>
            <div className="flex flex-col gap-1">
              <span className="eyebrow">Mode</span>
              <div className="flex flex-wrap gap-1">
                {[...MODES, "compare" as const].map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setMode(option)}
                    title={option === "compare" ? "Run A, B and C on the same recognition" : MODE_LABELS[option].pipeline}
                    className={`rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                      mode === option ? "bg-splm-500/20 text-splm-300 ring-1 ring-splm-500/40" : "faint hairline border hover:text-[var(--text)]"
                    }`}
                  >
                    {option === "compare" ? "Compare A · B · C" : `${MODE_LABELS[option].short} · ${MODE_LABELS[option].name}`}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={recording ? stop : start}
              disabled={busy || !micSupported || !secure}
              className={`flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                recording ? "bg-danger-400 text-white" : "bg-splm-500 text-ink-950 hover:bg-splm-400"
              }`}
            >
              <span className={`size-2.5 rounded-full ${recording ? "animate-pulse bg-white" : "bg-ink-950"}`} />
              {recording ? `Stop and send (${seconds}s)` : busy ? "Thinking…" : "Click to talk"}
            </button>
            <label className={`${buttonGhostClass} cursor-pointer`}>
              Upload audio
              <input
                type="file"
                accept="audio/*"
                className="hidden"
                disabled={busy}
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (file) await send({ audio_base64: await blobToBase64(file) });
                  event.target.value = "";
                }}
              />
            </label>
            {busy && <Loading label="Listening, thinking and speaking" />}
          </div>
          {!secure && (
            <Caveat>
              The browser only allows the microphone on HTTPS or localhost. On a remote server open the
              dashboard through an SSH tunnel (ssh -L 3010:localhost:3010 …) or HTTPS, or use Upload / typed text.
            </Caveat>
          )}

          <form
            className="flex flex-col gap-2 sm:flex-row"
            onSubmit={(event) => {
              event.preventDefault();
              if (text.trim()) void send({ text });
            }}
          >
            <input value={text} onChange={(event) => setText(event.target.value)} className={inputClass}
              placeholder="…or type what you would say (skips Whisper)" />
            <button type="submit" className={buttonClass} disabled={busy || !text.trim()}>Send text</button>
          </form>

          <ModelStatus status={status} warming={warming} onWarm={warm} />
        </div>
      </Panel>

      {error && <ErrorBox error={error} />}

      {shown && (
        <>
          {result?.shared_asr && (
            <div className="flex flex-wrap items-center gap-1">
              {MODES.filter((m) => turns[m]).map((m) => (
                <button key={m} type="button" onClick={() => setView(m)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium ${view === m ? "bg-splm-500/20 text-splm-300" : "faint hover:text-[var(--text)]"}`}>
                  {MODE_LABELS[m].short} · {MODE_LABELS[m].name}
                </button>
              ))}
            </div>
          )}

          <div className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
            <Panel title="Your words, sorted into Phrase DNA"
              hint="WHO · ACTION / STATUS · ON WHAT · FOR WHAT · WHERE · WHEN · WITH WHOM · HOW. “?” = the action expects it but you did not say it.">
              <div className="mb-3 flex flex-col gap-1">
                <span className="eyebrow">You said</span>
                <p className="text-base font-medium">“{shown.transcript || "…"}”</p>
                <div className="flex flex-wrap gap-1.5">
                  {shown.language && <Pill tone="splm">{shown.language} · {shown.asr?.language_source}</Pill>}
                  {shown.asr?.model_id && <Pill>{shown.asr.model_id}</Pill>}
                  {shown.validation?.changed && <Pill tone="warn">validation changed the transcript</Pill>}
                </div>
              </div>
              <DnaSort sort={shown.dna} />
              <Hypotheses turn={shown} />
            </Panel>

            <div className="flex flex-col gap-4">
              <Panel title={`Answer · ${MODE_LABELS[shown.mode].short} ${MODE_LABELS[shown.mode].name}`}
                hint={MODE_LABELS[shown.mode].pipeline}>
                <Answer turn={shown} />
              </Panel>
              <Panel title="This turn's timings" hint="Server-side wall clock for this one utterance — an example, not a benchmark.">
                <Timings turn={shown} />
              </Panel>
            </div>
          </div>

          {result?.shared_asr && <CompareTable turns={turns} note={result.note} />}
        </>
      )}

      {!shown && !busy && (
        <Panel>
          <Empty>
            Click the microphone, say something like “{EXAMPLES[language === "auto" ? "en" : language]}”, then click again.
            The first request loads the models (Whisper, the answer model and the voice), which can take a minute; use
            “Load models” first to warm them up.
          </Empty>
        </Panel>
      )}

      <BenchmarkPanel />
      <Provenance status={status} />
    </div>
  );
}

function ModelStatus({ status, warming, onWarm }: { status: SpeechStatus | null; warming: boolean; onWarm: () => void }) {
  if (!status) return <Loading label="Checking models" />;
  if (!status.available) return <ErrorBox error={`Speech lab unavailable: ${status.reason}`} />;
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      <Pill tone={status.asr?.loaded ? "ok" : "neutral"}>ASR {status.asr?.model_id}</Pill>
      <Pill tone="neutral">LLM {status.answer_model}</Pill>
      {Object.entries(status.tts?.voices ?? {}).map(([code, id]) => (
        <Pill key={code} tone={status.tts?.loaded.includes(code) ? "ok" : "neutral"}>{code} voice {id.split("/")[1]}</Pill>
      ))}
      {!status.warm && (
        <button type="button" className={buttonGhostClass} onClick={onWarm} disabled={warming}>
          {warming ? "Loading models…" : "Load models"}
        </button>
      )}
      {status.warm && <Pill tone="ok">models warm</Pill>}
    </div>
  );
}

function Hypotheses({ turn }: { turn: SpeechTurn }) {
  const hypotheses = turn.asr?.hypotheses ?? [];
  if (hypotheses.length <= 1 && !turn.validation) return null;
  const scored = new Map((turn.validation?.scored ?? []).map((s) => [s.rank, s]));
  return (
    <details className="mt-3">
      <summary className="faint cursor-pointer text-[11px]">Whisper n-best ({hypotheses.length}){turn.validation ? " and validation scores" : ""}</summary>
      <table className="num mt-2 w-full text-left text-[11px]">
        <thead className="faint"><tr><th className="py-1">#</th><th>hypothesis</th><th>acoustic</th>{turn.validation && <><th>DNA</th><th>agree</th><th>total</th></>}</tr></thead>
        <tbody>
          {hypotheses.map((h) => {
            const s = scored.get(h.rank);
            const chosen = turn.validation ? turn.validation.chosen_rank === h.rank : h.rank === 1;
            return (
              <tr key={h.rank} className={`hairline border-t ${chosen ? "text-splm-300" : ""}`}>
                <td className="py-1 pr-2">{h.rank}{chosen ? " ✓" : ""}</td>
                <td className="pr-2">{h.text}</td>
                <td className="pr-2">{h.score.toFixed(2)}</td>
                {turn.validation && <>
                  <td className="pr-2">{s ? `${(s.completeness * 100).toFixed(0)}%${s.has_predicate ? "" : " no verb"}${s.unresolved ? `, ${s.unresolved} gap` : ""}` : "—"}</td>
                  <td className="pr-2">{s ? s.consensus.toFixed(2) : "—"}</td>
                  <td>{s ? `${s.total.toFixed(2)}${s.eligible ? "" : " (too far)"}` : "—"}</td>
                </>}
              </tr>
            );
          })}
        </tbody>
      </table>
      {turn.validation?.warnings.map((w) => <Caveat key={w}>{w}</Caveat>)}
    </details>
  );
}

function Answer({ turn }: { turn: SpeechTurn }) {
  return (
    <div className="flex flex-col gap-3">
      {turn.clarification && (
        <p className="rounded-lg border border-warn-400/30 bg-warn-400/8 px-3 py-2 text-[11px] text-warn-400">
          Dialogue policy: {turn.clarification.reason} → asking about {turn.clarification.missing.replace("_", " ").toUpperCase()}.
        </p>
      )}
      <p className="text-lg leading-snug">{turn.response_text || <span className="faint">No answer.</span>}</p>
      {turn.audio_wav_base64 ? (
        // eslint-disable-next-line jsx-a11y/media-has-caption
        <audio key={turn.audio_wav_base64.slice(0, 64)} controls autoPlay className="w-full"
          src={`data:audio/wav;base64,${turn.audio_wav_base64}`} />
      ) : (
        <span className="faint text-xs">No audio for this answer.</span>
      )}
      <div className="flex flex-wrap gap-1.5">
        <Pill tone={turn.mode === "base" ? "base" : "splm"}>{turn.response_source}</Pill>
        {turn.settings.tts_model ? <Pill>{String(turn.settings.tts_model)}</Pill> : null}
        {turn.tokens_generated > 0 && <Pill>{turn.tokens_generated} tokens</Pill>}
      </div>
      {turn.warnings.map((w) => <Caveat key={w}>{w}</Caveat>)}
      {turn.response_dna && turn.response_dna.categories.some((c) => c.items.length) && (
        <details>
          <summary className="faint cursor-pointer text-[11px]">Answer’s Phrase DNA</summary>
          <div className="mt-2"><DnaSort sort={turn.response_dna} compact /></div>
        </details>
      )}
    </div>
  );
}

function Timings({ turn }: { turn: SpeechTurn }) {
  const t = turn.timings_ms;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <Stat label="ASR" value={ms(t.asr)} sub={turn.rtf.asr != null ? `RTF ${turn.rtf.asr}` : undefined} />
      {t.validation !== undefined && <Stat label="Validation" value={ms(t.validation)} />}
      <Stat label="Phrase DNA" value={ms(t.analysis)} />
      <Stat label="Generation" value={ms(t.generation)} tone={turn.mode === "base" ? "base" : "splm"} />
      <Stat label="Time to first audio" value={ms(t.time_to_first_audio)} />
      <Stat label="End to end" value={ms(t.end_to_end)} sub={turn.rtf.end_to_end != null ? `RTF ${turn.rtf.end_to_end}` : undefined} />
      <Stat label="Memory (RSS)" value={turn.memory.rss_mb != null ? `${Math.round(turn.memory.rss_mb)} MB` : "—"}
        sub={turn.memory.peak_rss_mb != null ? `peak ${Math.round(turn.memory.peak_rss_mb)} MB (process)` : undefined} />
    </div>
  );
}

function CompareTable({ turns, note }: { turns: TurnResponse["turns"]; note?: string }) {
  const rows: [string, (t: SpeechTurn) => string][] = [
    ["Transcript", (t) => t.transcript],
    ["Answer", (t) => t.response_text],
    ["Source", (t) => t.response_source],
    ["Generation", (t) => ms(t.timings_ms.generation)],
    ["Time to first audio", (t) => ms(t.timings_ms.time_to_first_audio)],
    ["End to end", (t) => ms(t.timings_ms.end_to_end)],
    ["RTF (end to end)", (t) => (t.rtf.end_to_end != null ? String(t.rtf.end_to_end) : "—")],
    ["DNA filled", (t) => (t.dna ? `${t.dna.categories.filter((c) => c.items.length).length}` : "—")],
  ];
  return (
    <Panel title="Same recording, three modes" hint={note}>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="faint">
            <tr className="hairline border-b"><th className="py-1.5 pr-3" />{MODES.map((m) => <th key={m} className="pr-3">{MODE_LABELS[m].short} · {MODE_LABELS[m].name}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label} className="hairline border-b last:border-0 align-top">
                <td className="faint py-1.5 pr-3">{label}</td>
                {MODES.map((m) => <td key={m} className="py-1.5 pr-3">{turns[m] ? value(turns[m]!) : "—"}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Caveat>One utterance shows behaviour, not a difference in quality. See the benchmark below for paired results over many items.</Caveat>
    </Panel>
  );
}

function BenchmarkPanel() {
  const [report, setReport] = useState<SpeechBenchmarkReport | null>(null);
  const [state, setState] = useState<"loading" | "none" | "ready" | "error">("loading");
  useEffect(() => {
    speechApi.benchmarks()
      .then(async ({ results }) => {
        if (!results.length) return setState("none");
        setReport(await speechApi.benchmark(results[0].run_id));
        setState("ready");
      })
      .catch(() => setState("error"));
  }, []);

  return (
    <Panel title="Benchmark · paired comparison of the three modes"
      hint="Latest run of scripts/speech_benchmark.py: identical audio, ASR result, hardware and greedy decoding for every mode.">
      {state === "loading" && <Loading label="Loading results" />}
      {state === "error" && <Empty>Could not load benchmark results.</Empty>}
      {state === "none" && <Empty>No speech benchmark yet. Run: python scripts/speech_benchmark.py</Empty>}
      {report && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-1.5">
            <Pill>{report.run_id}</Pill>
            <Pill>{report.samples} items · {report.languages.join(", ")}</Pill>
            <Pill tone={report.synthetic ? "warn" : "ok"}>{report.synthetic ? "synthetic speech (TTS)" : report.dataset}</Pill>
          </div>
          <div className="overflow-x-auto">
            <table className="num w-full text-left text-xs">
              <thead className="faint">
                <tr className="hairline border-b">
                  {["mode", "WER", "CER", "slot acc.", "entities kept", "numbers kept", "generation", "first audio", "end to end", "RTF", "peak RSS"].map((h) => (
                    <th key={h} className="py-1.5 pr-3 font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {MODES.map((m) => {
                  const s = report.per_mode[m];
                  if (!s) return null;
                  return (
                    <tr key={m} className="hairline border-b last:border-0">
                      <td className="py-1.5 pr-3">{MODE_LABELS[m].short} · {MODE_LABELS[m].name}</td>
                      <td className="pr-3">{s.corpus_wer ?? "—"}</td>
                      <td className="pr-3">{s.mean_cer ?? "—"}</td>
                      <td className="pr-3">{s.slot_accuracy.percent}% <span className="faint">({s.slot_accuracy.total})</span></td>
                      <td className="pr-3">{s.entity_preservation.percent}% <span className="faint">({s.entity_preservation.total})</span></td>
                      <td className="pr-3">{s.number_preservation.percent}% <span className="faint">({s.number_preservation.total})</span></td>
                      <td className="pr-3">{ms(s.generation_ms)}</td>
                      <td className="pr-3">{ms(s.time_to_first_audio_ms)}</td>
                      <td className="pr-3">{ms(s.end_to_end_ms)}</td>
                      <td className="pr-3">{s.rtf_end_to_end ?? "—"}</td>
                      <td className="pr-3">{s.peak_rss_mb ? `${Math.round(s.peak_rss_mb)} MB` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <ul className="flex flex-col gap-1 text-xs">
            {report.headline.map((line) => <li key={line}>• {line}</li>)}
          </ul>
          {report.caveats.map((c) => <Caveat key={c}>{c}</Caveat>)}
        </div>
      )}
    </Panel>
  );
}

function Provenance({ status }: { status: SpeechStatus | null }) {
  const rows = status?.provenance ?? [];
  if (!rows.length) return null;
  return (
    <Panel title="Model provenance" hint="Verified = loaded and run by scripts/download_resources.py --speech (voices: Whisper must hear the test sentence back).">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="faint"><tr className="hairline border-b">{["role", "model", "licence", "revision", "verified"].map((h) => <th key={h} className="py-1.5 pr-3">{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.role}-${row.model_id}`} className="hairline border-b last:border-0 align-top">
                <td className="py-1.5 pr-3">{row.role}{row.language ? ` (${row.language})` : ""}</td>
                <td className="pr-3"><a className="text-splm-300 hover:underline" href={row.source} target="_blank" rel="noreferrer">{row.model_id}</a></td>
                <td className="pr-3">{row.licence}</td>
                <td className="num faint pr-3">{row.revision ? row.revision.slice(0, 10) : "not cached"}</td>
                <td className="pr-3" title={row.verification ?? ""}>
                  {row.verified ? <Pill tone="ok">verified</Pill> : <Pill tone="warn">not verified</Pill>}
                  {row.verification && <span className="faint ml-1.5 text-[10.5px]">{row.verification}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
