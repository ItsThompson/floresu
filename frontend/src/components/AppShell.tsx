import { Outlet } from "react-router";

import { Sidebar } from "./Sidebar";

/**
 * The authenticated app shell: a persistent sidebar plus the routed view in the
 * main region. Mounted under `RequireAuth`, so it renders only for a resolved
 * session; the matched child route renders through `<Outlet/>`.
 */
export function AppShell() {
  return (
    <div className="bg-background text-foreground flex min-h-svh">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
