"use client";

/**
 * "2 · Image / video chat": the five stages from a scene to predicted frames.
 *   1 scene  ->  2 computer vision + object libraries + environment physics  ->  3 the action
 *   ->  4 physics engine simulates the consequences  ->  5 output frames / video
 * Drawn in the infographic's light palette (it sits between the infographic's images).
 */

type Icon = "scene" | "vision" | "action" | "engine" | "output";

function Glyph({ name }: { name: Icon }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 48 48" className="size-11 shrink-0" aria-hidden>
      {name === "scene" && (
        <g {...common}>
          <rect x="5" y="9" width="38" height="30" rx="3" />
          <path d="M5 33l11-11 9 9 6-6 12 12" />
          <circle cx="33" cy="17" r="3.5" />
        </g>
      )}
      {name === "vision" && (
        <g {...common}>
          <path d="M5 14V8h6M37 8h6v6M43 34v6h-6M11 40H5v-6" />
          <path d="M9 24s6-9 15-9 15 9 15 9-6 9-15 9-15-9-15-9z" />
          <circle cx="24" cy="24" r="4.5" />
        </g>
      )}
      {name === "action" && (
        <g {...common}>
          <circle cx="13" cy="28" r="7" />
          <circle cx="36" cy="28" r="7" />
          <path d="M21 28h6M24 25l3 3-3 3" />
          <path d="M28 14l2 4M33 12v4M38 14l-2 4" />
        </g>
      )}
      {name === "engine" && (
        <g {...common}>
          <circle cx="24" cy="24" r="6" />
          <path d="M24 6v6M24 36v6M6 24h6M36 24h6M11.3 11.3l4.2 4.2M32.5 32.5l4.2 4.2M11.3 36.7l4.2-4.2M32.5 15.5l4.2-4.2" />
        </g>
      )}
      {name === "output" && (
        <g {...common}>
          <rect x="6" y="10" width="36" height="28" rx="2" />
          <path d="M6 16h36M6 32h36M12 10v6M20 10v6M28 10v6M36 10v6M12 32v6M20 32v6M28 32v6M36 32v6" />
          <path d="M21 20v8l7-4z" fill="currentColor" />
        </g>
      )}
    </svg>
  );
}

const STAGES: { icon: Icon; title: string; tone: string; text: string; example: string; today: string }[] = [
  {
    icon: "scene", title: "Scene", tone: "bg-violet-100 text-violet-900",
    text: "An image or a video of the scene.",
    example: "a mug near the edge of a kitchen table, a hand next to it",
    today: "built-in demo image and clip",
  },
  {
    icon: "vision", title: "Recognise objects + environment", tone: "bg-cyan-100 text-cyan-900",
    text: "Computer vision identifies each object and matches it to the library of its environment (kitchen, house, garden, street, mountain). Each library object carries its physical properties; the environment is loaded into a physics engine like Unreal Engine 5.",
    example: "mug → ceramic · 0.3 kg · cylinder · smooth glaze · μ 0.35 · breaks above 2.5 m/s",
    today: "recognition is mocked; libraries are real data",
  },
  {
    icon: "action", title: "The action", tone: "bg-violet-100 text-violet-900",
    text: "The action to test, stated in text or seen in the image / video (for example a collision).",
    example: "“push the mug 20 cm toward the edge” · or: the hand hits the mug at T = 2 s",
    today: "from the menu, the video, or your question (read by the LLM)",
  },
  {
    icon: "engine", title: "Physics engine simulates", tone: "bg-cyan-100 text-cyan-900",
    text: "The engine runs the action with the objects' properties: slides, tips, falls, collisions. ACM turns the events into consequences and marks what it cannot know as unknown.",
    example: "slides → crosses the edge → falls → hits the floor at 3.7 m/s → may break · spill: unknown",
    today: "matter.js stands in for Unreal Engine 5",
  },
  {
    icon: "output", title: "Output frames or video", tone: "bg-violet-100 text-violet-900",
    text: "The predicted outcome as frames or a video of what would happen next, with ACM's consequences and answers to your questions.",
    example: "replay + event timeline + blast-radius rings + chat answers",
    today: "a 2D side-view replay, not a rendered video yet",
  },
];

export function SceneFlow({ compact = false }: { compact?: boolean }) {
  return (
    <section
      aria-label="Image / video chat: from a scene to predicted frames"
      className="rounded-xl border border-sky-200 bg-[#eef6fb] p-3 text-[#1e2a4a] sm:p-4"
    >
      {!compact && (
        <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="grid size-9 place-items-center rounded-full bg-[#1e3a6e] font-serif text-[18px] font-bold text-white">2</span>
          <h2 className="font-serif text-[26px] font-bold leading-none text-[#1e2f5e]">· Image / video chat</h2>
          <span className="font-serif text-[15px] text-[#33415f]">Ask a question about a scene (image or video).</span>
        </div>
      )}
      <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {STAGES.map((s, i) => (
          <li key={s.title} className="relative flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-2.5 shadow-sm">
            <div className={`flex items-center gap-2 rounded-md px-2 py-1.5 ${s.tone}`}>
              <span className="grid size-6 shrink-0 place-items-center rounded-full bg-[#4c3ca8] text-[12px] font-bold text-white">{i + 1}</span>
              <span className="font-serif text-[15px] font-bold leading-tight">{s.title}</span>
            </div>
            <div className="flex items-start gap-2">
              <span className={i % 2 ? "text-cyan-700" : "text-violet-700"}><Glyph name={s.icon} /></span>
              <p className="text-[12px] leading-snug">{s.text}</p>
            </div>
            <p className="rounded bg-slate-50 px-2 py-1 font-serif text-[11.5px] italic leading-snug text-[#33415f]">e.g. {s.example}</p>
            <p className="mt-auto text-[10.5px] text-amber-700">today: {s.today}</p>
            {i < STAGES.length - 1 && (
              <span aria-hidden className="absolute -right-2.5 top-1/2 z-10 hidden text-[18px] text-slate-400 lg:block">→</span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
