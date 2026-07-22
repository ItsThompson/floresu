import type { IncomingMessage } from "node:http";
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The external backend app. The dev server proxies the API paths to it so the
// SPA calls the backend same-origin (no CORS, and the session cookie flows).
// `/auth/` keeps the trailing slash so it proxies the auth endpoints without
// swallowing the `/authorize` SPA consent route; `/oauth` reaches the OAuth AS
// (the consent context/decision XHRs). The remaining prefixes are the domain
// routes the in-app views read and write.
//
// `/worklog` and `/resumes` are BOTH API prefixes AND SPA page routes, so a bare
// proxy would swallow their browser navigations. `bypassSpaNavigation` forwards
// only non-document requests (XHR/fetch, whose Accept is not `text/html`) and
// lets Vite serve the SPA for document navigations. This is dev-only; prod is
// host-split (the API lives on its own subdomain).
const BACKEND_ORIGIN = "http://localhost:8000";
const PROXIED_PATHS = [
  "/auth/",
  "/me",
  "/feed",
  "/oauth",
  "/account",
  "/worklog",
  "/sources",
  "/bullets",
  "/skills",
  "/identity-variants",
  "/resumes",
  "/job-applications",
  "/search",
];

// A browser navigating to an SPA route sends a `text/html` document request;
// return the URL to bypass the proxy (Vite serves the SPA). API clients send
// XHR/fetch (Accept `*/*`, `application/json`, `text/event-stream`), which
// returns undefined and is proxied to the backend.
const bypassSpaNavigation = (req: IncomingMessage): string | undefined =>
  req.headers.accept?.includes("text/html") ? req.url : undefined;

// Proxy every API prefix to the backend. Shared by the dev server and `vite
// preview` (the E2E suite serves the production build via preview) so both reach
// the backend same-origin with the session cookie flowing.
const apiProxy = Object.fromEntries(
  PROXIED_PATHS.map((path) => [
    path,
    { target: BACKEND_ORIGIN, changeOrigin: true, bypass: bypassSpaNavigation },
  ]),
);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text-summary", "text"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.test.{ts,tsx}",
        "src/**/*.d.ts",
        "src/test/**",
        "src/main.tsx",
        "src/**/index.ts",
        "src/components/ui/**", // vendored shadcn primitives
        "src/mocks/**", // dev-only MSW harness
      ],
      // Frontend coverage floor, enforced locally (`npm run test:coverage`) and
      // in CI. vitest exits non-zero below the floor, failing the build.
      thresholds: {
        lines: 70,
      },
    },
  },
});
