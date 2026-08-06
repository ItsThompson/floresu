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
 * guards, and the session lifecycle against the MSW backend. The default entry is
 * the app's Home, the first in-app screen; `/` is the public page, which is
 * outside the guards and needs neither a session nor the app shell.
 */
export function renderApp(initialEntries: string[] = ["/home"]): RenderResult {
  const router = createMemoryRouter(appRoutes, { initialEntries });
  return render(
    <Providers>
      <RouterProvider router={router} />
    </Providers>,
  );
}

/**
 * Render a single component inside the providers and a memory router, for
 * isolated component tests. `initialEntries` positions the router, so a component
 * that reads the location (an active `NavLink`, say) can be asserted without the
 * full app tree; the component itself is the only route, so a redirect it renders
 * changes the location without needing a destination view.
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
