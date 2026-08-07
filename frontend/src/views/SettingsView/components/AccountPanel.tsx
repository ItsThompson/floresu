import { useAuth } from "@/auth";

import { formatDate } from "../constants";
import { SettingsPanel } from "./SettingsPanel";

/**
 * The Account section: the signed-in identity and when the account was created.
 * Read-only; the destructive account operations live in the Data section.
 */
export function AccountPanel() {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <SettingsPanel title="Account">
      <dl className="flex flex-col gap-3">
        <div className="flex flex-col gap-0.5">
          <dt className="caption text-muted-foreground">Email</dt>
          <dd className="text-foreground text-sm font-medium">{user.email}</dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="caption text-muted-foreground">Member since</dt>
          <dd className="mono-meta text-foreground">{formatDate(user.created_at)}</dd>
        </div>
      </dl>
    </SettingsPanel>
  );
}
