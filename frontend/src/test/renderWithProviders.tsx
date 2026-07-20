import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";

import { ApiClientProvider } from "@/api";
import { AuthProvider } from "@/auth";
import { appRoutes } from "@/routes";

// Absolute base so undici's Request (used by the MSW interceptor) can parse the
// URL under jsdom; the MSW handlers match any host, so both clients hit the mock.
const TEST_BASE_URL = "http://localhost";

function Providers({ children }: { children: ReactNode }) {
  return (
    <ApiClientProvider baseUrl={TEST_BASE_URL}>
      <AuthProvider>{children}</AuthProvider>
    </ApiClientProvider>
  );
}

/**
 * Render the whole application route tree in memory at `initialEntries`, wrapped
 * in the API + auth providers. The most sociable harness: exercises real routing,
 * guards, and the session lifecycle against the MSW backend.
 */
export function renderApp(initialEntries: string[] = ["/"]): RenderResult {
  const router = createMemoryRouter(appRoutes, { initialEntries });
  return render(
    <Providers>
      <RouterProvider router={router} />
    </Providers>,
  );
}

/**
 * Render a single component inside the providers and a memory router, for
 * isolated component tests. A `/` route stub lets components that redirect Home
 * (`<Navigate to="/"/>`) be asserted without the full app tree.
 */
export function renderWithProviders(
  ui: ReactElement,
  initialEntries: string[] = ["/test"],
): RenderResult {
  return render(
    <Providers>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </Providers>,
  );
}
