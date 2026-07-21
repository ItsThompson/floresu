import { useAuth } from "@/auth";

import { formatDate } from "../constants";

/**
 * The Account section: the signed-in identity and when the account was created.
 * Read-only; the destructive account operations live in the Data section.
 */
export function AccountPanel() {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold tracking-tight">Account</h2>
      <dl className="flex flex-col gap-3 text-sm">
        <div className="flex flex-col gap-0.5">
          <dt className="text-muted-foreground">Email</dt>
          <dd className="font-medium">{user.email}</dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="text-muted-foreground">Member since</dt>
          <dd className="font-medium">{formatDate(user.created_at)}</dd>
        </div>
      </dl>
    </div>
  );
}
