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

export const PAGES =
  APP_MODE === "acm"
    ? [
        { href: "/acm", label: "ACM Demo" },
        { href: "/multimodal", label: "Text · Image · Video" },
        { href: "/mlm", label: "MLM Playground" },
        ...MLM_PAGES,
      ]
    : [
        { href: "/", label: "Playground" },
        ...MLM_PAGES.slice(0, 3),
        { href: "/acm", label: "ACM Demo" },
        { href: "/multimodal", label: "Multimodal → ACM" },
        ...MLM_PAGES.slice(3),
      ];
