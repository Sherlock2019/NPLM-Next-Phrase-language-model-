"use client";

/**
 * ARM home: "Every action has consequences." A hero, what ARM is and why, and four ways in:
 * actions (phrase), object images, object videos, and (concept) objects & human behaviour.
 * Pictures are cropped from the design (public/acm/home-*.webp).
 */

import Link from "next/link";

const svg = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

function Person({ x, y }: { x: number; y: number }) {
  return (
    <g {...svg}>
      <circle cx={x} cy={y} r={4} />
      <path d={`M${x - 6} ${y + 13}c0-5 3-7 6-7s6 2 6 7z`} />
    </g>
  );
}

const ICONS = {
  actions: (
    <svg viewBox="0 0 64 64" className="size-14" aria-hidden>
      <Person x={32} y={8} />
      <path {...svg} d="M32 24v8M14 32h36M14 32v6M32 32v6M50 32v6" />
      <Person x={14} y={44} /><Person x={32} y={44} /><Person x={50} y={44} />
    </svg>
  ),
  image: (
    <svg viewBox="0 0 48 48" className="size-11" aria-hidden>
      <g {...svg} strokeWidth={2.4}><rect x="5" y="8" width="38" height="32" rx="4" /><path d="M5 34l11-11 9 9 6-6 12 12" /><circle cx="33" cy="17" r="3.5" /></g>
    </svg>
  ),
  video: (
    <svg viewBox="0 0 48 48" className="size-11" aria-hidden>
      <rect {...svg} strokeWidth={2.4} x="5" y="8" width="38" height="32" rx="4" />
      <path d="M20 17v14l12-7z" fill="currentColor" />
    </svg>
  ),
  people: (
    <svg viewBox="0 0 64 48" className="h-12 w-16" aria-hidden>
      <g {...svg} strokeWidth={2.2}>
        <path d="M6 22l12-6 12 6v14l-12 6-12-6zM6 22l12 6 12-6M18 28v14" />
        <circle cx="46" cy="7" r="4" />
        <path d="M46 12l-3 12 6 6v12M43 24l-5 6M46 15l7 6M49 30l-6 12" />
      </g>
    </svg>
  ),
};

const MODES = [
  {
    n: "01", icon: ICONS.actions, title: "Action–Reaction", sub: "Human actions & consequences",
    text: "Explore how a decision could affect people and situations.",
    example: "A manager changes a deadline. What could follow?",
    href: "/acm#phrase", cta: "Explore Actions",
  },
  {
    n: "02", icon: ICONS.image, title: "Object Image", sub: "Physical outcomes from a scene",
    text: "Identify objects, define an action, and simulate possible consequences.",
    img: "/acm/home-image.webp", alt: "A red mug on a wooden table, outlined by an object-detection box",
    href: "/acm/scene?source=image", cta: "Explore Images",
  },
  {
    n: "03", icon: ICONS.video, title: "Object Video", sub: "Motion & interaction predictions",
    text: "Track objects and simulate what could happen next.",
    img: "/acm/home-video.webp", alt: "Video frames of a red mug sliding, tipping and falling off a table",
    href: "/acm/scene?source=video", cta: "Explore Videos",
  },
  {
    n: "04", icon: ICONS.people, title: "Objects & Human Behavior", sub: "Images, videos & human responses",
    text: "Explore interactions between people, objects, and their environment.",
    img: "/acm/home-people.webp", alt: "A worker walking through a warehouse past a cart of boxes, with predicted paths drawn on the floor",
    href: null, cta: "Explore Interactions",
  },
];

