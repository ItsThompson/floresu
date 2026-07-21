import { NavLink } from "react-router";

import { useAuth } from "@/auth";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { to: "/", label: "Home", end: true },
  { to: "/library", label: "Library", end: false },
] as const;

/**
 * Left sidebar: brand, primary nav, and the signed-in identity with sign-out.
 * Nav items are real links (`NavLink`) so browser link semantics work; sign-out
 * is a genuine action (a revoking POST), so it is a button. After logout the
 * session flips to anonymous and `RequireAuth` redirects to sign-in.
 */
export function Sidebar() {
  const { user, logout } = useAuth();

  return (
    <nav className="bg-sidebar text-sidebar-foreground flex w-56 shrink-0 flex-col gap-6 border-r p-4">
      <span className="text-lg font-semibold tracking-tight">Floresu</span>

      <ul className="flex flex-1 flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm font-medium ${
                  isActive ? "bg-sidebar-accent text-sidebar-accent-foreground" : "hover:bg-sidebar-accent/50"
                }`
              }
            >
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>

      <div className="flex flex-col gap-2">
        {user && <span className="text-muted-foreground truncate text-xs">{user.email}</span>}
        <Button variant="outline" size="sm" onClick={() => void logout()}>
          Sign out
        </Button>
      </div>
    </nav>
  );
}
