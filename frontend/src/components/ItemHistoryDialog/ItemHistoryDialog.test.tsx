import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { buildFeedEvent } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/renderWithProviders";

import { ItemHistoryDialog } from "./ItemHistoryDialog";

/** Serve the item-history endpoint with the given rows (caller passes newest-first). */
function serveItemHistory(rows: ReturnType<typeof buildFeedEvent>[]) {
  return http.get("*/feed/history/:entityType/:entityId", () => HttpResponse.json(rows));
}

function renderDialog() {
  renderWithProviders(
    <ItemHistoryDialog isOpen onClose={vi.fn()} entityType="worklog" entityId={100} />,
  );
}

describe("ItemHistoryDialog", () => {
  it("renders each row's actor, action, summary, and time, newest-first", async () => {
    server.use(
      serveItemHistory([
        buildFeedEvent({
          id: 2,
          actor_type: "agent",
          actor_label: "claude",
          action: "update",
          summary: "Refined the wording",
          created_at: "2026-07-21T09:00:00Z",
        }),
        buildFeedEvent({
          id: 1,
          actor_type: "human",
          actor_label: null,
          action: "create",
          created_at: "2026-07-20T12:00:00Z",
        }),
      ]),
    );

    renderDialog();

    const rows = await screen.findAllByRole("listitem");
    expect(rows).toHaveLength(2);
    // Newest-first: the agent update precedes the human create.
    expect(rows[0]).toHaveTextContent("claude");
    expect(rows[0]).toHaveTextContent("updated");
    expect(rows[0]).toHaveTextContent("Refined the wording");
    expect(rows[1]).toHaveTextContent("You");
    expect(rows[1]).toHaveTextContent("created");

    // Human vs agent is distinguished by shape (a bot glyph), not color alone.
    const glyphs = screen.getAllByTestId("agent-glyph");
    expect(glyphs).toHaveLength(1);
    expect(screen.getByRole("img", { name: "claude" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "You" })).toBeInTheDocument();
  });

  it("shows an empty state, not an error, when the item has no history", async () => {
    server.use(serveItemHistory([]));

    renderDialog();

    expect(await screen.findByText("No history yet for this item.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("shows an inline error with no rows when the fetch fails", async () => {
    server.use(
      http.get("*/feed/history/:entityType/:entityId", () => new HttpResponse(null, { status: 500 })),
    );

    renderDialog();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load history. Close and reopen to retry.",
    );
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });
});
