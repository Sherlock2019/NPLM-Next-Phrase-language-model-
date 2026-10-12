"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const PAGES = [
  { href: "/", label: "Playground" },
  { href: "/phrase-dna", label: "Phrase DNA" },
  { href: "/inspector", label: "Inspector" },
  { href: "/context", label: "Context Graph" },
  { href: "/multilingual", label: "Multilingual" },
  { href: "/benchmark", label: "Benchmark" },
  { href: "/ablation", label: "Ablation" },
  { href: "/architecture", label: "Architecture" },
  { href: "/system", label: "System" },
];

export function Nav() {
  const pathname = usePathname();
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const stored = window.localStorage.getItem("splm-theme");
    if (stored === "light" || stored === "dark") {
      setTheme(stored);
      document.documentElement.dataset.theme = stored;
    }
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("splm-theme", next);
  }

  return (
    <header className="hairline sticky top-0 z-40 border-b backdrop-blur-md"
      style={{ background: "color-mix(in srgb, var(--page) 88%, transparent)" }}
    >
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="group flex items-center gap-2.5">
          <span
            aria-hidden
            className="grid size-7 place-items-center rounded-md bg-splm-500/15 text-[11px] font-bold text-splm-400 ring-1 ring-splm-500/30"
          >
            SP
          </span>
          <span className="flex flex-col leading-none">
            <span className="text-[13px] font-semibold tracking-tight">
              Smart Phrase Language Model
            </span>
            <span className="faint mt-0.5 text-[10.5px]">
              Understand meaning before predicting language
            </span>
          </span>
        </Link>

        <nav className="order-3 -mx-1 flex w-full items-center gap-0.5 overflow-x-auto sm:order-2 sm:mx-0 sm:w-auto">
          {PAGES.map((page) => {
            const active =
              page.href === "/" ? pathname === "/" : pathname.startsWith(page.href);
            return (
              <Link
                key={page.href}
                href={page.href}
                className={`shrink-0 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
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
          className="dim hairline order-2 ml-auto shrink-0 rounded-md border px-2.5 py-1.5 text-[11px] font-medium transition-colors hover:text-[var(--text)] sm:order-3"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </div>
    </header>
  );
}
