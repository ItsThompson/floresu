import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_MCP_URL, resolveMcpUrl } from "./mcpUrl";

describe("resolveMcpUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("falls back to the default when VITE_MCP_URL is unset", () => {
    vi.stubEnv("VITE_MCP_URL", undefined);
    expect(resolveMcpUrl()).toBe(DEFAULT_MCP_URL);
  });

  it("returns the configured VITE_MCP_URL when set", () => {
    vi.stubEnv("VITE_MCP_URL", "https://mcp.example.test/mcp");
    expect(resolveMcpUrl()).toBe("https://mcp.example.test/mcp");
  });
});
