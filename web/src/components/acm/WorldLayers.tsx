"use client";

/**
 * ACM's world model as a layer stack, read bottom-up like the OSI network model it borrows its
 * shape from: an action or event (0) happens in the physical world (1), is perceived (2), is
 * routed (3) to the world models that should examine it (4–8).
 *
 * WORLD_LAYERS mirrors acm.scene.layers.LAYERS in the ACM repo (the source of truth; the scene
 * bundle carries its own copy). The OSI column is an analogy for the shape of the stack.
 */

import { useState } from "react";
import type { LayerId, WorldLayer } from "@/lib/acm/scene";

export const WORLD_LAYERS: WorldLayer[] = [
  { level: 0, id: "action", icon: "🎬", name: "Action or event", examines: "Who acts, why, their goal and desired outcome, and what happens",
    osi: "Source", osi_role: "A networking application creates or receives information",
    engine: "The scene script (acm.scene): actors, goals, ordered events and their state changes; single sentences are parsed by MLM's phrase model", status: "working" },
  { level: 1, id: "physical", icon: "⚙️", name: "Physical world", examines: "Objects, materials, movement, forces, location and energy",
    osi: "Physical", osi_role: "Transmits raw bits as signals over a physical medium",
    engine: "Scene state tracks positions, holders and owners (2D player). Forces and materials: a 2D matter.js stand-in in the Image/Video chat; a 3D physics engine (Unreal Engine 5, Chaos) is planned", status: "partial" },
  { level: 2, id: "perception", icon: "👁️", name: "Perception and observation", examines: "Images, video, audio, speech, sensors and observations",
    osi: "Data Link", osi_role: "Transfers frames across a local network link",
    engine: "Scene observations and who can see or hear each event. Image/video recognition in the Image/Video chat uses replayed detections; a vision-language model and detector are planned", status: "partial" },
  { level: 3, id: "routing", icon: "🧭", name: "Consequence routing", examines: "Determines which world models, actors and systems should examine an event",
    osi: "Network", osi_role: "Addresses and routes packets across networks (routing)",
    engine: "acm.scene.layers.route: explicit rules over each event's verb, type, objects and effects, plus the events each consequence cites as evidence", status: "working" },
  { level: 4, id: "human_social", icon: "🧠", name: "Human and social", examines: "Goals, behaviour, dialogue, relationships and group reactions",
    osi: "Transport", osi_role: "Provides end-to-end data transport between applications",
    engine: "The script model (goals, stated positions, possible feelings, conflicts) and next scenes from the authored demo or the local next-action model", status: "working" },
  { level: 5, id: "digital", icon: "💻", name: "Digital and information systems", examines: "Applications, records, calculations, permissions and workflows",
    osi: "Session", osi_role: "Establishes, manages and ends communication sessions",
    engine: "Explicit state changes and calculations (rule engine: has(x, y), amounts). No external system (registry, bank) is connected", status: "partial" },
  { level: 6, id: "business", icon: "🏭", name: "Business and institutions", examines: "Organisations, operations, processes, finance and policies",
    osi: "Presentation", osi_role: "Represents or transforms data, including formats and encoding",
    engine: "Obligations in the scene (debts, agreements) and the rule engine's organisation-scoped impact rules", status: "partial" },
  { level: 7, id: "society", icon: "🏛️", name: "Society and collective systems", examines: "Economy, markets, society, public governance and politics",
    osi: "Application", osi_role: "Provides network services used by applications, such as web and email",
    engine: "The rule engine's society- and country-scoped impact rules. No economic or political model yet", status: "partial" },
  { level: 8, id: "planetary", icon: "🌍", name: "Planetary and ecosystem", examines: "Resources, pollution, biodiversity and sustainability",
    osi: "Beyond the stack", osi_role: "(no OSI layer: the outermost system every other one depends on)",
    engine: "The rule engine's earth-scoped impact rules (e.g. flying and emissions). No ecosystem model yet", status: "partial" },
];

/**
 * The laws each world follows: the consequence of an action is predicted separately in each
 * world, by that world's laws. Keyed by id (not stored on WorldLayer) so it also applies to the
 * layer lists carried by scene bundles. The atomic scale is folded into the physical world
 * rather than added as a level, so the stack stays aligned with acm.scene.layers.LAYERS.
 */
export const LAYER_LAWS: Record<LayerId, string> = {
  action: "The cause: an actor, their goal and the action, parsed into Phrase DNA",
  physical: "Physical laws: force, motion, gravity, friction, energy. At the atomic scale: atomic and chemical laws (bonds, reactions, heat)",
  perception: "Laws of vibration and signals: light, sound, waves and sensing",
  routing: "No laws of its own: sends each event to the worlds whose laws apply",
  human_social: "Behavioural and psychological laws of humans and animals: goals, emotions, reactions, relationships",
  digital: "Digital system laws: data, logic, permissions, protocols and workflows",
  business: "Institutional laws: contracts, policies, accounting and regulation",
  society: "Economic, legal and social laws: supply and demand, prices, law, trust and governance",
  planetary: "Earth laws: ecology, climate, resource cycles and biodiversity",
};

/** Fill per layer (presentation only), cool at the bottom to warm at the top. */
export const LAYER_FILL: Record<LayerId, string> = {
  action: "#0b1b2e", physical: "#e0e7ff", perception: "#dbeafe", routing: "#a5f3fc", human_social: "#ccfbf1",
  digital: "#dcfce7", business: "#fef9c3", society: "#fde68a", planetary: "#fed7aa",
};

