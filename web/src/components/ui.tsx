/**
 * Shared presentational pieces.
 *
 * One rule runs through all of them: an absent value renders as an explicit
 * "not available", never as 0%, an empty bar, or a plausible-looking placeholder.
 */

import type { ReactNode } from "react";

export function Panel({
  title,
  hint,
  actions,
  children,
  className = "",
  padded = true,
}: {
  title?: string;
  hint?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="hairline flex items-start gap-3 border-b px-4 py-2.5">
          <div className="min-w-0 flex-1">
            {title && <h2 className="eyebrow">{title}</h2>}
            {hint && <p className="faint mt-1 text-[11px] leading-snug">{hint}</p>}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Pill({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "base" | "splm" | "warn" | "danger" | "ok";
  title?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "bg-white/5 text-[var(--text-dim)] ring-white/10",
    base: "bg-base-500/15 text-base-400 ring-base-500/25",
    splm: "bg-splm-500/15 text-splm-300 ring-splm-500/25",
    warn: "bg-warn-400/12 text-warn-400 ring-warn-400/25",
    danger: "bg-danger-400/12 text-danger-400 ring-danger-400/25",
    ok: "bg-ok-400/12 text-ok-400 ring-ok-400/25",
  };
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide ring-1 ring-inset ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "neutral" | "base" | "splm" | "warn" | "danger" | "ok";
}) {
  const colors: Record<string, string> = {
    neutral: "text-[var(--text)]",
    base: "text-base-400",
    splm: "text-splm-300",
    warn: "text-warn-400",
    danger: "text-danger-400",
    ok: "text-ok-400",
  };
  return (
    <div className="panel-raised px-3 py-2.5">
      <div className="eyebrow">{label}</div>
      <div className={`num mt-1 text-xl font-semibold leading-none ${colors[tone]}`}>
        {value}
      </div>
      {sub && <div className="faint mt-1.5 text-[11px] leading-snug">{sub}</div>}
    </div>
  );
}

/** A horizontal probability bar. `compare` draws a second, fainter bar behind it. */
export function Bar({
  value,
  compare,
  tone = "splm",
  height = 6,
}: {
  value: number;
  compare?: number;
  tone?: "base" | "splm" | "warn" | "neutral";
  height?: number;
}) {
  const fills: Record<string, string> = {
    base: "bg-base-500",
    splm: "bg-splm-500",
    warn: "bg-warn-400",
    neutral: "bg-ink-400",
  };
  const clamp = (n: number) => Math.max(0, Math.min(1, n)) * 100;
  return (
    <div
      className="relative w-full overflow-hidden rounded-full bg-white/6"
      style={{ height }}
    >
      {compare !== undefined && (
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-white/12"
          style={{ width: `${clamp(compare)}%` }}
        />
      )}
      <div
        className={`animate-bar absolute inset-y-0 left-0 rounded-full ${fills[tone]}`}
        style={{ width: `${clamp(value)}%` }}
      />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="faint grid place-items-center px-4 py-8 text-center text-xs leading-relaxed">
      {children}
    </div>
  );
}

export function Loading({ label = "Working" }: { label?: string }) {
  return (
    <div className="dim flex items-center gap-2 px-4 py-8 text-xs">
      <span className="animate-pulse-soft size-1.5 rounded-full bg-splm-400" />
      <span className="animate-pulse-soft size-1.5 rounded-full bg-splm-400 [animation-delay:0.2s]" />
      <span className="animate-pulse-soft size-1.5 rounded-full bg-splm-400 [animation-delay:0.4s]" />
      <span className="ml-1">{label}…</span>
    </div>
  );
}

export function ErrorBox({ error }: { error: string }) {
  return (
    <div className="rounded-lg border border-danger-400/30 bg-danger-400/8 px-3 py-2.5 text-xs leading-relaxed text-danger-400">
      {error}
    </div>
  );
}

/** A caveat the reader must see next to the number it qualifies. */
export function Caveat({ children }: { children: ReactNode }) {
  return (
    <p className="faint mt-2 flex gap-1.5 text-[11px] leading-snug">
      <span aria-hidden className="text-warn-400">
        !
      </span>
      <span>{children}</span>
    </p>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="panel-raised flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-white/4"
    >
      <span
        className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
          checked ? "bg-splm-500" : "bg-white/12"
        }`}
      >
        <span
          className={`absolute top-0.5 size-3 rounded-full bg-white transition-all ${
            checked ? "left-3.5" : "left-0.5"
          }`}
        />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-medium">{label}</span>
        {hint && <span className="faint block text-[10.5px] leading-snug">{hint}</span>}
      </span>
    </button>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="eyebrow">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "hairline w-full rounded-md border bg-[var(--panel-raised)] px-2.5 py-1.5 text-xs outline-none transition-colors focus:border-splm-500/60";

export const buttonClass =
  "rounded-md bg-splm-500 px-3.5 py-1.5 text-xs font-semibold text-ink-950 transition-colors hover:bg-splm-400 disabled:cursor-not-allowed disabled:opacity-40";

export const buttonGhostClass =
  "dim hairline rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:text-[var(--text)] disabled:cursor-not-allowed disabled:opacity-40";
