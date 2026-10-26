"use client";

import { SLOT_ORDER, slotLabel } from "@/lib/api";
import type { FrameElement, PhraseFrame } from "@/lib/types";
import { Empty, Pill } from "./ui";

/**
 * The Universal Phrase DNA as cards.
 *
 * Filled slots show what the text said. Slots the predicate plausibly takes but the
 * text has not filled show "?" - never a guess. That distinction is the point: MLM
 * knows what it does not know, and the next-slot prediction is built on it.
 */
export function PhraseDna({
  frame,
  expectedSlot,
  compact = false,
}: {
  frame: PhraseFrame | null;
  expectedSlot?: string | null;
  compact?: boolean;
}) {
  if (!frame) {
    return (
      <Empty>
        No phrase frame. The parser produced no analysis for this text — check that a
        parser model is installed for the detected language.
      </Empty>
    );
  }

  const filled = SLOT_ORDER.filter(
    (slot) => slot !== "predicate" && (frame[slot as keyof PhraseFrame] as FrameElement[])?.length,
  );
  const missing = frame.unresolved_slots.filter((slot) => slot !== "predicate");

  return (
    <div className="flex flex-col gap-3">
      <div
        className={`grid gap-2 ${
          compact
            ? "grid-cols-2 sm:grid-cols-3"
            : "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4"
        }`}
      >
        {frame.predicate && (
          <SlotCard
            label={frame.predicate.type}
            value={frame.predicate.lemma}
            detail={frame.predicate.sense ?? undefined}
            kind="predicate"
          />
        )}

        {filled.map((slot) => {
          const elements = frame[slot as keyof PhraseFrame] as FrameElement[];
          return elements.map((element, index) => (
            <SlotCard
              key={`${slot}-${index}`}
              label={slotLabel(slot)}
              value={element.text}
              detail={element.semantic_role}
              element={element}
              kind="filled"
            />
          ));
        })}

        {missing.map((slot) => (
          <SlotCard
            key={`missing-${slot}`}
            label={slotLabel(slot)}
            value="?"
            kind={expectedSlot === slot ? "expected" : "missing"}
            detail={expectedSlot === slot ? "expected next" : undefined}
          />
        ))}
      </div>

      <FrameMeta frame={frame} />

      {frame.children.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="eyebrow">Also in this sentence</p>
          {frame.children.map((child, index) => (
            <div key={index} className="panel-raised p-3">
              <PhraseDna frame={child} compact />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SlotCard({
  label,
  value,
  detail,
  element,
  kind,
}: {
  label: string;
  value: string;
  detail?: string;
  element?: FrameElement;
  kind: "predicate" | "filled" | "missing" | "expected";
}) {
  const styles: Record<string, string> = {
    predicate: "border-splm-500/35 bg-splm-500/8",
    filled: "hairline",
    // Missing information is drawn as an outline, so it reads as a gap.
    missing: "border-dashed border-white/12 bg-transparent",
    expected: "border-dashed border-warn-400/50 bg-warn-400/6",
  };
  const nested = element?.frame ?? null;

  return (
    <div
      className={`animate-rise flex min-w-0 flex-col rounded-lg border px-3 py-2 ${styles[kind]}`}
    >
      <span
        className={`eyebrow truncate ${
          kind === "expected" ? "text-warn-400" : kind === "predicate" ? "text-splm-400" : ""
        }`}
      >
        {label}
      </span>
      <span
        className={`mt-1 truncate text-sm font-medium ${
          kind === "missing" || kind === "expected" ? "faint" : ""
        }`}
        title={value}
      >
        {value}
      </span>

      {detail && (
        <span className="faint mt-1 truncate text-[10.5px] uppercase tracking-wide">
          {detail}
        </span>
      )}

      {element && Object.keys(element.annotations).length > 0 && (
        <span className="faint mt-1 truncate text-[10.5px]">
          {Object.entries(element.annotations)
            .map(([key, val]) => `${key}: ${String(val)}`)
            .join(" · ")}
        </span>
      )}

      {element && element.alternatives.length > 0 && element.confidence < 0.75 && (
        <span
          className="faint mt-1 truncate text-[10.5px]"
          title={element.alternatives
            .map((alt) => `${alt.role} ${(alt.probability * 100).toFixed(0)}%`)
            .join(", ")}
        >
          also read as {element.alternatives[0].role.toLowerCase()}
        </span>
      )}

      {nested && (
        <span className="faint mt-1.5 truncate text-[10.5px]">
          ↳ {nested.predicate?.lemma ?? "nested frame"}
        </span>
      )}
    </div>
  );
}

function FrameMeta({ frame }: { frame: PhraseFrame }) {
  const bits: { label: string; tone?: "warn" | "neutral" }[] = [];
  if (frame.tense) bits.push({ label: frame.tense });
  if (frame.aspect && frame.aspect !== "simple") bits.push({ label: frame.aspect });
  if (frame.modality) bits.push({ label: frame.modality });
  if (frame.voice === "passive") bits.push({ label: "passive" });
  if (frame.negation) bits.push({ label: "negated", tone: "warn" });
  if (frame.intent && frame.intent !== "statement") bits.push({ label: frame.intent });
  if (frame.certainty !== null)
    bits.push({ label: `certainty ${(frame.certainty * 100).toFixed(0)}%` });
  if (frame.dangling_marker)
    bits.push({ label: `awaiting "${frame.dangling_marker}" complement`, tone: "warn" });

  if (bits.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {bits.map((bit) => (
        <Pill key={bit.label} tone={bit.tone ?? "neutral"}>
          {bit.label}
        </Pill>
      ))}
    </div>
  );
}
