import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { components } from "@/api";
import { mockAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

/**
 * Sociable tests for the Archive & Trash section: they drive the real route tree
 * and archive state machine against the MSW-backed lifecycle routes. Only the
 * network is mocked.
 */

type WorklogSummary = components["schemas"]["WorklogSummary"];
type SourceSummary = components["schemas"]["SourceSummary"];
type BulletpointRecord = components["schemas"]["BulletpointRecord"];

function archivedWorklog(overrides?: Partial<WorklogSummary>): WorklogSummary {
  return {
    id: 1,
    title: "Archived entry",
    entry_date: "2026-07-01",
    description: null,
    tags: [],
    source_ids: [],
    archived_at: "2026-07-02T00:00:00Z",
    ...overrides,
  };
}

function archivedSource(overrides?: Partial<SourceSummary>): SourceSummary {
  return {
    id: 10,
    kind: "role",
    display_label: "Archived source",
    date_start: null,
    date_end: null,
    summary: null,
    sort_order: 0,
    archived_at: "2026-07-03T00:00:00Z",
    ...overrides,
  };
}

function archivedBullet(overrides?: Partial<BulletpointRecord>): BulletpointRecord {
  return {
    id: 20,
    text: "Archived bullet",
    source_ids: [],
    worklog_ids: [],
    used_in_count: 0,
    revision: 1,
    archived_at: "2026-07-04T00:00:00Z",
    ...overrides,
  };
}

function authenticateOnResume() {
  server.use(http.post("*/auth/refresh", () => HttpResponse.json(mockAuthUser)));
}

interface ArchiveFixtures {
  worklog?: WorklogSummary[];
  sources?: SourceSummary[];
  bullets?: BulletpointRecord[];
}

function mockArchiveLists({ worklog = [], sources = [], bullets = [] }: ArchiveFixtures) {
  server.use(
    http.get("*/worklog", () => HttpResponse.json(worklog)),
    http.get("*/sources", () => HttpResponse.json(sources)),
    http.get("*/bullets", () => HttpResponse.json(bullets)),
  );
}

describe("ArchivePanel", () => {
  it("lists archived worklog entries, sources, and bullets, and hides active items", async () => {
    authenticateOnResume();
    mockArchiveLists({
      worklog: [
        archivedWorklog(),
        archivedWorklog({ id: 2, title: "Active entry", archived_at: null }),
      ],
      sources: [archivedSource()],
      bullets: [archivedBullet()],
    });

    renderApp(["/settings/archive"]);

    expect(await screen.findByText("Archived entry")).toBeInTheDocument();
    expect(screen.getByText("Archived source")).toBeInTheDocument();
    expect(screen.getByText("Archived bullet")).toBeInTheDocument();
    expect(screen.queryByText("Active entry")).not.toBeInTheDocument();
  });

  it("shows an empty state when nothing is archived", async () => {
    authenticateOnResume();
    mockArchiveLists({});

    renderApp(["/settings/archive"]);

    expect(await screen.findByText(/nothing is archived/i)).toBeInTheDocument();
  });

  it("restores an item and removes it from the archive list", async () => {
    authenticateOnResume();
    mockArchiveLists({ worklog: [archivedWorklog()] });
    let restoredId: string | null = null;
    server.use(
      http.post("*/worklog/:id/restore", ({ params }) => {
        restoredId = params.id as string;
        return HttpResponse.json({});
      }),
    );

    renderApp(["/settings/archive"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Restore/ }));

    await waitFor(() => expect(screen.queryByText("Archived entry")).not.toBeInTheDocument());
    expect(restoredId).toBe("1");
  });

  it("permanently deletes only after the acknowledgement is confirmed", async () => {
    authenticateOnResume();
    mockArchiveLists({ sources: [archivedSource()] });
    let deleteConfirm: string | null = null;
    server.use(
      http.delete("*/sources/:id", ({ request }) => {
        deleteConfirm = new URL(request.url).searchParams.get("confirm");
        return HttpResponse.json({ entity_type: "source", entity_id: 10, embedding_purged: true });
      }),
    );

    renderApp(["/settings/archive"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Delete/ }));
    const confirm = screen.getByRole("button", { name: /Delete permanently/ });
    // Gated: confirm stays disabled until the acknowledgement is checked.
    expect(confirm).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    await waitFor(() => expect(screen.queryByText("Archived source")).not.toBeInTheDocument());
    expect(deleteConfirm).toBe("true");
  });

  it("surfaces a load error when the archive lists fail", async () => {
    authenticateOnResume();
    server.use(
      http.get("*/worklog", () => HttpResponse.error()),
      http.get("*/sources", () => HttpResponse.json([])),
      http.get("*/bullets", () => HttpResponse.json([])),
    );

    renderApp(["/settings/archive"]);

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn.t load your archived items/i);
  });
});
