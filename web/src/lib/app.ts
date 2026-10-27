/**
 * Which product this dashboard presents.
 *
 *   mlm (default)  the Meaning Language Model console; "/" is the Playground
 *   acm            the Actions Consequential Model; "/" opens the ACM demo and the
 *                  MLM Playground moves to /mlm. ACM's ./start.sh sets this.
 *
 * Set with NEXT_PUBLIC_APP_MODE when the dashboard starts (it is read at build/dev time).
 */

export const APP_MODE: "mlm" | "acm" = process.env.NEXT_PUBLIC_APP_MODE === "acm" ? "acm" : "mlm";

export const BRAND =
  APP_MODE === "acm"
    ? { mark: "ACM", name: "Actions Consequential Model", tagline: "See what an action changes before taking it" }
    : { mark: "SP", name: "Meaning Language Model", tagline: "Understand meaning before predicting language" };

const MLM_PAGES = [
  { href: "/phrase-dna", label: "Phrase DNA" },
  { href: "/inspector", label: "Inspector" },
  { href: "/context", label: "Context Graph" },
  { href: "/multilingual", label: "Multilingual" },
  { href: "/benchmark", label: "Benchmark" },
  { href: "/ablation", label: "Ablation" },
  { href: "/architecture", label: "Architecture" },
  { href: "/system", label: "System" },
];

/** `primary` pages sit in the header's top row, the rest in the second row. */
export const PAGES: { href: string; label: string; primary?: boolean }[] =
  APP_MODE === "acm"
    ? [
        { href: "/acm/tour", label: "Tour", primary: true },
        { href: "/acm", label: "ACM Demo", primary: true },
        { href: "/acm/inference", label: "What happens next?", primary: true },
        { href: "/multimodal", label: "Text · Image · Video", primary: true },
        { href: "/mlm", label: "MLM Playground" },
        ...MLM_PAGES,
      ]
    : [
        { href: "/", label: "Playground", primary: true },
        ...MLM_PAGES.slice(0, 3).map((p) => ({ ...p, primary: true })),
        { href: "/acm", label: "ACM Demo" },
        { href: "/acm/inference", label: "What happens next?" },
        { href: "/multimodal", label: "Multimodal → ACM" },
        ...MLM_PAGES.slice(3),
      ];
