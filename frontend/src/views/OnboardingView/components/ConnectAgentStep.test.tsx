import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConnectAgentStep } from "./ConnectAgentStep";

const MCP_URL = "https://mcp.example.test/mcp";

describe("ConnectAgentStep", () => {
  it("displays the MCP URL threaded in as a prop", () => {
    render(<ConnectAgentStep mcpUrl={MCP_URL} onContinue={vi.fn()} />);
    expect(screen.getByLabelText("MCP URL")).toHaveValue(MCP_URL);
  });

  it("advances when Continue is pressed", async () => {
    const onContinue = vi.fn();
    render(<ConnectAgentStep mcpUrl={MCP_URL} onContinue={onContinue} />);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
