/**
 * Test environment guard + setup.
 *
 * This module MUST be evaluated before "@/db" in every test process. The harness
 * modules (./db, ./factories) import it on their first line, so simply importing
 * one of them at the top of a test file is enough.
 *
 * What it does:
 *  1. Refuses to run against a real PostgreSQL server. The suite truncates tables
 *     between tests, so pointing it at a real database could delete real data.
 *  2. Forces an ephemeral, in-memory PGlite database (src/db/index.ts passes
 *     PGLITE_DIR straight to PGlite). Nothing is ever written to your ./.pgdata,
 *     and every row a test creates vanishes when the process exits.
 *  3. Sets a few deterministic env vars so unrelated subsystems stay quiet.
 */

// (1) Never let the destructive test suite touch a real database.
if (process.env.DATABASE_URL && process.env.TEST_ALLOW_REAL_DB !== "1") {
  throw new Error(
    "[test] DATABASE_URL is set. The test suite truncates tables between tests and must " +
      "never run against a real database. Unset DATABASE_URL to use the in-memory test " +
      "database, or set TEST_ALLOW_REAL_DB=1 to explicitly override (strongly discouraged).",
  );
}

// (2) Force an isolated in-memory database for this test process.
process.env.PGLITE_DIR = "memory://";

// (3) Keep the background worker and auth deterministic during tests.
process.env.SMARTSME_NO_WORKER = "1";
if (!process.env.AUTH_SECRET || process.env.AUTH_SECRET.length < 32) {
  process.env.AUTH_SECRET = "smartsme-test-secret-0123456789-abcdefghijklmnop";
}
