import { Navigate, Outlet, useLocation } from "react-router";

import { useAuth } from "@/auth";
import { RouteLoading } from "./RouteLoading";

/**
 * Guards the authenticated in-app routes. Rendered as a layout (parent) route,
 * so it either renders `<Outlet/>` (the matched child view) or redirects.
 *
 * - `loading` → neutral full-screen loader (never misroute or flash a guarded
 *   view while the session resolves on mount)
 * - `anonymous` → redirect to `/signin`, carrying the attempted location as
 *   `from` so sign-in returns the user here (e.g. a deep-linked consent URL);
 *   `replace` keeps the guard out of history
 * - `authenticated` → render the route
 */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <RouteLoading />;
  if (status === "anonymous") {
    const from = `${location.pathname}${location.search}`;
    return <Navigate to="/signin" state={{ from }} replace />;
  }
  return <Outlet />;
}
