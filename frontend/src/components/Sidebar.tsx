import { NavLink } from "react-router";

import { useAuth } from "@/auth";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/home", label: "Home", end: true },
  { to: "/worklog", label: "Worklog", end: false },
  { to: "/library", label: "Library", end: false },
  { to: "/resumes", label: "Resumes", end: false },
  { to: "/applications", label: "Job Applications", end: false },
  { to: "/profile", label: "Profile", end: false },
  { to: "/settings", label: "Settings", end: false },
] as const;

const NAV_ITEM_BASE = "relative block rounded-md px-3 py-2 text-sm font-medium";

/**
 * Left sidebar: brand, primary nav, and the signed-in identity with sign-out.
 * Nav items are real links (`NavLink`) so browser link semantics work; sign-out
 * is a genuine action (a revoking POST), so it is a button. After logout the
 * session flips to anonymous and `RequireAuth` redirects to sign-in.
 *
 * The chrome stays quiet so the user's own record carries the color: the active
 * nav item is the single loud moment here, and the serif wordmark is the brand
 * signature rather than one of the view-level display moments.
 */
export function Sidebar() {
  const { user, logout } = useAuth();

  return (
    <nav className="bg-card text-card-foreground border-border flex w-56 shrink-0 flex-col gap-6 border-r p-4">
      <span className="font-serif text-lg font-medium tracking-tight">floresu</span>

      <ul className="flex flex-1 flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  NAV_ITEM_BASE,
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-muted",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span
                      aria-hidden="true"
                      data-testid="nav-active-indicator"
                      className="bg-bloom absolute inset-y-1 left-0 w-[3px] rounded-full"
                    />
                  )}
                  {item.label}
                </>
              )}
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
