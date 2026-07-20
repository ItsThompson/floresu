import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The external backend app. The dev server proxies the API paths to it so the
// SPA calls the backend same-origin (no CORS, and the session cookie flows).
const BACKEND_ORIGIN = "http://localhost:8000";
const PROXIED_PATHS = ["/auth", "/me", "/feed"];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: Object.fromEntries(
      PROXIED_PATHS.map((path) => [path, { target: BACKEND_ORIGIN, changeOrigin: true }]),
    ),
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
