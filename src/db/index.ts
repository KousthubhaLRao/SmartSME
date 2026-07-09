import { sql } from "drizzle-orm";
import type { PgliteDatabase } from "drizzle-orm/pglite";
import * as schema from "./schema";

// A single exported `db` type keeps the rest of the app driver-agnostic.
export type Database = PgliteDatabase<typeof schema>;

export const usingPglite = !process.env.DATABASE_URL;

const g = globalThis as unknown as {
  __smartsmeDb?: Database;
  __smartsmeReady?: Promise<void>;
};

// All driver imports are dynamic + webpackIgnore so the bundler never tries to
// bundle postgres/PGlite (and their node:net / node:crypto / WASM deps) — which
// breaks in the instrumentation/edge compilation layers. They resolve natively
// at runtime instead.
async function initDb(): Promise<Database> {
  const url = process.env.DATABASE_URL;
  if (url) {
    const { default: postgres } = await import(/* webpackIgnore: true */ "postgres");
    const { drizzle } = await import(/* webpackIgnore: true */ "drizzle-orm/postgres-js");
    // prepare:false is required for pooled endpoints (e.g. Neon's PgBouncer
    // transaction pooler), which don't support session-level prepared statements.
    const client = postgres(url, { max: 10, prepare: false });
    return drizzle(client, { schema }) as unknown as Database;
  }
  const { PGlite } = await import(/* webpackIgnore: true */ "@electric-sql/pglite");
  const { drizzle } = await import(/* webpackIgnore: true */ "drizzle-orm/pglite");
  const dir = process.env.PGLITE_DIR || ".pgdata";
  const client = new PGlite(dir);
  return drizzle(client, { schema }) as unknown as Database;
}

// `db` is a thin proxy over the initialized instance. ensureReady() (awaited by
// instrumentation before the server serves requests) sets the real instance, so
// server components and actions can use `db` synchronously.
export const db: Database = new Proxy({} as Database, {
  get(_t, prop) {
    const real = g.__smartsmeDb;
    if (!real) {
      throw new Error(
        "Database not initialized. ensureReady() runs from instrumentation before requests are served.",
      );
    }
    const value = (real as unknown as Record<string | symbol, unknown>)[prop];
    return typeof value === "function" ? (value as (...a: unknown[]) => unknown).bind(real) : value;
  },
});

async function runMigrations(): Promise<void> {
  const target = g.__smartsmeDb as never;
  if (usingPglite) {
    const { migrate } = await import(/* webpackIgnore: true */ "drizzle-orm/pglite/migrator");
    await migrate(target, { migrationsFolder: "drizzle" });
  } else {
    const { migrate } = await import(/* webpackIgnore: true */ "drizzle-orm/postgres-js/migrator");
    await migrate(target, { migrationsFolder: "drizzle" });
  }
}

/**
 * Initializes the driver, applies migrations, and seeds demo data — exactly
 * once per process. Awaited from instrumentation before the server accepts
 * requests, so `db` is ready for any server component or action.
 */
export async function ensureReady(): Promise<void> {
  if (!g.__smartsmeReady) {
    g.__smartsmeReady = (async () => {
      if (process.env.NEXT_PHASE === "phase-production-build") return;
      // Only the connection is critical. Migrations + seed are best-effort so a
      // missing ./drizzle folder (e.g. not bundled in a serverless deploy) or a
      // seed hiccup can never crash boot and 500 every route.
      g.__smartsmeDb = await initDb();
      try {
        await runMigrations();
      } catch (err) {
        console.warn("[db] migrations skipped:", err instanceof Error ? err.message : err);
      }
      try {
        const { seedIfEmpty } = await import("./seed");
        await seedIfEmpty();
      } catch (err) {
        console.warn("[db] seed skipped:", err instanceof Error ? err.message : err);
      }
    })().catch((err) => {
      g.__smartsmeReady = undefined;
      throw err;
    });
  }
  return g.__smartsmeReady;
}

export async function ping(): Promise<boolean> {
  try {
    await db.execute(sql`select 1`);
    return true;
  } catch {
    return false;
  }
}
