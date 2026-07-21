import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { McpUrlField } from "./McpUrlField";

const MCP_URL = "https://mcp.example.test/mcp";

const originalClipboard = navigator.clipboard;

afterEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: originalClipboard, configurable: true });
  vi.restoreAllMocks();
});

describe("McpUrlField", () => {
  it("shows the URL in a read-only field", () => {
    render(<McpUrlField url={MCP_URL} />);
    const field = screen.getByLabelText("MCP URL");
    expect(field).toHaveValue(MCP_URL);
    expect(field).toHaveAttribute("readonly");
  });

  it("copies the URL to the clipboard and confirms", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    render(<McpUrlField url={MCP_URL} />);
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));

    expect(writeText).toHaveBeenCalledWith(MCP_URL);
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("shows a manual-copy hint when the clipboard is unavailable", async () => {
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });

    render(<McpUrlField url={MCP_URL} />);
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/copy it manually/i);
    expect(screen.queryByRole("button", { name: "Copied" })).not.toBeInTheDocument();
  });

  it("shows a manual-copy hint when the clipboard write is denied", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    render(<McpUrlField url={MCP_URL} />);
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/copy it manually/i);
    expect(screen.queryByRole("button", { name: "Copied" })).not.toBeInTheDocument();
  });
});
