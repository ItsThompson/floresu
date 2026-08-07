import { NavLink } from "react-router";

import { cn } from "@/lib/utils";

import { SETTINGS_SECTIONS } from "../constants";

/**
 * The Settings sub-navigation. Real links (`NavLink`) to the nested section
 * routes, so browser link semantics work and the active section is reflected in
 * the URL. Order and labels come from `SETTINGS_SECTIONS`.
 *
 * The active tab is a muted fill with ink text, not the accent fill and bloom bar
 * `frontend/src/components/Sidebar.tsx` gives its active item: the sidebar holds
 * the only bloom marker on screen, and a second one would read as two active
 * locations at once. Inactive tabs shift ink on hover rather than taking a fill,
 * so hover never impersonates the active tab.
 */
export function SettingsNav() {
  return (
    <nav
      aria-label="Settings sections"
      className="border-border flex flex-wrap gap-1 border-b pb-2"
    >
      {SETTINGS_SECTIONS.map((section) => (
        <NavLink
          key={section.path}
          to={section.path}
          className={({ isActive }) =>
            cn(
              "rounded-md px-3 py-1.5 text-sm font-medium",
              isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
            )
          }
        >
          {section.label}
        </NavLink>
      ))}
    </nav>
  );
}
