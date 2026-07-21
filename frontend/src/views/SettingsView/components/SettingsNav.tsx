import { NavLink } from "react-router";

import { SETTINGS_SECTIONS } from "../constants";

/**
 * The Settings sub-navigation. Real links (`NavLink`) to the nested section
 * routes, so browser link semantics work and the active section is reflected in
 * the URL. Order and labels come from `SETTINGS_SECTIONS`.
 */
export function SettingsNav() {
  return (
    <nav aria-label="Settings sections" className="flex flex-wrap gap-1 border-b pb-2">
      {SETTINGS_SECTIONS.map((section) => (
        <NavLink
          key={section.path}
          to={section.path}
          className={({ isActive }) =>
            `rounded-md px-3 py-1.5 text-sm font-medium ${
              isActive
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/50"
            }`
          }
        >
          {section.label}
        </NavLink>
      ))}
    </nav>
  );
}
