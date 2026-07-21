/**
 * The MCP endpoint a user adds to their AI client. It is a domain truth shared by
 * every surface that shows it (the onboarding connect step and the Settings
 * connected-agents panel), so it lives here rather than inside any one view.
 *
 * The URL is fixed for a deployment: `VITE_MCP_URL` sets it in production and the
 * default covers dev and tests. Resolve it once at a view root and thread the
 * string down as a prop; presentational components read no environment.
 */

/** MCP endpoint shown when `VITE_MCP_URL` is unset (dev and tests). */
export const DEFAULT_MCP_URL = "https://mcp.floresu.app/mcp";

/** The configured MCP URL, falling back to the default when unset. */
export function resolveMcpUrl(): string {
  return import.meta.env.VITE_MCP_URL ?? DEFAULT_MCP_URL;
}
