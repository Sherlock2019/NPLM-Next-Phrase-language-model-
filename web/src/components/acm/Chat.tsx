"use client";

/**
 * Chat boxes for the ARM demo. Each answer shows how it was reached:
 *   1. how the question was read (its Phrase DNA)
 *   2. the answer, then each consequence as its own phrase chained to the action:
 *      original action  →  WHO · DOES · WHAT · WHERE · WHEN · WITH WHOM · WHY
 *
 * PhraseChat asks the live MLM parser + ARM backend (POST /api/acm/ask).
 * The object chat for image/video reuses ChatShell, DnaChips and ChainRow.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { buttonClass, inputClass, ErrorBox } from "@/components/ui";
import { StatusTag } from "@/components/multimodal/Stages";
import type { ActionDna, AskChain, AskResult, LlmAnswer, PhraseResult } from "@/lib/multimodal/types";

/** The LLM's answer and its Phrase DNA; on failure, says that ARM's own answer is shown instead. */
export function LlmAnswerView({ llm, step }: { llm: LlmAnswer | null | undefined; step: string }) {
  if (!llm) return null;
  if (llm.error !== undefined)
    return <p className="text-[11px] text-warn-400">LLM unavailable ({llm.error}). ARM&apos;s own answer is shown below.</p>;
  return (
    <div className="flex flex-col gap-1">
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="eyebrow">{step} · LLM answer</span>
        <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-[10px] font-bold text-sky-300">{llm.model} · {llm.seconds}s</span>
        <span className="faint text-[10.5px]">worded only from the facts below</span>
      </span>
      <p className="text-[13.5px] leading-relaxed">{llm.text}</p>
      {llm.phrases.length > 0 && (
        <ol className="flex flex-col gap-1">
          {llm.phrases.map((p, i) => (
            <li key={i} className="flex items-start gap-1.5">
              <span aria-hidden className="text-sky-300">→</span>
              <DnaChips items={[["WHO", p.who], ["DOES", p.does], ["WHAT", p.what], ["WHERE", p.where], ["WHEN", p.when], ["WITH", p.with_whom], ["WHY", p.why]]} tone="bg-sky-500/10" />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export type Dna = [label: string, value: string | null | undefined][];

export function DnaChips({ items, tone = "panel-raised" }: { items: Dna; tone?: string }) {
  return (
    <span className="flex flex-wrap gap-1">
      {items.filter(([, v]) => v).map(([label, value]) => (
        <span key={label} className={`${tone} inline-flex items-baseline gap-1 rounded px-1.5 py-0.5 text-[11px]`}>
          <span className="eyebrow text-[9.5px]">{label}</span>
          <span className="font-medium">{value}</span>
        </span>
      ))}
    </span>
  );
}

const KIND_WORD: Record<string, string> = { status: "status", action: "action", impact: "impact", goal: "goal" };
const DIR_WORD: Record<string, string> = { "+": "▲ helps", "-": "▼ harms", "0": "● changes" };

export function ChainRow({ chain, mark }: { chain: AskChain; mark?: "added" | "removed" }) {
  const d = chain.dna;
  return (
    <li className={`flex flex-col gap-1 rounded-md px-2 py-1.5 ${mark === "removed" ? "opacity-60 line-through decoration-danger-400/60" : ""} ${mark === "added" ? "bg-ok-400/6" : "bg-white/3"}`}>
      <span className="flex flex-wrap items-center gap-1.5 text-[10.5px]">
        <span aria-hidden className="text-splm-300">→</span>
        <span className="font-semibold">{chain.ring_title}</span>
        <span className="faint">{KIND_WORD[chain.kind]}</span>
        <StatusTag status={chain.basis} />
        {chain.status && (
          <span className={chain.direction === "+" ? "text-ok-400" : chain.direction === "-" ? "text-danger-400" : "dim"}>{chain.status.replace("_", " ")}</span>
        )}
        {chain.direction && chain.kind === "impact" && <span className="dim">{DIR_WORD[chain.direction]}</span>}
        {mark && <span className={mark === "added" ? "text-ok-400" : "text-danger-400"}>{mark === "added" ? "new" : "no longer"}</span>}
      </span>
      <DnaChips items={[["WHO", d.who], ["DOES", d.does], ["WHAT", d.what], ["WHERE", d.where], ["WITH", d.with_whom], ["WHEN", d.when], ["WHY", d.why]]} />
      <span className="num faint text-[10.5px] leading-snug">↳ {d.rule}</span>
    </li>
  );
}

export function actionChips(a: ActionDna): Dna {
  return [
    ["WHO", a.who], ["DOES", a.does ? `${a.negated ? "not " : ""}${a.does}${a.concept ? ` → ${a.concept}` : ""}` : null],
    ["WHAT", a.what], ["TO WHOM", a.to_whom], ["WITH", a.with_whom], ["WHERE", a.where], ["FROM", a.from_where],
    ["WHEN", a.when], ["HOW", a.how], ["WHY", a.why ?? "unknown"], ["IF", a.condition],
  ];
}

export interface ChatMessage {
  id: number;
  question: string;
  body?: ReactNode;
  error?: string;
  pending?: boolean;
}

/** Message list + preset questions + input. `ask` returns the rendered answer. */
export function ChatShell({ title, hint, presets, disabled, disabledReason, ask, placeholder }: {
  title: string;
  hint: ReactNode;
  presets: string[];
  disabled?: boolean;
  disabledReason?: string;
  ask: (question: string) => Promise<ReactNode>;
  placeholder?: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const log = useRef<HTMLOListElement>(null);
  const next = useRef(0);

  useEffect(() => {
    log.current?.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages]);

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy || disabled) return;
    const id = next.current++;
    setDraft("");
    setBusy(true);
    setMessages((m) => [...m, { id, question: q, pending: true }]);
    try {
      const body = await ask(q);
      setMessages((m) => m.map((x) => (x.id === id ? { ...x, body, pending: false } : x)));
    } catch (e) {
      setMessages((m) => m.map((x) => (x.id === id ? { ...x, error: (e as Error).message, pending: false } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel-raised flex flex-col gap-2.5 p-3">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-[13px] font-semibold">{title}</span>
        <span className="faint text-[11px]">{hint}</span>
        {messages.length > 0 && (
          <button type="button" className="dim ml-auto text-[11px] underline" onClick={() => setMessages([])}>clear</button>
        )}
      </div>
      {messages.length > 0 && (
        <ol ref={log} className="flex max-h-[560px] flex-col gap-3 overflow-y-auto pr-1" aria-live="polite">
          {messages.map((m) => (
            <li key={m.id} className="flex flex-col gap-1.5">
              <span className="self-end rounded-lg bg-splm-500/20 px-2.5 py-1 text-[12.5px]">{m.question}</span>
              <div className="hairline flex flex-col gap-2 rounded-lg border px-2.5 py-2">
                {m.pending ? <span className="faint animate-pulse-soft text-[11.5px]">thinking…</span> : m.error ? <ErrorBox error={m.error} /> : m.body}
              </div>
            </li>
          ))}
        </ol>
      )}
      <div className="flex flex-wrap gap-1.5">
        {presets.map((p) => (
          <button key={p} type="button" disabled={busy || disabled} onClick={() => send(p)}
            className="hairline rounded-full border px-2.5 py-0.5 text-[11px] transition-colors hover:border-splm-500/60 disabled:opacity-40">
            {p}
          </button>
        ))}
      </div>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
        <input className={inputClass} value={draft} onChange={(e) => setDraft(e.target.value)} disabled={disabled}
          placeholder={disabled ? disabledReason : placeholder ?? "Ask your own question…"} aria-label={title} />
        <button type="submit" className={buttonClass} disabled={busy || disabled || !draft.trim()}>Ask</button>
      </form>
    </div>
  );
}

// -- phrase ------------------------------------------------------------------------------------

const INTENT_WORD: Record<AskResult["intent"], string> = {
  subject: "asks what happens to a subject", who: "asks who is affected", why: "asks for the reason",
  where: "asks where the effects reach", when: "asks when", certainty: "asks how sure ARM is",
  what_if: "asks a what-if: ARM re-runs the action",
};

/** Extra what-ifs for the bundled examples, so the counterfactual is one click away. */
const WHAT_IFS: Record<string, string[]> = {
  "John flew to London.": ["What if John traveled to London by train?"],
  "John traveled to Paris by train.": ["What if John flew to Paris?"],
  "I will sell my car to Sarah to pay my debt.": ["What if I sell my car to Mark?"],
  "John stole the car.": ["What if John bought the car?"],
  "The company destroyed the forest.": ["What if the company protected the forest?"],
};

function AskAnswer({ r }: { r: AskResult }) {
  const q = r.question;
  const cf = r.counterfactual;
  return (
    <>
      <div className="flex flex-col gap-1">
        <span className="eyebrow">1 · MLM reads the question</span>
        <DnaChips items={[
          ["WH", q.wh], ["DOES", q.predicate], ...q.slots.map((s) => [s.slot.toUpperCase(), s.text] as [string, string]),
          ["TENSE", q.tense], ["NEGATED", q.negated ? "yes" : null],
        ]} />
        <span className="faint text-[10.5px]">{q.parsed ? "parsed by MLM" : q.note} · intent: {INTENT_WORD[r.intent]}</span>
      </div>
      <LlmAnswerView llm={r.llm} step="2" />
      <div className="flex flex-col gap-1">
        <span className="eyebrow">3 · ARM&apos;s facts (rule engine)</span>
        <p className={r.llm && r.llm.error === undefined ? "dim text-[12px] leading-relaxed" : "text-[13px] leading-relaxed"}>{r.answer}</p>
      </div>
      <div className="flex flex-col gap-1">
        <span className="eyebrow">4 · Original action → consequence (Phrase DNA, from ARM)</span>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="rounded bg-splm-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase">action</span>
          <DnaChips items={actionChips(cf ? cf.action : r.action)} tone="bg-splm-500/10" />
        </div>
        {cf ? (
          <ol className="flex flex-col gap-1">
            {cf.added.map((c, i) => <ChainRow key={`a${i}`} chain={c} mark="added" />)}
            {cf.removed.map((c, i) => <ChainRow key={`r${i}`} chain={c} mark="removed" />)}
            {cf.kept.map((c, i) => <ChainRow key={`k${i}`} chain={c} />)}
          </ol>
        ) : r.chains.length ? (
          <ol className="flex flex-col gap-1">{r.chains.map((c, i) => <ChainRow key={i} chain={c} />)}</ol>
        ) : (
          <p className="faint text-[11.5px] italic">No supporting evidence — ARM&apos;s rules record nothing here (never read as “no impact”).</p>
        )}
      </div>
      {r.why.length > 0 && (
        <details className="text-[11px]">
          <summary className="faint cursor-pointer">why ARM says this</summary>
          <ul className="mt-1 flex flex-col gap-0.5">{r.why.map((w, i) => <li key={i} className="num dim">↳ {w}</li>)}</ul>
        </details>
      )}
      {r.unknowns.length > 0 && r.intent !== "what_if" && (
        <p className="faint text-[10.5px]">Unknown: {r.unknowns.map((u) => `${u.subject} ${u.aspect} (needs ${u.needs.join(", ")})`).join(" · ")}</p>
      )}
    </>
  );
}

export function PhraseChat({ result, live, liveReason }: { result: PhraseResult; live: boolean; liveReason: string }) {
  const presets = [...(result.suggestions ?? ["What happens next?", "Who is harmed?", "Why?"]), ...(WHAT_IFS[result.text] ?? [])];
  async function ask(question: string) {
    const response = await fetch("/api/acm/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: result.text, context: result.context, question }),
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(body?.detail ?? `ARM ask failed (${response.status})`);
    return <AskAnswer r={body as AskResult} />;
  }
  return (
    <ChatShell
      key={`${result.text}|${result.context.join("|")}`}
      title="Ask ARM about this action"
      hint={<>live: MLM parses your question, ARM computes the answer from its report of <b>“{result.text}”</b>, the local LLM words it</>}
      presets={presets}
      disabled={!live}
      disabledReason={`Chat needs Live mode (MLM parser + ARM): ${liveReason}`}
      placeholder="e.g. What happens to Sarah? · Who benefits? · What if John took the train?"
      ask={ask}
    />
  );
}
