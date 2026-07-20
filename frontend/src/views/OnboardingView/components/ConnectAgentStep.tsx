import { useState } from "react";

import { Button } from "@/components/ui/button";

import type { ConnectAgentStepProps } from "../types";

/**
 * Shows the MCP URL for the user to add to their AI client. The URL is threaded
 * in as a prop (sourced once at the view root); this step reads no environment.
 * Copy is a best-effort convenience: if the Clipboard API is unavailable or
 * denied, the URL stays visible for manual selection.
 */
export function ConnectAgentStep({ mcpUrl, onContinue }: ConnectAgentStepProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(mcpUrl);
      setCopied(true);
    } catch {
      // Clipboard denied/unavailable: the URL remains visible to copy by hand.
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
          readOnly
          aria-label="MCP URL"
          value={mcpUrl}
          className="border-input bg-muted h-9 flex-1 rounded-md border px-3 font-mono text-sm outline-none"
        />
        <Button variant="outline" onClick={() => void handleCopy()}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <Button onClick={onContinue}>Continue</Button>
    </div>
  );
}
