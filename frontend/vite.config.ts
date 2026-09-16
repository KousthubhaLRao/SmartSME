// From vitest/config, not vite: it is the same function with the `test` key
// typed. Importing it from "vite" makes the block below a type error.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  // Plain Node, no DOM: these tests cover the request layer rather than
  // components, and Node's own fetch/FormData/File are the ones the browser
  // uses. The only browser global involved is localStorage, which the setup
  // file stubs in three lines - cheaper than depending on a DOM implementation.
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    setupFiles: ["src/test-setup.ts"],
  },
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    // The API runs on :8000. Proxying keeps the session cookie first-party in
    // development, so no CORS or SameSite juggling is needed.
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
});
