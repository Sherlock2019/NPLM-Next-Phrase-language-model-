/**
 * Which product this dashboard presents.
 *
 *   mlm (default)  the Meaning Language Model console; "/" is the Playground
 *   acm            ARM, the Action Reaction Model (built on ARM); "/" opens the ARM home page
 *                  and the MLM Playground moves to /mlm. ARM's ./start.sh sets this.
 *
 * Set with NEXT_PUBLIC_APP_MODE when the dashboard starts (it is read at build/dev time).
 */

export const APP_MODE: "mlm" | "acm" = process.env.NEXT_PUBLIC_APP_MODE === "acm" ? "acm" : "mlm";

export const BRAND =
  APP_MODE === "acm"
    ? { mark: "ARM", name: "Action Reaction Model", tagline: "Every action has consequences" }
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

/** The header menu. ARM mode follows the ARM design; every page stays reachable from it. */
export const MENU: MenuEntry[] =
  APP_MODE === "acm"
    ? [
        { href: "/acm/home#what", label: "What is ARM?" },
        { href: "/acm/home#why", label: "Why ARM?" },
        {
          label: "Prediction Modes",
          items: [
            { href: "/acm#phrase", label: "Action–Reaction Prediction", hint: "Consequences and reactions to human actions" },
            { href: "/acm/scene?source=image", label: "Object Image Prediction", hint: "Physical consequences from a scene" },
            { href: "/acm/scene?source=video", label: "Object Video Prediction", hint: "Outcomes from motion and interactions" },
            { href: "/acm/home#modes", label: "Objects & Human Behavior", hint: "People, objects, images and video combined — concept" },
          ],
        },
        { href: "/acm/tour", label: "How It Works" },
        { href: "/acm/definitions", label: "Definitions" },
        {
          label: "Research",
          items: [
            { href: "/acm/inference", label: "What happens next?", hint: "53 actions answered with their reasoning" },
            { href: "/multimodal", label: "Text · Image · Video", hint: "One meaning from three kinds of evidence" },
            { href: "/mlm", label: "MLM Playground", hint: "The meaning layer under ARM" },
            ...MLM_PAGES,
          ],
        },
      ]
    : [
        { href: "/", label: "Playground" },
        ...MLM_PAGES.slice(0, 3),
        { href: "/acm", label: "ARM Demo" },
        { href: "/acm/inference", label: "What happens next?" },
        { href: "/multimodal", label: "Multimodal → ARM" },
        ...MLM_PAGES.slice(3),
      ];

/** The header's call to action (ARM mode). */
export const CTA: MenuLink | null = APP_MODE === "acm" ? { href: "/acm", label: "Try a Demo" } : null;
