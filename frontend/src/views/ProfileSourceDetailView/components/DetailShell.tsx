import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

interface DetailShellProps {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
}

/**
 * Chrome for the source detail screen: a back link to the profile hub, an
 * optional title and header action, and the body. Kept presentational so the
 * orchestrator composes create and edit layouts into it.
 */
export function DetailShell({ title, action, children }: DetailShellProps) {
  return (
    <section className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link
            to="/profile"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
          >
            <ArrowLeft className="size-4" /> Profile
          </Link>
          {title && <h1 className="text-xl font-semibold tracking-tight">{title}</h1>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
