import { Button } from "@/components/ui/button";
import { McpUrlField } from "@/components/McpUrlField";

import type { ConnectAgentStepProps } from "../types";

/**
 * Shows the MCP URL for the user to add to their AI client. The URL is threaded
 * in as a prop (sourced once at the view root); this step reads no environment.
 * The read-only field and its copy control are the shared `McpUrlField`, so the
 * onboarding and Settings surfaces show the URL identically.
 */
export function ConnectAgentStep({ mcpUrl, onContinue }: ConnectAgentStepProps) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold tracking-tight">Connect your agent</h1>
      <p className="text-muted-foreground">
        Add this MCP URL to your AI client. When your agent connects, you approve its access on the
        consent screen before it can read or write anything.
      </p>
      <McpUrlField url={mcpUrl} />
      <Button onClick={onContinue}>Continue</Button>
    </div>
  );
}
