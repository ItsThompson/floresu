import { defineConfig, devices } from "@playwright/test";

import { backendEnv } from "./harness/env";
import { EXTERNAL_API_URL, FRONTEND_URL, PORTS } from "./harness/env";

/**
 * Full-stack E2E configuration.
 *
 * Infrastructure (Postgres, Redis, MinIO) is brought up by `tsx harness/infra.ts
 * up` before this config runs (see the `test` script), so the backend never
 * boots ahead of its database. Playwright owns the three app processes below and
 * tears the infrastructure down afterwards via `globalTeardown`.
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["blob"]] : [["list"]],
  globalTeardown: "./harness/globalTeardown.ts",

  use: {
    baseURL: FRONTEND_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  webServer: [
    {
      command: "node fakes/embeddings-server.mjs",
      url: `http://localhost:${PORTS.fakeEmbeddings}/`,
      env: { FAKE_EMBEDDINGS_PORT: String(PORTS.fakeEmbeddings) },
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      // serve-backend.sh runs both ASGI apps (:8000 external + :8001 internal).
      // `uv run` puts the backend venv (uvicorn) on PATH.
      command: "uv run bash ../scripts/serve-backend.sh",
      cwd: "../backend",
      url: `${EXTERNAL_API_URL}/readyz`,
      env: backendEnv,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      // Serve the production build via `vite preview`, not the dev server: the
      // dev server's React StrictMode double-invokes the session-resume effect,
      // and the rotating refresh token turns the second call into a 401. The
      // built bundle invokes effects once, matching production. `preview.proxy`
      // forwards the API prefixes to the backend (same-origin, cookies flow).
      command: `npm run build && npm run preview -- --port ${PORTS.frontend} --strictPort`,
      cwd: "../frontend",
      url: FRONTEND_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
});
