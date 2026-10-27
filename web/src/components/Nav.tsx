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
    <svg viewBox="0 0 70 40" className="h-11 w-auto shrink-0 text-slate-300 [[data-theme=light]_&]:text-[#1e3a6e]" aria-hidden>
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

  return (
    <header ref={header} className="hairline sticky top-0 z-40 border-b backdrop-blur-md"
      style={{ background: "color-mix(in srgb, var(--page) 88%, transparent)" }}
    >
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="group flex items-center gap-3">
          <DominoMark />
          <span className="flex flex-col leading-none">
            <span className="text-[26px] font-bold tracking-tight sm:text-[39px]">{BRAND.name}</span>
            <span className="faint mt-1 text-[12px] sm:text-[14px]">{BRAND.tagline}</span>
          </span>
        </Link>

        {/* Links at 5x size: one full-width row that scrolls sideways instead of wrapping. */}
        <nav className="order-3 -mx-1 flex w-full items-center gap-2 overflow-x-auto pb-1">
          {PAGES.map((page) => {
            // The longest matching link wins: /acm/inference highlights only "What happens next?".
            const best = PAGES.filter((p) => (p.href === "/" ? pathname === "/" : pathname === p.href || pathname.startsWith(`${p.href}/`)))
              .sort((a, b) => b.href.length - a.href.length)[0];
            const active = best?.href === page.href;
            return (
              <Link
                key={page.href}
                href={page.href}
                className={`shrink-0 rounded-xl px-5 py-2 text-[36px] font-semibold leading-tight tracking-tight transition-colors sm:text-[60px] ${
                  active
                    ? "bg-splm-500/12 text-splm-300"
                    : "dim hover:bg-white/5 hover:text-[var(--text)]"
                }`}
              >
                {page.label}
              </Link>
            );
          })}
        </nav>

        <button
          type="button"
          onClick={toggleTheme}
          className="dim hairline order-2 ml-auto shrink-0 rounded-md border px-2.5 py-1.5 text-[11px] font-medium transition-colors hover:text-[var(--text)]"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </div>
    </header>
  );
}
