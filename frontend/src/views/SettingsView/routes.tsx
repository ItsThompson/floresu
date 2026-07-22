import { Navigate, type RouteObject } from "react-router";

import { SettingsView } from "./SettingsView";
import { AccountPanel } from "./components/AccountPanel";
import { ArchivePanel } from "./components/ArchivePanel";
import { ConnectedAgentsPanel } from "./components/ConnectedAgentsPanel";
import { DataPanel } from "./components/DataPanel";

/**
 * The `/settings` route subtree, owned by this view so the app router only
 * mounts it. The layout renders the sub-nav and an `<Outlet/>`; each section is a
 * nested child. The index redirects to Account, the first section.
 */
export const settingsRoute: RouteObject = {
  path: "settings",
  element: <SettingsView />,
  children: [
    { index: true, element: <Navigate to="account" replace /> },
    { path: "account", element: <AccountPanel /> },
    { path: "agents", element: <ConnectedAgentsPanel /> },
    { path: "archive", element: <ArchivePanel /> },
    { path: "data", element: <DataPanel /> },
  ],
};
