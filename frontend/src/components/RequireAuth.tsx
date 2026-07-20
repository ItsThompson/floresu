import { Navigate, Outlet } from "react-router";

import { useAuth } from "@/auth";
import { RouteLoading } from "./RouteLoading";

/**
 * Guards the authenticated in-app routes. Rendered as a layout (parent) route,
 * so it either renders `<Outlet/>` (the matched child view) or redirects.
 *
 * - `loading` → neutral full-screen loader (never misroute or flash a guarded
 *   view while the session resolves on mount)
 * - `anonymous` → redirect to `/signin` (`replace` keeps it out of history)
 * - `authenticated` → render the route
 */
export function RequireAuth() {
  const { status } = useAuth();

  if (status === "loading") return <RouteLoading />;
  if (status === "anonymous") return <Navigate to="/signin" replace />;
  return <Outlet />;
}
