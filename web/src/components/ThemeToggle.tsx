"use client";

/** Light / dark switch (lives in the footer; the header follows the ARM design). */

import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const stored = window.localStorage.getItem("splm-theme");
    if (stored === "light" || stored === "dark") {
      setTheme(stored);
      document.documentElement.dataset.theme = stored;
    }
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("splm-theme", next);
  }

  return (
    <button type="button" onClick={toggle}
      className="dim hairline shrink-0 rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors hover:text-[var(--text)]"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
      {theme === "dark" ? "Light mode" : "Dark mode"}
    </button>
  );
}
