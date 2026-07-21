import { Download, Trash2 } from "lucide-react";
import { useState } from "react";

import { useApiBaseUrl } from "@/api";
import { useAuth } from "@/auth";
import { Button } from "@/components/ui/button";

import { useAccountData } from "../hooks/useAccountData";
import { ConfirmDestructiveDialog } from "./ConfirmDestructiveDialog";

/**
 * The Data section: export the account's records, and delete the account.
 *
 * Export is a plain credentialed download link to the web-only export route, so
 * the browser handles the attachment natively. Account deletion is irreversible:
 * it is confirm-gated and only enabled after the user types their email, and it
 * revokes every connected agent server-side. On success the session is cleared,
 * returning the now-anonymous user to sign-in.
 */
export function DataPanel() {
  const baseUrl = useApiBaseUrl();
  const { user } = useAuth();
  const { state, actions } = useAccountData();
  const [isConfirming, setIsConfirming] = useState(false);

  const exportHref = `${baseUrl}/account/export`;

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Export your data</h2>
        <p className="text-muted-foreground text-sm">
          Download an archive of your records: profile, worklog, library, and resumes.
        </p>
        <div>
          <Button asChild variant="outline">
            <a href={exportHref} download>
              <Download aria-hidden />
              Export my data
            </a>
          </Button>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Delete account</h2>
        <p className="text-muted-foreground text-sm">
          Permanently delete your account and all records, and revoke every connected agent. This is
          irreversible.
        </p>
        <div>
          <Button variant="destructive" onClick={() => setIsConfirming(true)}>
            <Trash2 aria-hidden />
            Delete my account
          </Button>
        </div>
        {state.status === "error" && (
          <p role="alert" className="text-destructive text-sm">
            {state.error}
          </p>
        )}
      </section>

      {isConfirming && (
        <ConfirmDestructiveDialog
          title="Delete your account?"
          description="This permanently removes your account and all records and revokes every connected agent. It cannot be undone."
          confirmLabel="Delete account"
          typePhrase={user?.email ?? ""}
          isBusy={state.status === "deleting"}
          onConfirm={actions.deleteAccount}
          onCancel={() => setIsConfirming(false)}
        />
      )}
    </div>
  );
}
