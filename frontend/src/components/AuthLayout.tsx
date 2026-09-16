import type { ReactNode } from "react";
import { BrandLockup } from "@/components/Brand";

const POINTS = [
  "Natural-language & OCR business input",
  "Automatic inventory + workflow engine",
  "Real-time dashboard & business health",
];

/** The shared shell for sign-in and sign-up: a lime brand panel beside the
 *  form. The brand panel keeps its colour in both themes — it *is* the brand —
 *  while the form panel follows the app surface, so the split reads the same
 *  whether the user is in light or dark mode.
 *
 *  Below `lg` the panel collapses to a banner above the form rather than
 *  disappearing, so the product still introduces itself on a phone. */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <aside className="relative isolate overflow-hidden bg-primary px-6 py-10 text-primary-foreground sm:px-10 lg:flex lg:flex-col lg:justify-between lg:px-14 lg:py-14">
        {/* A soft wash from the top-right corner. The two outlined rings that
            used to sit over it read as an unexplained diagram rather than as
            texture, so they are gone; the gradient alone gives the panel depth
            without putting a shape on screen that means nothing. */}
        <div
          aria-hidden
          className="pointer-events-none absolute -right-32 -top-40 -z-10 h-[34rem] w-[34rem] rounded-full opacity-[0.07] [background:radial-gradient(circle,var(--primary-foreground)_0%,transparent_65%)]"
        />

        <BrandLockup tone="contrast" />

        <div className="mt-12 max-w-lg lg:mt-0">
          <h1 className="text-[2rem] font-bold leading-[1.1] tracking-[-0.035em] sm:text-[2.6rem]">
            Run your business on autopilot.
          </h1>
          <p className="mt-5 max-w-md text-[15px] leading-relaxed opacity-75">
            Event-driven ERP with an AI input engine. Type a note or snap a photo of a bill and
            SmartSME turns it into sales, purchases, inventory updates and alerts automatically.
          </p>
          <ul className="mt-9 flex flex-col gap-3.5">
            {POINTS.map((point) => (
              <li key={point} className="flex items-start gap-3 text-[0.9375rem] font-medium">
                <span aria-hidden className="mt-px opacity-55">
                  ✦
                </span>
                {point}
              </li>
            ))}
          </ul>
        </div>

        <p className="mt-12 max-w-sm text-xs leading-relaxed opacity-55 lg:mt-0">
          Every entry lands in your own PostgreSQL and is replayed through the event bus, so stock,
          balances and alerts stay in step.
        </p>
      </aside>

      <main className="flex items-center justify-center bg-background px-6 py-14 sm:px-10">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}
