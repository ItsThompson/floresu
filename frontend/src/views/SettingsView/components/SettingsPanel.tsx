import type { ReactNode } from "react";

interface SettingsPanelProps {
  /** The section heading, rendered as the panel's `h2`. */
  title: string;
  /** Optional lead paragraph, rendered above the panel body. */
  description?: string;
  children: ReactNode;
}

/**
 * The card frame every Settings section renders inside: a titled `bg-card` panel
 * with a 1px border, mirroring `frontend/src/views/ProfileHubView/components/SectionCardShell.tsx`.
 *
 * Settings is a trust screen, so the frame itself carries no accent and no
 * elevation; what the panel holds (an agent's access, an irreversible delete) is
 * what the eye should reach, not the container.
 */
export function SettingsPanel({ title, description, children }: SettingsPanelProps) {
  return (
    <section className="border-border bg-card text-card-foreground flex flex-col gap-3 rounded-lg border p-5">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      {description && <p className="text-muted-foreground text-sm">{description}</p>}
      {children}
    </section>
  );
}
