import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConnectAgentStep } from "./ConnectAgentStep";

const MCP_URL = "https://mcp.example.test/mcp";

const originalClipboard = navigator.clipboard;

afterEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: originalClipboard, configurable: true });
  vi.restoreAllMocks();
});

describe("ConnectAgentStep", () => {
  it("displays the MCP URL threaded in as a prop", () => {
    render(<ConnectAgentStep mcpUrl={MCP_URL} onContinue={vi.fn()} />);
    expect(screen.getByLabelText("MCP URL")).toHaveValue(MCP_URL);
  });

  it("copies the MCP URL to the clipboard and confirms", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    render(<ConnectAgentStep mcpUrl={MCP_URL} onContinue={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));

    expect(writeText).toHaveBeenCalledWith(MCP_URL);
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("shows a manual-copy hint when the clipboard is unavailable", async () => {
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });

    render(<ConnectAgentStep mcpUrl={MCP_URL} onContinue={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/copy it manually/i);
    // The button does not falsely claim success.
    expect(screen.queryByRole("button", { name: "Copied" })).not.toBeInTheDocument();
  });

  it("shows a manual-copy hint when the clipboard write is denied", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    render(<ConnectAgentStep mcpUrl={MCP_URL} onContinue={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/copy it manually/i);
    expect(screen.queryByRole("button", { name: "Copied" })).not.toBeInTheDocument();
  });

  it("advances when Continue is pressed", async () => {
    const onContinue = vi.fn();
    render(<ConnectAgentStep mcpUrl={MCP_URL} onContinue={onContinue} />);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
