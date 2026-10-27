"use client";

/** Top-of-page intro: the "MLM → ACM: from questions to consequences" infographic (public/acm/how-chat-works.webp). */

import type { PageKind } from "./HowItWorks";

const WHERE: Record<PageKind | "tour", string | null> = {
  demo: null,
  tour: "Try both chats on the ACM Demo page.",
  inference: "The chats are on the ACM Demo page. On this page every answer is put together by ACM from its own trace; no LLM writes it.",
  multimodal: "The chats and the physics lab are on the ACM Demo page. This page shows the meaning and consequence stages in detail.",
};

export const INFOGRAPHIC_ALT =
  "MLM to ACM, from questions to consequences: rules determine outcomes, the LLM plans or explains. " +
  "Phrase chat: 1 question, 2 MLM parses it with Stanza and its own rules into Phrase DNA, 3 ACM's rule packs compute the consequences, " +
  "4 the LLM phrases ACM's facts in plain language; ACM's sentence and supporting rows stay visible. " +
  "Image/video chat: 1 question and scene, 2 the LLM plans the object, question, action and force, 3 matter.js simulates it with library " +
  "properties, 4 the LLM explains the simulated events; assumptions and events stay visible. " +
  "MLM does not rely on an LLM. Unknown causes are marked UNKNOWN. Object detection is mocked and object properties are assumptions.";

export function Intro({ page }: { page: PageKind | "tour" }) {
  const where = WHERE[page];
  return (
    <section className="panel flex flex-col gap-2 p-3" aria-label="How the chats answer">
      <a href="/acm/how-chat-works.webp" target="_blank" rel="noreferrer" title="Open full size">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/acm/how-chat-works.webp" alt={INFOGRAPHIC_ALT} width={1601} height={982} className="block h-auto w-full rounded-md" />
      </a>
      {where && (
        <p className="text-[12px] text-sky-300">
          {where} <a className="underline" href="/acm">Go to the ACM Demo →</a>
        </p>
      )}
    </section>
  );
}
