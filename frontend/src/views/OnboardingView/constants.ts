/**
 * The ordered onboarding steps. This list is the single source of step order and
 * count: the progress indicator, the first/last-step derivations, and the step
 * routing all read from it, so adding or reordering a step is a one-line change.
 */
export const STEPS = ["welcome", "choose_path", "connect_agent", "how_it_works"] as const;

/**
 * MCP endpoint shown on the connect-agent step when `VITE_MCP_URL` is unset (dev
 * and tests). Sourced once at the view root and threaded to the step as a prop;
 * steps never read the environment themselves.
 */
export const DEFAULT_MCP_URL = "https://mcp.floresu.app/mcp";
