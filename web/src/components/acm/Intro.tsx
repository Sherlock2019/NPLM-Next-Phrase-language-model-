"use client";

/** Top-of-page intro: how the chats answer, what the LLM does and does not do, with live examples. */

import type { PageKind } from "./HowItWorks";

const WHERE: Record<PageKind, string | null> = {
  demo: null,
  inference: "The chats are on the ACM Demo page. On this page every answer is put together by ACM from its own trace; no LLM writes it.",
  multimodal: "The chats and the physics lab are on the ACM Demo page. This page shows the meaning and consequence stages in detail.",
};

function Example({ q, a }: { q: string; a: string }) {
  return (
    <li className="text-[12px] leading-snug">
      <span className="font-medium">“{q}”</span> <span className="faint">→</span> <span className="dim">{a}</span>
    </li>
  );
}

export function Intro({ page }: { page: PageKind }) {
  const where = WHERE[page];
  return (
    <section className="panel flex flex-col gap-3 p-4" aria-label="How the chats answer">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-[15px] font-semibold">Ask ACM — answered by a local LLM, grounded in ACM&apos;s facts</h2>
        <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-[10px] font-bold text-sky-300">qwen2.5:7b · Ollama · runs on this machine</span>
      </div>
      <p className="text-[13px] leading-relaxed">
        The chat boxes answer with a real LLM, <b>qwen2.5:7b</b>, running locally through Ollama on this machine&apos;s GPU, so nothing
        leaves the machine. The LLM only <b>words</b> the answers and reads free-form physics questions. It never decides a consequence:
        those come from ACM&apos;s rule packs and the simulator.
      </p>
      {where && (
        <p className="text-[12px] text-sky-300">
          {where} <a className="underline" href="/acm">Go to the ACM Demo →</a>
        </p>
      )}

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="panel-raised flex flex-col gap-1.5 p-3">
          <h3 className="text-[13px] font-semibold">Does MLM rely on the LLM?</h3>
          <p className="text-[12px] leading-relaxed">
            No. MLM reads a phrase into Phrase DNA with the <b>Stanza parser and its own rules</b>. The small SmolLM2 model it is
            configured with is only used for next-phrase prediction in the MLM Playground. ACM&apos;s consequences come from its rule packs
            and the simulator.
          </p>
        </div>

        <div className="panel-raised flex flex-col gap-1.5 p-3">
          <h3 className="text-[13px] font-semibold">Phrase chat</h3>
          <ol className="flex list-decimal flex-col gap-0.5 pl-4 text-[12px] leading-snug">
            <li>MLM reads the question.</li>
            <li>ACM works out the answer from its rules.</li>
            <li>
              The LLM writes it as plain sentences plus phrases in the same format (WHO · DOES · WHAT · WHERE · WHEN · WITH WHOM · WHY),
              using only ACM&apos;s facts.
            </li>
            <li>ACM&apos;s own sentence and its rows stay underneath as the evidence.</li>
          </ol>
          <span className="eyebrow mt-1">Live answers</span>
          <ul className="flex flex-col gap-1">
            <Example q="What happens to the neighbours?" a="“The neighbours in Croydon, Watford, and Slough are exposed to harmful aircraft noise and fumes after John flew to London.”" />
            <Example q="Why did John fly?" a="“The reason … is UNKNOWN; ACM does not invent one.”" />
            <Example q="What if John traveled to London by train?" a="the new phrases are correct (public transport helps the city, lower emissions help the earth)" />
          </ul>
          <p className="text-[11px] text-warn-400">
            Known limit: for a what-if, the sentence on top can be vague and not say clearly what no longer happens — the rows below list it.
          </p>
        </div>

        <div className="panel-raised flex flex-col gap-1.5 p-3">
          <h3 className="text-[13px] font-semibold">Image / video chat</h3>
          <ol className="flex list-decimal flex-col gap-0.5 pl-4 text-[12px] leading-snug">
            <li>The LLM turns the question into a plan: which object, what you are asking, and what action and how far.</li>
            <li>matter.js simulates it.</li>
            <li>The LLM writes the answer from the simulated events and the object&apos;s library properties.</li>
          </ol>
          <span className="eyebrow mt-1">Example</span>
          <ul className="flex flex-col gap-1">
            <Example q="Will the red mug survive if someone knocks it hard to the right?" a="read as: the red cup, a break question, a flick to the right" />
          </ul>
          <p className="faint text-[11px]">
            Object detection is a mock and object properties are library assumptions; the page labels both. If the LLM is down, the chats
            fall back to ACM&apos;s own sentences and a keyword parser.
          </p>
        </div>
      </div>
    </section>
  );
}
