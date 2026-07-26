import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { buildFeedEvent } from "@/mocks/data";

import { FeedRow } from "./FeedRow";

function renderRow(event = buildFeedEvent(), animate = false) {
  return render(
    <MemoryRouter>
      <ul>
        <FeedRow event={event} animate={animate} />
      </ul>
    </MemoryRouter>,
  );
}

describe("FeedRow", () => {
  it("shows the actor, the action, the object link, and the timestamp", () => {
    const { container } = renderRow(
      buildFeedEvent({
        id: 4,
        action: "create",
        entity_type: "worklog",
        entity_id: 12,
        created_at: "2026-07-20T12:00:00Z",
      }),
    );

    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("created")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "worklog #12" });
    expect(link).toHaveAttribute("href", "/worklog");
    // The timestamp is rendered as locale text; the machine-readable ISO lives on
    // the <time> element's dateTime attribute.
    expect(container.querySelector("time")).toHaveAttribute("dateTime", "2026-07-20T12:00:00Z");
  });

  it("names the agent and links to the affected object", () => {
    renderRow(
      buildFeedEvent({
        actor_type: "agent",
        actor_label: "claude",
        action: "update",
        entity_type: "bullet",
        entity_id: 7,
      }),
    );

    expect(screen.getByText("claude")).toBeInTheDocument();
    expect(screen.getByText("updated")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "bullet #7" })).toHaveAttribute(
      "href",
      "/library?bullet=7",
    );
  });

  it("uses the summary as the object label when present", () => {
    renderRow(buildFeedEvent({ summary: "Shipped the search module", entity_type: "worklog" }));
    expect(
      screen.getByRole("link", { name: "Shipped the search module" }),
    ).toBeInTheDocument();
  });

  it("applies the entrance animation only when motion is allowed", () => {
    const { container, rerender } = renderRow(buildFeedEvent(), true);
    expect(container.querySelector("li")?.className).toContain("animate-in");

    rerender(
      <MemoryRouter>
        <ul>
          <FeedRow event={buildFeedEvent()} animate={false} />
        </ul>
      </MemoryRouter>,
    );
    expect(container.querySelector("li")?.className).not.toContain("animate-in");
  });
});
