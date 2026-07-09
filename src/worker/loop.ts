import { and, asc, eq } from "drizzle-orm";
import { db } from "@/db";
import { events } from "@/db/schema";
import { runWorkflowRules } from "@/lib/workflow/engine";

const MAX_RETRIES = 5;
const POLL_MS = 1000;
const BATCH = 20;

const globalForWorker = globalThis as unknown as {
  __smartsmeWorker?: ReturnType<typeof setInterval>;
  __smartsmeTickRunning?: boolean;
};

// True on Vercel / serverless, where a background setInterval can't run
// reliably (the function freezes between requests).
const isServerless = Boolean(process.env.VERCEL) || process.env.SMARTSME_NO_WORKER === "1";

/**
 * Processes one batch of pending events. Claims each (SET status='processing'),
 * runs its workflow rules, marks it done — or retries with a bounded count and
 * dead-letters after MAX_RETRIES. Returns the number of events processed.
 */
async function processBatch(): Promise<number> {
  const pending = await db
    .select()
    .from(events)
    .where(eq(events.status, "pending"))
    .orderBy(asc(events.createdAt))
    .limit(BATCH);

  let processed = 0;
  for (const ev of pending) {
    // Atomic claim — guards against double-processing if two drains overlap.
    const claimed = await db
      .update(events)
      .set({ status: "processing" })
      .where(and(eq(events.id, ev.id), eq(events.status, "pending")))
      .returning({ id: events.id });
    if (claimed.length === 0) continue;

    processed++;
    try {
      await runWorkflowRules(ev);
      await db
        .update(events)
        .set({ status: "done", processedAt: new Date(), error: null })
        .where(eq(events.id, ev.id));
    } catch (err) {
      const next = ev.retryCount + 1;
      const status = next >= MAX_RETRIES ? "dead" : "pending";
      await db
        .update(events)
        .set({ status, retryCount: next, error: String(err instanceof Error ? err.message : err) })
        .where(eq(events.id, ev.id));
    }
  }
  return processed;
}

// One guarded tick (used by the interval on long-running hosts).
export async function tick(): Promise<void> {
  if (globalForWorker.__smartsmeTickRunning) return;
  globalForWorker.__smartsmeTickRunning = true;
  try {
    await processBatch();
  } finally {
    globalForWorker.__smartsmeTickRunning = false;
  }
}

/**
 * Drains the whole queue synchronously, following event chains (a sale emits
 * STOCK_UPDATED, which may raise alerts) until nothing is left. Called right
 * after a business write so effects apply within the request — the mechanism
 * that makes the event bus work on serverless where the interval can't run.
 */
export async function drainQueue(maxRounds = 12): Promise<number> {
  let total = 0;
  for (let i = 0; i < maxRounds; i++) {
    const n = await processBatch();
    total += n;
    if (n === 0) break;
  }
  return total;
}

export function startWorker(): void {
  if (isServerless) {
    // On serverless we drain synchronously after each write (see drainQueue),
    // and/or via the /api/worker cron endpoint — no background interval.
    return;
  }
  if (globalForWorker.__smartsmeWorker) return;
  globalForWorker.__smartsmeWorker = setInterval(() => {
    tick().catch((e) => console.error("[worker] tick failed:", e));
  }, POLL_MS);
  console.log("✅ SmartSME event worker running (polling every 1s)…");
}

export function stopWorker(): void {
  if (globalForWorker.__smartsmeWorker) {
    clearInterval(globalForWorker.__smartsmeWorker);
    globalForWorker.__smartsmeWorker = undefined;
  }
}
