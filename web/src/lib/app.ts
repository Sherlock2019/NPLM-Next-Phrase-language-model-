/**
 * Which product this dashboard presents.
 *
 *   mlm (default)  the Meaning Language Model console; "/" is the Playground
 *   acm            ACM, the Butterfly Model: the Action–Worlds Consequence prediction Model (built on MLM); "/" opens the ACM home page
 *                  and the MLM Playground moves to /mlm. ACM's ./start.sh sets this.
 *
 * Set with NEXT_PUBLIC_APP_MODE when the dashboard starts (it is read at build/dev time).
 */

export const APP_MODE: "mlm" | "acm" = process.env.NEXT_PUBLIC_APP_MODE === "acm" ? "acm" : "mlm";

export const BRAND =
  APP_MODE === "acm"
    ? { mark: "ACM", name: "The Butterfly Model", tagline: "Action–Worlds Consequence prediction Model" }
    : { mark: "SP", name: "Meaning Language Model", tagline: "Understand meaning before predicting language" };

export interface MenuLink {
  href: string;
  label: string;
  hint?: string;
}
export interface MenuGroup {
  label: string;
  items: MenuLink[];
}
export type MenuEntry = MenuLink | MenuGroup;

const MLM_PAGES: MenuLink[] = [
  { href: "/phrase-dna", label: "Phrase DNA" },
  { href: "/context", label: "Context Graph" },
  { href: "/multilingual", label: "Multilingual" },
  { href: "/benchmark", label: "Benchmark" },
  { href: "/ablation", label: "Ablation" },
  { href: "/architecture", label: "Architecture" },
  { href: "/system", label: "System" },
];

/** The header menu. ACM mode follows the ACM design; every page stays reachable from it. */
export const MENU: MenuEntry[] =
  APP_MODE === "acm"
    ? [
        { href: "/acm/home#what", label: "What is ACM?" },
        { href: "/acm/home#why", label: "Why ACM?" },
        {
          label: "Prediction Modes",
          items: [
            { href: "/acm/scenario", label: "Scenario Engine: human behaviour", hint: "Scripts of how people react to an action: 8 scenarios" },
            { href: "/acm#phrase", label: "Action–Consequence Prediction", hint: "Consequences of one action sentence (rule engine)" },
            { href: "/acm/scene?source=image", label: "Object Image Prediction", hint: "Physical consequences from a scene" },
            { href: "/acm/scene?source=video", label: "Object Video Prediction", hint: "Outcomes from motion and interactions" },
          ],
        },
        {
          label: "How It Works",
          items: [
            { href: "/acm/home#so-what", label: "So what?", hint: "What ACM gives you that an LLM does not" },
            { href: "/acm/home#how", label: "How it works", hint: "Seven explicit steps, from a sentence to its blast radius" },
            { href: "/acm/home#unreal", label: "Physical world · Unreal Engine 5", hint: "Simulate an action's physical consequences before acting" },
            { href: "/acm/home#next", label: "What next", hint: "The research roadmap" },
            { href: "/acm/tour", label: "Step-by-step tour", hint: "Real outputs, ACM vs a language model" },
          ],
        },
        { href: "/acm/definitions", label: "Definitions" },
        {
          label: "Research",
          items: [
            { href: "/acm/inference", label: "What happens next?", hint: "53 actions answered with their reasoning" },
            { href: "/multimodal", label: "Text · Image · Video", hint: "One meaning from three kinds of evidence" },
            { href: "/mlm", label: "MLM Playground", hint: "The meaning layer under ACM" },
            ...MLM_PAGES,
          ],
        },
      ]
    : [
        { href: "/", label: "Playground" },
        ...MLM_PAGES.slice(0, 3),
        { href: "/acm", label: "ACM Demo" },
        { href: "/acm/inference", label: "What happens next?" },
        { href: "/multimodal", label: "Multimodal → ACM" },
        ...MLM_PAGES.slice(3),
      ];

/** The header's call to action (ACM mode). */
export const CTA: MenuLink | null = APP_MODE === "acm" ? { href: "/acm", label: "Try a Demo" } : null;
