import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { ThemeToggle } from "@/components/ThemeToggle";
import { APP_MODE } from "@/lib/app";

export const metadata: Metadata =
  APP_MODE === "acm"
    ? {
        title: "ARM — Action Reaction Model",
        description:
          "Every action has consequences: ARM explores possible reactions and outcomes across human decisions, objects, images and videos, built on ACM and the Meaning Language Model.",
      }
    : {
        title: "Meaning Language Model",
        description:
          "Understand meaning before predicting language. A research console comparing a standard Transformer against the same Transformer with an explicit linguistic and semantic layer.",
      };

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <div className="flex min-h-screen flex-col">
          <Nav />
          <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 pb-16 pt-6 sm:px-6">
            {children}
          </main>
          <footer className="hairline border-t px-4 py-4 sm:px-6">
            <div className="mx-auto flex max-w-[1600px] items-start gap-4">
            <p className="faint flex-1 text-xs leading-relaxed">
              {APP_MODE === "acm" ? (
                <>
                  ACM predicts consequences from rules (its knowledge packs), a constrained tabletop simulator and declared
                  assumptions, on meaning read by MLM. &quot;No supporting evidence&quot; means no rule matched, never &quot;no impact&quot;;
                  certainty values are rule weights, not calibrated probabilities. Demo results replay bundled examples and
                  say so.
                </>
              ) : (
                <>
              Every figure shown is measured at request time from the running system,
              except on the Multimodal page in Demo mode, which replays bundled examples
              and says so. MLM is a hypothesis under test, not a proven improvement: where
              the evidence does not support a claim, this dashboard says so.
                </>
              )}
            </p>
            <ThemeToggle />
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
