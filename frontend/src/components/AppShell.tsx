import { Outlet } from "react-router";

import { Sidebar } from "./Sidebar";

/**
 * The authenticated app shell: a persistent sidebar plus the routed view in the
 * main region. Mounted under `RequireAuth`, so it renders only for a resolved
 * session; the matched child route renders through `<Outlet/>`.
 *
 * The shell owns the page gutter. It deliberately does not cap the content
 * width: single-column views apply `reading-width` themselves, and the editor
 * and detail views are full width by design.
 */
export function AppShell() {
  return (
    <div className="bg-background text-foreground flex min-h-svh">
      <Sidebar />
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
