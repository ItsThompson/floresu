import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";

import type { ConnectAgentStepProps } from "../types";

/** Copy outcome. `unavailable` covers a missing or denied Clipboard API. */
type CopyStatus = "idle" | "copied" | "unavailable";

/**
 * Shows the MCP URL for the user to add to their AI client. The URL is threaded
 * in as a prop (sourced once at the view root); this step reads no environment.
 * Copy is a best-effort convenience: if the Clipboard API is missing or denied,
 * the URL field is selected and a manual-copy hint is shown, so the user is never
 * left without feedback.
 */
export function ConnectAgentStep({ mcpUrl, onContinue }: ConnectAgentStepProps) {
  const [copyStatus, setCopyStatus] = useState<CopyStatus>("idle");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleCopy = async () => {
    if (!navigator.clipboard) {
      setCopyStatus("unavailable");
      inputRef.current?.select();
      return;
    }
    try {
      await navigator.clipboard.writeText(mcpUrl);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("unavailable");
      inputRef.current?.select();
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold tracking-tight">Connect your agent</h1>
      <p className="text-muted-foreground">
        Add this MCP URL to your AI client. When your agent connects, you approve its access on the
        consent screen before it can read or write anything.
      </p>
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          readOnly
          aria-label="MCP URL"
          value={mcpUrl}
          className="border-input bg-muted h-9 flex-1 rounded-md border px-3 font-mono text-sm outline-none"
        />
        <Button variant="outline" onClick={() => void handleCopy()}>
          {copyStatus === "copied" ? "Copied" : "Copy"}
        </Button>
      </div>
      {copyStatus === "unavailable" && (
        <p role="status" className="text-muted-foreground text-sm">
          Couldn&apos;t copy automatically. The URL above is selected: copy it manually.
        </p>
      )}
      <Button onClick={onContinue}>Continue</Button>
    </div>
  );
}
