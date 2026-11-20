"use client";

/**
 * Top-of-page intro: the "MLM → ACM: from questions to consequences" infographic.
 * Its title + phrase-chat row and its footer are images (public/acm/how-chat-top.webp,
 * how-chat-footer.webp); the image/video row in between is <SceneFlow />, so its stages
 * can be kept in step with the app.
 */

import { ACM_PROJECT_URL } from "@/lib/app";
import type { PageKind } from "./HowItWorks";
import { SceneFlow } from "./SceneFlow";

const WHERE: Record<PageKind | "tour", string | null> = {
  demo: null,
  tour: "Try both chats on the ACM Demo page.",
  inference: "The chats are on the ACM Demo page. On this page every answer is put together by ACM from its own trace; no LLM writes it.",
  multimodal: "The chats and the physics lab are on the ACM Demo page. This page shows the meaning and consequence stages in detail.",
};

const TOP_ALT =
  "MLM to ACM, from questions to consequences: rules determine outcomes, the LLM plans or explains. " +
  "Phrase chat: 1 question, 2 MLM parses it with Stanza and its own rules into Phrase DNA, 3 ACM's rule packs compute the consequences, " +
  "4 the LLM phrases ACM's facts in plain language; ACM's sentence and supporting rows stay visible.";
const FOOTER_ALT =
  "MLM does not rely on an LLM. Honest unknowns: a missing cause is marked UNKNOWN, never invented. " +
  "Prototype limits: object detection is mocked and object properties are assumptions; without the LLM, ACM's sentence and a keyword parser are used.";

export function Intro({ page }: { page: PageKind | "tour" }) {
  const where = WHERE[page];
  return (
    <section className="panel flex flex-col gap-2 p-3" aria-label="How the chats answer">
      <div className="relative">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/acm/how-chat-top.webp" alt={TOP_ALT} width={1601} height={492} className="block h-auto w-full rounded-md" />
        {/* Sits in the blank band under the infographic's subtitle; positioned and sized
            relative to the image so it stays in that band at every width. */}
        {page === "inference" && <a
          href={ACM_PROJECT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="absolute left-1/2 top-[20.5%] -translate-x-1/2 whitespace-nowrap rounded-full bg-[#1e3a8a] px-[1.2%] py-[0.2%] font-semibold text-white shadow-md ring-1 ring-white/30 transition-colors hover:bg-[#2563eb]"
          style={{ fontSize: "clamp(8px, 0.9vw, 13px)" }}
        >
          Open the live ACM demo project ↗
        </a>}
      </div>
      <SceneFlow />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/acm/how-chat-footer.webp" alt={FOOTER_ALT} width={1568} height={114} className="block h-auto w-full rounded-md" />
      {where && (
        <p className="text-[12px] text-sky-300">
          {where} <a className="underline" href="/acm">Go to the ACM Demo →</a>
        </p>
      )}
    </section>
  );
}
