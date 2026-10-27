"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BRAND, PAGES } from "@/lib/app";

/** Falling dominoes: one action knocking on to the next — what ACM traces. */
function DominoMark() {
  const tiles = [
    { x: 4, rot: -58, fill: "currentColor", pips: 2 },
    { x: 20, rot: -38, fill: "currentColor", pips: 3 },
    { x: 37, rot: -16, fill: "#2563eb", pips: 4 },
    { x: 54, rot: 0, fill: "#14b8a6", pips: 5 },
  ];
  return (
    <svg viewBox="0 0 70 40" className="h-9 w-auto shrink-0 text-slate-300 [[data-theme=light]_&]:text-[#1e3a6e]" aria-hidden>
      {tiles.map((t, i) => (
        <g key={i} transform={`rotate(${t.rot} ${t.x + 6} 38)`}>
          <rect x={t.x} y={8} width={12} height={30} rx={2.5} fill={t.fill} />
          <line x1={t.x + 2} x2={t.x + 10} y1={23} y2={23} stroke="#fff" strokeWidth={1.2} opacity={0.8} />
          {Array.from({ length: t.pips }).map((_, p) => (
            <circle key={p} cx={t.x + (p % 2 ? 8.5 : 3.5)} cy={p < 2 ? 14 + p * 4 : 27 + (p - 2) * 4} r={1.3} fill="#fff" />
          ))}
        </g>
      ))}
    </svg>
  );
}

function ThemeIcon({ theme }: { theme: "dark" | "light" }) {
  return theme === "dark" ? (
    <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-hidden>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

export function Nav() {
  const pathname = usePathname();
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const header = useRef<HTMLElement>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem("splm-theme");
    if (stored === "light" || stored === "dark") {
      setTheme(stored);
      document.documentElement.dataset.theme = stored;
    }
  }, []);

  // Pages pin banners just below the header: publish its real height as --nav-h.
  useEffect(() => {
    const el = header.current;
    if (!el) return;
    const publish = () => document.documentElement.style.setProperty("--nav-h", `${el.offsetHeight}px`);
    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("splm-theme", next);
  }

  // The longest matching link wins: /acm/inference highlights only "What happens next?".
  const best = PAGES.filter((p) => (p.href === "/" ? pathname === "/" : pathname === p.href || pathname.startsWith(`${p.href}/`)))
    .sort((a, b) => b.href.length - a.href.length)[0];
  const primary = PAGES.filter((p) => p.primary);
  const secondary = PAGES.filter((p) => !p.primary);

  return (
    <header ref={header} className="hairline sticky top-0 z-40 border-b backdrop-blur-md"
      style={{ background: "color-mix(in srgb, var(--page) 90%, transparent)" }}
    >
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-3">
          <DominoMark />
          <span className="text-[28px] font-extrabold leading-none tracking-tight text-slate-100 [[data-theme=light]_&]:text-[#1e3a6e]">
            {BRAND.mark}
          </span>
          <span aria-hidden className="hairline hidden h-9 border-l sm:block" />
          <span className="hidden flex-col leading-tight sm:flex">
            <span className="text-[17px] font-semibold tracking-tight">{BRAND.name}</span>
            <span className="faint text-[12px]">{BRAND.tagline}</span>
          </span>
        </Link>

        <nav aria-label="Main" className="order-3 -mx-1 flex w-full items-center gap-1 overflow-x-auto md:order-2 md:mx-0 md:ml-auto md:w-auto">
          {primary.map((page) => (
            <Link key={page.href} href={page.href} aria-current={best?.href === page.href ? "page" : undefined}
              className={`shrink-0 rounded-lg px-3 py-1.5 text-[14px] font-medium transition-colors ${
                best?.href === page.href ? "bg-splm-500/15 text-splm-300" : "dim hover:bg-white/5 hover:text-[var(--text)]"
              }`}>
              {page.label}
            </Link>
          ))}
        </nav>

        <button type="button" onClick={toggleTheme}
          className="dim hairline order-2 ml-auto grid size-9 shrink-0 place-items-center rounded-full border transition-colors hover:text-[var(--text)] md:order-3 md:ml-0"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
          <ThemeIcon theme={theme} />
        </button>
      </div>

      {secondary.length > 0 && (
        <div className="hairline border-t">
          <nav aria-label="MLM tools" className="mx-auto flex max-w-[1600px] items-center justify-between gap-1 overflow-x-auto px-4 py-1.5 sm:px-6">
            {secondary.map((page) => (
              <Link key={page.href} href={page.href} aria-current={best?.href === page.href ? "page" : undefined}
                className={`shrink-0 rounded-md px-2.5 py-1 text-[12.5px] font-medium transition-colors ${
                  best?.href === page.href ? "bg-splm-500/12 text-splm-300" : "dim hover:bg-white/5 hover:text-[var(--text)]"
                }`}>
                {page.label}
              </Link>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}
