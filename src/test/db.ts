import "./env"; // must be first: forces the in-memory DB before "@/db" loads
import { sql } from "drizzle-orm";
import { db, ensureReady } from "@/db";

let initialized = false;

/**
 * The tables we know about, used as a fallback if runtime discovery returns
 * nothing. Runtime discovery (below) is tried first, so newly added tables are
 * cleaned automatically without editing this list.
 */
const KNOWN_TABLES = [
  "events",
  "notifications",
  "workflow_executions",
  "workflow_rules",
  "stock_movements",
  "sale_items",
  "sales",
  "purchase_items",
  "purchases",
  "expenses",
  "parties",
  "products",
  "users",
  "businesses",
];

async function publicTableNames(): Promise<string[]> {
  try {
    const res = (await db.execute(
      sql`SELECT tablename FROM pg_tables WHERE schemaname = 'public'`,
    )) as unknown as { rows?: Array<{ tablename?: string }> } | Array<{ tablename?: string }>;
    const rows = Array.isArray(res) ? res : res?.rows ?? [];
    const names = rows.map((r) => r?.tablename).filter((n): n is string => Boolean(n));
    if (names.length > 0) return names;
  } catch {
    // fall through to the static list
  }
  return KNOWN_TABLES;
}

/**
 * Deletes every row from every application table. TRUNCATE ... CASCADE means we
 * do not have to care about foreign-key ordering, and RESTART IDENTITY resets any
 * sequences. Called after every test so nothing a test wrote survives it.
 */
export async function truncateAll(): Promise<void> {
  const tables = await publicTableNames();
  if (tables.length === 0) return;
  const list = tables.map((t) => `"${t}"`).join(", ");
  await db.execute(sql.raw(`TRUNCATE TABLE ${list} RESTART IDENTITY CASCADE`));
}

/**
 * Call this in beforeEach(). It initializes the in-memory database once
 * (applying migrations from ./drizzle), then wipes it so every test starts from
 * a clean, empty slate.
 */
export async function setupTestDb(): Promise<void> {
  if (!initialized) {
    await ensureReady(); // creates in-memory PGlite, applies migrations, seeds demo once
    initialized = true;
  }
  await truncateAll();
}

export { db };
