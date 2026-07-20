import type { RouteObject } from "react-router";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/components/RequireAuth";
import { AuthView } from "@/views/AuthView";
import { HomeView } from "@/views/HomeView";

/**
 * The application route tree. Kept separate from `App` (the provider
 * composition) so a routing-config test can assert the structural invariants:
 * that `/signin` and `/signup` live OUTSIDE `RequireAuth` (chrome-free, always
 * reachable) and the in-app routes live inside it (guarded by the session),
 * without rendering the views.
 */
export const appRoutes: RouteObject[] = [
  // Chrome-free auth screens, always reachable (no session required).
  { path: "/signin", element: <AuthView mode="login" /> },
  { path: "/signup", element: <AuthView mode="register" /> },

  // Guarded: an anonymous user is redirected to /signin before the shell mounts.
  {
    element: <RequireAuth />,
    children: [
      {
        path: "/",
        element: <AppShell />,
        children: [{ index: true, element: <HomeView /> }],
      },
    ],
  },
];
