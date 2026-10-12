"use client";

import { percent, slotLabel } from "@/lib/api";
import type { PhraseFrame, SlotPrediction } from "@/lib/types";
import { Bar, Empty, Pill } from "./ui";

/**
 * "What does SPLM expect next?" - the prediction that has no base-model equivalent.
 *
 * Confidence is shown alongside entropy, and an ambiguous distribution is labelled as
 * such. Pretending to certainty when two slots score alike would be the easiest way
 * to make this look better than it is.
 */
export function ExpectedSlot({
  slots,
  frame,
  text,
}: {
  slots: SlotPrediction | null;
  frame?: PhraseFrame | null;
  text?: string;
}) {
  if (!slots || Object.keys(slots.distribution).length === 0) {
    return <Empty>No slot prediction available for this input.</Empty>;
  }

  const ranked = Object.entries(slots.distribution).sort((a, b) => b[1] - a[1]);
  const [topSlot, topProbability] = ranked[0];

  const tone =
    slots.confidence_label === "high"
      ? "ok"
      : slots.confidence_label === "medium"
        ? "warn"
        : "danger";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="text-3xl font-semibold leading-none tracking-tight text-warn-400">
            {slotLabel(topSlot)}
          </div>
          <div className="faint mt-1.5 text-[11px]">
            most probable next kind of meaning
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="num text-3xl font-semibold leading-none">
            {percent(topProbability, 0)}
          </div>
          <div className="mt-1.5 flex justify-end">
            <Pill tone={tone}>{slots.confidence_label} confidence</Pill>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        {ranked.slice(0, 6).map(([slot, probability]) => (
          <div key={slot} className="flex items-center gap-2.5">
            <span
              className={`w-36 shrink-0 truncate text-[11px] font-medium ${
                slot === topSlot ? "text-warn-400" : "dim"
              }`}
              title={slotLabel(slot)}
            >
              {slotLabel(slot)}
            </span>
            <Bar value={probability} tone={slot === topSlot ? "warn" : "neutral"} />
            <span className="num w-11 shrink-0 text-right text-[11px]">
              {percent(probability, 0)}
            </span>
          </div>
        ))}
      </div>

      <div className="faint flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
        <span>
          normalised entropy{" "}
          <span className="num">{slots.normalized_entropy.toFixed(2)}</span>
        </span>
        <span>predictor: {slots.backend}</span>
        {slots.dangling_marker && (
          <span>
            dangling marker: <code className="num">{slots.dangling_marker}</code>
          </span>
        )}
      </div>

      {slots.confidence_label === "ambiguous" && (
        <p className="rounded-md border border-warn-400/25 bg-warn-400/6 px-2.5 py-2 text-[11px] leading-snug text-warn-400">
          Competing slots score similarly here, so this is a genuine ambiguity rather
          than a confident prediction. Re-ranking will spread its effect across the
          rival readings instead of committing to one.
        </p>
      )}

      <Why slots={slots} frame={frame} text={text} />
    </div>
  );
}

/**
 * The "why" panel (UI spec section 8).
 *
 * Assembled entirely from structured state: the frame's own elements, the slot
 * predictor's recorded evidence, and the list of unfilled slots. Nothing here is
 * generated prose, and nothing exposes model-internal reasoning.
 */
function Why({
  slots,
  frame,
  text,
}: {
  slots: SlotPrediction;
  frame?: PhraseFrame | null;
  text?: string;
}) {
  const interpretation: { part: string; reading: string }[] = [];

  if (frame) {
    for (const element of frame.subject) {
      interpretation.push({ part: element.text, reading: element.semantic_role });
    }
    if (frame.predicate) {
      interpretation.push({
        part: frame.predicate.lemma,
        reading: frame.predicate.type,
      });
    }
    for (const slot of [
      "objects",
      "participants",
      "recipients",
      "location",
      "destination",
      "time",
      "manner",
      "instrument",
    ] as const) {
      for (const element of frame[slot]) {
        interpretation.push({ part: element.text, reading: element.semantic_role });
      }
    }
  }

  return (
    <div className="hairline flex flex-col gap-3 border-t pt-3">
      <h3 className="eyebrow">Why</h3>

      {text && (
        <p className="faint text-[11px] leading-snug">
          Current text: <span className="text-[var(--text-dim)]">{text}</span>
        </p>
      )}

      {interpretation.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="faint text-[10.5px] uppercase tracking-wide">
            SPLM interpretation
          </span>
          <div className="flex flex-wrap gap-1.5">
            {interpretation.map((item, index) => (
              <span
                key={`${item.part}-${index}`}
                className="panel-raised inline-flex items-baseline gap-1.5 px-2 py-1 text-[11px]"
              >
                <span className="font-medium">{item.part}</span>
                <span aria-hidden className="faint">
                  →
                </span>
                <span className="faint uppercase tracking-wide">{item.reading}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {slots.evidence.length > 0 && (
        <ul className="flex flex-col gap-1">
          {slots.evidence.map((line, index) => (
            <li key={index} className="dim flex gap-2 text-[11px] leading-snug">
              <span aria-hidden className="text-splm-400">
                ·
              </span>
              <span>{line}</span>
            </li>
          ))}
        </ul>
      )}

      {slots.missing_slots.length > 0 && (
        <p className="faint text-[11px] leading-snug">
          Not yet stated:{" "}
          <span className="text-[var(--text-dim)]">
            {slots.missing_slots.map((slot) => slotLabel(slot)).join(", ")}
          </span>
        </p>
      )}
    </div>
  );
}
