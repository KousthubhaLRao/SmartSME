import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root (a stray lockfile in the home dir otherwise confuses
  // Next's root inference).
  outputFileTracingRoot: process.cwd(),
  // Ship the generated SQL migrations into the serverless bundle so the boot-time
  // migrator can find them on Vercel (it reads them from disk at runtime).
  outputFileTracingIncludes: {
    "/**": ["./drizzle/**/*"],
  },
  // Keep native/server-only packages out of the bundler so PGlite, postgres-js,
  // Drizzle (its migrator imports node:crypto), and the Anthropic SDK load
  // correctly at runtime on the server.
  serverExternalPackages: ["@electric-sql/pglite", "postgres", "drizzle-orm", "@anthropic-ai/sdk"],
  experimental: {
    // Allow the event worker started from instrumentation to keep running.
    serverActions: {
      bodySizeLimit: "8mb", // OCR image uploads
    },
  },
};

export default nextConfig;