const STATUS_TONE: Record<WorldLayer["status"], string> = {
  working: "text-emerald-600 ring-emerald-500/40 bg-emerald-500/10",
  partial: "text-amber-600 ring-amber-500/40 bg-amber-500/10",
  planned: "text-slate-500 ring-slate-400/40 bg-slate-400/10",
};
const STATUS_LABEL: Record<WorldLayer["status"], string> = { working: "working", partial: "partly modelled", planned: "planned" };

export function LayerStatus({ s }: { s: WorldLayer["status"] }) {
  return <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold ring-1 ${STATUS_TONE[s]}`}>{STATUS_LABEL[s]}</span>;
}

export function layerName(layers: WorldLayer[], id: string) {
  const l = layers.find((x) => x.id === id);
  return l ? `${l.icon} ${l.name}` : id;
}

/**
 * The stack itself: level 8 on top, the action at the bottom. Each row is a button. `count`
 * shows a per-layer number (e.g. consequences found there); `dim` greys out a layer.
 */
export function LayerStackView({ layers, selected, onSelect, count, dim }: {
  layers: WorldLayer[]; selected: LayerId | null; onSelect: (id: LayerId) => void;
  count?: (id: LayerId) => number | null; dim?: (id: LayerId) => boolean;
}) {
  return (
    <ol className="flex flex-col gap-1" aria-label="ACM world layers, top to bottom">
      {[...layers].reverse().map((l) => {
        const on = selected === l.id;
        const source = l.id === "action";
        const router = l.id === "routing";
        const n = count?.(l.id);
        return (
          <li key={l.id}>
            <button type="button" onClick={() => onSelect(l.id)} aria-pressed={on}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left ring-1 transition ${on ? "ring-2 ring-cyan-500" : "ring-black/5"} ${dim?.(l.id) ? "opacity-45" : ""} ${router ? "border-y-2 border-dashed border-cyan-600/50" : ""}`}
              style={{ background: LAYER_FILL[l.id], color: source ? "#fff" : "#0b1b2e" }}>
              <span className="num w-5 shrink-0 text-center text-[12px] font-bold opacity-70">{source ? "·" : l.level}</span>
              <span aria-hidden className="text-[18px]">{l.icon}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13.5px] font-bold leading-tight">{l.name}</span>
                <span className="block text-[11.5px] leading-snug opacity-80"><span aria-hidden>⚖️ </span>{LAYER_LAWS[l.id] ?? l.examines}</span>
              </span>
              {n != null && <span className="num shrink-0 rounded-full bg-white/70 px-2 py-0.5 text-[11px] font-bold text-[#0b1b2e]">{n}</span>}
              <span className="hidden shrink-0 rounded bg-black/10 px-1.5 py-0.5 text-[10.5px] font-semibold sm:inline">OSI · {l.osi}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

export function LayerFacts({ l }: { l: WorldLayer }) {
  return (
    <dl className="grid gap-x-3 gap-y-1.5 text-[13px] sm:grid-cols-[110px_1fr]">
      {LAYER_LAWS[l.id] && <><dt className="faint font-semibold">Its laws</dt><dd className="font-semibold">{LAYER_LAWS[l.id]}</dd></>}
      <dt className="faint font-semibold">Examines</dt><dd>{l.examines}</dd>
      <dt className="faint font-semibold">In ACM today</dt><dd className="flex flex-col items-start gap-1"><LayerStatus s={l.status} /><span>{l.engine}</span></dd>
      <dt className="faint font-semibold">OSI analogy</dt><dd><b>{l.osi}</b>: {l.osi_role}</dd>
    </dl>
  );
}

/** The home page version: the generic stack with a description of each layer. */
export function WorldLayersIntro({ layers = WORLD_LAYERS }: { layers?: WorldLayer[] }) {
  const [sel, setSel] = useState<LayerId>("routing");
  const l = layers.find((x) => x.id === sel) ?? layers[0];
  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-cyan-500">ACM world model</p>
        <h3 className="text-[22px] font-extrabold tracking-tight">Eight layers above every action</h3>
        <p className="dim max-w-3xl text-[13.5px] leading-relaxed">
          Read it bottom-up, like the OSI network stack it borrows its shape from. An action happens in the physical world and is perceived. The
          <b className="text-[var(--text)]"> consequence router</b> then decides which world models, actors and systems should examine it: people,
          digital systems, institutions, society and the planet. <b className="text-[var(--text)]">Each world follows its own laws</b> (⚖️), from
          atomic and physical laws up to earth laws, and the consequence of an action is predicted in each world by those laws. Every consequence
          names the layer it belongs to.
        </p>
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <LayerStackView layers={layers} selected={sel} onSelect={setSel} />
        <section className="panel-raised flex flex-col gap-3 p-4" aria-live="polite">
          <header>
            <p className="text-[11px] font-bold uppercase tracking-wider text-cyan-500">{l.id === "action" ? "The source" : `Layer ${l.level}`}</p>
            <h4 className="text-[18px] font-bold">{l.icon} {l.name}</h4>
          </header>
          <LayerFacts l={l} />
          <p className="faint border-t border-[var(--border)] pt-2 text-[11.5px]">
            Layers and rings are two axes. A <b>layer</b> says which kind of system a consequence is about and which model examines it; a <b>ring</b> (below)
            says how far it reaches, from the actor to the world. The OSI column is an analogy for the stack's shape, not a networking claim.
          </p>
        </section>
      </div>
    </div>
  );
}
