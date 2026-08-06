import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/App";
// Fixed order: fonts, then tokens, then the Tailwind bridge. The bridge reads
// token variables, so it must come last.
import "@/theme/fonts.css";
import "@/theme/tokens.css";
import "@/globals.css";

/**
 * Start the MSW worker before rendering when the mock harness is enabled
 * (`npm run dev:mock` sets `VITE_MOCK_API=true`). Unhandled requests bypass to
 * the network. In every other mode this is a no-op and the SPA talks to the real
 * backend (same-origin via the Vite dev proxy).
 */
async function enableMocking(): Promise<void> {
  if (import.meta.env.VITE_MOCK_API !== "true") return;
  const { worker } = await import("@/mocks/browser");
  await worker.start({ onUnhandledRequest: "bypass" });
}

function renderApp(): void {
  const rootElement = document.getElementById("root");
  if (!rootElement) {
    throw new Error("Root element #root not found");
  }
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

// Render regardless of mock-start outcome; a failed worker (dev-only) is logged
// rather than left as an unhandled rejection or a blank screen.
enableMocking()
  .catch((error: unknown) => {
    console.error("[MSW] Failed to start the mock worker", error);
  })
  .finally(renderApp);
