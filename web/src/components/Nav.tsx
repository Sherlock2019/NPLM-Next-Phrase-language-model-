"use client";

/**
 * The site header, after the ACM design: the butterfly logo (ACM mode; the PLM wordmark,
 * web/public/plm/logo.png, otherwise - its navy #040e42 is the header colour so it has no box)
 * + ACM / the Butterfly Model, the menu
 * (What is ACM? · Why ACM? · Prediction Modes ▾ · How It Works · Research ▾) and "Try a Demo".
 * Dropdowns open on click or hover and close on Escape or a click outside. On narrow screens
 * the menu folds into a "Menu" button.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BRAND, CTA, MENU, type MenuEntry, type MenuGroup } from "@/lib/app";

const isGroup = (e: MenuEntry): e is MenuGroup => "items" in e;
const linkClass = "rounded-md px-3 py-2 text-[15px] font-medium text-slate-100 transition-colors hover:bg-white/10 hover:text-white";

function Dropdown({ group, open, onToggle, onClose, active, alignRight = false }: {
  group: MenuGroup; open: boolean; onToggle: () => void; onClose: () => void; active: (href: string) => boolean;
  /** Open towards the left, for a dropdown at the right end of the menu (keeps it on screen). */
  alignRight?: boolean;
}) {
  return (
    <div className="relative" onMouseLeave={onClose}>
      <button type="button" aria-expanded={open} aria-haspopup="true" onClick={onToggle}
        onMouseEnter={() => { if (!open) onToggle(); }}
        className={`${linkClass} flex items-center gap-1.5 ${group.items.some((i) => active(i.href)) ? "text-cyan-300" : ""}`}>
        {group.label}
        <svg viewBox="0 0 12 12" className={`size-3 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden>
          <path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div className={`absolute ${alignRight ? "right-0" : "left-0"} top-full z-50 pt-2`}>
          <ul className="w-72 rounded-xl border border-white/10 bg-[#0f2338] p-1.5 shadow-2xl">
            {group.items.map((item) => (
              <li key={item.href}>
                <Link href={item.href} onClick={onClose}
                  className={`block rounded-lg px-3 py-2 transition-colors hover:bg-white/10 ${active(item.href) ? "bg-cyan-400/10" : ""}`}>
                  <span className={`block text-[14px] font-medium ${active(item.href) ? "text-cyan-300" : "text-slate-100"}`}>{item.label}</span>
                  {item.hint && <span className="block text-[12px] text-slate-400">{item.hint}</span>}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState<string | null>(null);
  const [mobile, setMobile] = useState(false);
  const header = useRef<HTMLElement>(null);

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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(null); setMobile(false); } };
    const onClick = (e: MouseEvent) => { if (!header.current?.contains(e.target as Node)) setOpen(null); };
    window.addEventListener("keydown", onKey);
    window.addEventListener("click", onClick);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("click", onClick); };
  }, []);

  useEffect(() => { setOpen(null); setMobile(false); }, [pathname]);

  const path = (href: string) => href.split(/[?#]/)[0];
  const active = (href: string) => path(href) === pathname;

  return (
    <header ref={header}
      className={`sticky top-0 z-40 border-b border-white/10 text-white shadow-lg ${BRAND.mark === "ACM" ? "bg-[#0b1b2e]" : "bg-[#040e42]"}`}>
      <div className="mx-auto flex max-w-[1600px] items-center gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-3" aria-label={`${BRAND.mark} — ${BRAND.name}, home`}>
          {BRAND.mark === "ACM" ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/acm/logo.png" alt="" width={64} height={42} className="h-11 w-auto shrink-0 rounded-md" />
              <span className="flex flex-col leading-none">
                <span className="text-[30px] font-extrabold tracking-tight">{BRAND.mark}</span>
                <span className="mt-0.5 text-[13px] font-medium text-slate-200">{BRAND.name}</span>
              </span>
            </>
          ) : (
            // The wordmark already spells "PLM · Phrase Language Model".
            // eslint-disable-next-line @next/next/no-img-element
            <img src="/plm/logo.png" alt={`${BRAND.mark} — ${BRAND.name}`} width={754} height={144}
              className="h-10 w-auto shrink-0 sm:h-12" />
          )}
        </Link>

        <nav aria-label="Main" className="ml-auto hidden items-center gap-1 lg:flex">
          {MENU.map((entry, index) =>
            isGroup(entry) ? (
              <Dropdown key={entry.label} group={entry} open={open === entry.label} active={active}
                alignRight={index >= MENU.length - 2}
                onToggle={() => setOpen(open === entry.label ? null : entry.label)} onClose={() => setOpen(null)} />
            ) : (
              <Link key={entry.href} href={entry.href} className={`${linkClass} ${active(entry.href) ? "text-cyan-300" : ""}`}>
                {entry.label}
              </Link>
            ),
          )}
        </nav>

        {CTA && (
          <Link href={CTA.href}
            className="ml-auto shrink-0 rounded-lg bg-cyan-400 px-5 py-2.5 text-[15px] font-semibold text-[#0b1b2e] transition-colors hover:bg-cyan-300 lg:ml-4">
            {CTA.label}
          </Link>
        )}
        <button type="button" onClick={() => setMobile(!mobile)} aria-expanded={mobile} aria-controls="mobile-menu"
          className={`${linkClass} border border-white/20 lg:hidden ${CTA ? "" : "ml-auto"}`}>
          Menu
        </button>
      </div>

      {mobile && (
        <nav id="mobile-menu" aria-label="Main" className="border-t border-white/10 px-4 pb-4 lg:hidden">
          <ul className="flex flex-col gap-0.5 pt-2">
            {MENU.map((entry) =>
              isGroup(entry) ? (
                <li key={entry.label} className="pt-2">
                  <span className="px-3 text-[11px] font-bold uppercase tracking-widest text-cyan-400">{entry.label}</span>
                  <ul className="flex flex-col">
                    {entry.items.map((item) => (
                      <li key={item.href}><Link href={item.href} className={`${linkClass} block`}>{item.label}</Link></li>
                    ))}
                  </ul>
                </li>
              ) : (
                <li key={entry.href}><Link href={entry.href} className={`${linkClass} block`}>{entry.label}</Link></li>
              ),
            )}
          </ul>
        </nav>
      )}
    </header>
  );
}