export default function HomePage() {
  return (
    <div className="flex flex-col gap-6">
      {/* hero: fixed dark, like the design */}
      <section className="relative overflow-hidden rounded-2xl bg-[#0b1b2e] text-white">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/acm/home-hero.webp" alt="" aria-hidden width={836} height={308}
          className="absolute inset-y-0 right-0 hidden h-full w-auto max-w-none object-cover md:block" />
        <div aria-hidden className="absolute inset-0 hidden bg-gradient-to-r from-[#0b1b2e] via-[#0b1b2e]/85 to-transparent md:block" />
        <div className="relative flex flex-col gap-4 px-6 py-10 sm:px-10 sm:py-14 md:max-w-[62%]">
          <p className="text-[12px] font-bold uppercase tracking-[0.3em] text-cyan-400">Action → Reaction → Consequence</p>
          <h1 className="text-[44px] font-extrabold leading-[1.02] tracking-tight sm:text-[64px]">
            Every action has <span className="text-cyan-400">consequences.</span>
          </h1>
          <p className="max-w-xl text-[17px] leading-relaxed text-slate-200 sm:text-[20px]">
            Explore possible reactions and outcomes across human decisions, objects, images, and videos.
          </p>
        </div>
      </section>

      {/* what / why */}
      <div className="grid gap-4 md:grid-cols-2">
        {[
          { id: "what", mark: "?", title: "What is ARM?", text: "A proposed framework for modeling actions, reactions, and consequences in human and physical scenarios." },
          { id: "why", mark: "✦", title: "Why ARM?", text: "Language fluency alone does not guarantee a reliable world model. ARM aims to ground predictions in explicit context, rules, and simulation." },
        ].map((c) => (
          <section key={c.title} id={c.id} className="panel flex scroll-mt-[calc(var(--nav-h,72px)+16px)] items-start gap-4 p-5">
            <span aria-hidden className="grid size-12 shrink-0 place-items-center rounded-full bg-cyan-400/15 text-[22px] font-bold text-cyan-500">{c.mark}</span>
            <div>
              <h2 className="text-[19px] font-bold">{c.title}</h2>
              <p className="dim mt-1 text-[14px] leading-relaxed">{c.text}</p>
            </div>
          </section>
        ))}
      </div>

      {/* modes */}
      <section id="modes" className="flex scroll-mt-[calc(var(--nav-h,72px)+16px)] flex-col gap-4">
        <h2 className="text-[30px] font-extrabold tracking-tight">Choose what you want to explore</h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {MODES.map((m) => (
            <article key={m.n} className="panel flex flex-col gap-3 p-4">
              <div className="flex items-start gap-3">
                <span className="text-[15px] font-bold text-cyan-500">{m.n}</span>
                <span className="shrink-0 text-[var(--text)]">{m.icon}</span>
                <div className="min-w-0">
                  <h3 className="text-[17px] font-bold leading-tight">{m.title}</h3>
                  <p className="dim text-[12.5px]">{m.sub}</p>
                </div>
              </div>
              <p className="text-[14px] leading-relaxed">{m.text}</p>
              {m.img ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={m.img} alt={m.alt} width={310} height={134} className="mt-auto block h-auto w-full rounded-md object-cover" />
              ) : (
                <p className="mt-auto flex items-start gap-2 rounded-lg bg-cyan-400/10 p-4 text-[14px] leading-snug">
                  <span aria-hidden className="text-[20px] leading-none text-cyan-500">💬</span>
                  {m.example}
                </p>
              )}
              {m.href ? (
                <Link href={m.href} className="flex items-center justify-center gap-2 rounded-lg bg-[#0b1b2e] px-4 py-2.5 text-[15px] font-semibold text-white ring-1 ring-white/10 transition-colors hover:bg-[#13304f]">
                  {m.cta} <span aria-hidden>→</span>
                </Link>
              ) : (
                <span className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--border)] px-4 py-2.5 text-[14px] font-semibold text-[var(--text-dim)]"
                  title="Not built yet: people's responses are not modelled in this prototype">
                  Concept — coming later
                </span>
              )}
            </article>
          ))}
        </div>
      </section>

      <footer className="hairline flex flex-wrap items-center gap-x-6 gap-y-2 border-t pt-4 text-[13px]">
        <p className="faint">Concept preview · Physical simulations depend on assumptions. Human responses are uncertain scenarios.</p>
        <nav aria-label="More" className="dim ml-auto flex flex-wrap gap-x-4">
          <Link href="/mlm" className="hover:text-[var(--text)]">Language &amp; Reasoning</Link>
          <Link href="/benchmark" className="hover:text-[var(--text)]">Evaluation</Link>
          <Link href="/architecture" className="hover:text-[var(--text)]">Architecture</Link>
          <Link href="/system" className="hover:text-[var(--text)]">System</Link>
        </nav>
      </footer>
    </div>
  );
}
