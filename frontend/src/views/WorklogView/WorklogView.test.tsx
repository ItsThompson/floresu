import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { SWRConfig } from "swr";
import { describe, expect, it } from "vitest";
import { buildBullet, buildEntry, buildSearchResult, buildSource, buildTag } from "@/mocks/worklogFixtures";
import { renderWithProviders } from "@/test/renderWithProviders";

import { installWorklogApi } from "./test-support/api";
import {
  ARCHIVE_ERROR_MESSAGE,
  DATE_REQUIRED_MESSAGE,
  SAVE_ERROR_MESSAGE,
  TIMELINE_ERROR_MESSAGE,
  TITLE_REQUIRED_MESSAGE,
} from "./constants";
import { WorklogView } from "./WorklogView";

// Fresh swr cache per render so one test's fetched data never leaks into the next.
function renderWorklog(ui: ReactElement = <WorklogView />) {
  return renderWithProviders(
    <SWRConfig value={{ provider: () => new Map() }}>{ui}</SWRConfig>,
    ["/worklog"],
  );
}

const ACME = buildSource({ id: 10, display_label: "Acme — Senior Engineer" });
const BETA = buildSource({ id: 11, display_label: "Beta — Engineer" });

describe("WorklogView", () => {
  it("groups entries by month, newest first, with date, title, source links, and tags", async () => {
    installWorklogApi({
      entries: [
        buildEntry({ id: 1, title: "Shipped payments", entry_date: "2026-07-18", tags: ["backend"], source_ids: [10] }),
        buildEntry({ id: 2, title: "Fixed cache bug", entry_date: "2026-07-04", tags: ["backend"], source_ids: [10] }),
        buildEntry({ id: 3, title: "Led API redesign", entry_date: "2026-06-20", tags: ["leadership"], source_ids: [10] }),
      ],
      sources: [ACME],
    });

    renderWorklog();

    expect(await screen.findByText("Shipped payments")).toBeInTheDocument();

    const monthHeadings = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(monthHeadings).toEqual(["July 2026", "June 2026"]);

    // Row detail: source link and tag pill are present on the entry.
    expect(screen.getAllByRole("link", { name: "@Acme — Senior Engineer" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("#backend").length).toBe(2);
    expect(screen.getByText("Jul 18")).toBeInTheDocument();
  });

  it("narrows the timeline by source, tag, and date filters combined", async () => {
    installWorklogApi({
      entries: [
        buildEntry({ id: 1, title: "Shipped payments", entry_date: "2026-07-18", tags: ["backend"], source_ids: [10] }),
        buildEntry({ id: 2, title: "Led team", entry_date: "2026-06-10", tags: ["leadership"], source_ids: [11] }),
        buildEntry({ id: 3, title: "Fixed cache", entry_date: "2026-05-02", tags: ["backend"], source_ids: [11] }),
      ],
      sources: [ACME, BETA],
      tags: [buildTag({ id: 1, label: "backend" }), buildTag({ id: 2, label: "leadership" })],
    });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Shipped payments");

    // Source filter alone: only Beta-attached entries remain.
    await user.selectOptions(screen.getByLabelText("Source"), "11");
    expect(screen.queryByText("Shipped payments")).not.toBeInTheDocument();
    expect(screen.getByText("Led team")).toBeInTheDocument();
    expect(screen.getByText("Fixed cache")).toBeInTheDocument();

    // Add a tag filter: backend + Beta narrows to the single entry.
    await user.selectOptions(screen.getByLabelText("Tag"), "backend");
    expect(screen.queryByText("Led team")).not.toBeInTheDocument();
    expect(screen.getByText("Fixed cache")).toBeInTheDocument();

    // Add a date lower bound that excludes the remaining May entry.
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-06-01" } });
    expect(screen.queryByText("Fixed cache")).not.toBeInTheDocument();
    expect(screen.getByText("No entries match your filters.")).toBeInTheDocument();
  });

  it("runs hybrid search and shows the fused ranked mix", async () => {
    const calls = installWorklogApi({
      entries: [buildEntry({ id: 1, title: "Shipped payments" })],
      sources: [ACME],
      search: buildSearchResult({
        ranked: [
          { type: "worklog", id: 1, score: 0.9 },
          { type: "bullet", id: 100, score: 0.5 },
          { type: "source", id: 10, score: 0.3 },
        ],
        graph: {
          worklog: [{ id: 1, title: "Shipped payments", date: "2026-07-18", score: 0.9, source_ids: [10] }],
          bullets: [{ id: 100, text: "Cut checkout latency 40%", score: 0.5, worklog_ids: [1], source_ids: [10] }],
          sources: [{ id: 10, kind: "role", label: "Acme — Senior Engineer", match_score: 0.3, score: 0.3 }],
        },
      }),
    });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Shipped payments");

    await user.type(screen.getByLabelText("Search worklog and bullets"), "payments");
    await user.click(screen.getByRole("button", { name: "Search" }));

    const results = await screen.findByRole("list", { name: "Search results" });
    const items = within(results).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Shipped payments");
    expect(items[1]).toHaveTextContent("Cut checkout latency 40%");
    expect(items[2]).toHaveTextContent("Acme — Senior Engineer");
    // The bullet result links into the Library, where the bullet lives.
    expect(within(results).getByRole("link", { name: "Cut checkout latency 40%" })).toHaveAttribute(
      "href",
      "/library?bullet=100",
    );
    expect(calls.searched).toEqual(["payments"]);
  });

  it("returns nothing for an empty query rather than dumping the corpus", async () => {
    const calls = installWorklogApi({ entries: [buildEntry({ id: 1, title: "Shipped payments" })], sources: [ACME] });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Shipped payments");

    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(calls.searched).toEqual([]);
    expect(screen.queryByRole("list", { name: "Search results" })).not.toBeInTheDocument();
  });

  it("shows 'No matches.' when a non-empty search returns zero results", async () => {
    const calls = installWorklogApi({
      entries: [buildEntry({ id: 1, title: "Shipped payments" })],
      sources: [ACME],
      search: buildSearchResult(),
    });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Shipped payments");

    await user.type(screen.getByLabelText("Search worklog and bullets"), "nothing matches this");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("No matches.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Search results" })).not.toBeInTheDocument();
    expect(calls.searched).toEqual(["nothing matches this"]);
  });

  it("adds an entry from just a title and a date; description, tags, and sources are optional", async () => {
    const calls = installWorklogApi({ entries: [], sources: [ACME] });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Worklog" });

    await user.click(screen.getByRole("button", { name: "+ Add entry" }));
    await user.type(screen.getByLabelText("Title"), "Wrote the design doc");
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-01" } });
    await user.click(screen.getByRole("button", { name: "Save entry" }));

    await waitFor(() => expect(calls.created).toHaveLength(1));
    expect(calls.created[0]).toEqual({
      title: "Wrote the design doc",
      entry_date: "2026-08-01",
      description: null,
      tags: [],
      source_ids: [],
    });
    expect(await screen.findByText("Wrote the design doc")).toBeInTheDocument();
  });

  it("attaches tags and multiple sources when provided", async () => {
    const calls = installWorklogApi({ entries: [], sources: [ACME, BETA] });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Worklog" });

    await user.click(screen.getByRole("button", { name: "+ Add entry" }));
    await user.type(screen.getByLabelText("Title"), "Cross-team launch");
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-02" } });

    const tagInput = screen.getByLabelText("Add a tag");
    await user.type(tagInput, "launch{Enter}");
    await user.type(tagInput, "backend{Enter}");

    await user.click(screen.getByLabelText("Acme — Senior Engineer"));
    await user.click(screen.getByLabelText("Beta — Engineer"));
    await user.click(screen.getByRole("button", { name: "Save entry" }));

    await waitFor(() => expect(calls.created).toHaveLength(1));
    expect(calls.created[0].tags).toEqual(["launch", "backend"]);
    expect(calls.created[0].source_ids).toEqual([10, 11]);
  });

  it("requires a title and a date before saving", async () => {
    const calls = installWorklogApi({ entries: [], sources: [ACME] });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Worklog" });

    await user.click(screen.getByRole("button", { name: "+ Add entry" }));
    await user.click(screen.getByRole("button", { name: "Save entry" }));

    expect(screen.getByText(TITLE_REQUIRED_MESSAGE)).toBeInTheDocument();
    expect(screen.getByText(DATE_REQUIRED_MESSAGE)).toBeInTheDocument();
    expect(calls.created).toHaveLength(0);
  });

  it("shows an inline error and preserves input when a save fails", async () => {
    installWorklogApi({ entries: [], sources: [ACME], failWrite: true });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Worklog" });

    await user.click(screen.getByRole("button", { name: "+ Add entry" }));
    await user.type(screen.getByLabelText("Title"), "Draft that fails");
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-01" } });
    await user.click(screen.getByRole("button", { name: "Save entry" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(SAVE_ERROR_MESSAGE);
    // Input is preserved for retry.
    expect(screen.getByLabelText("Title")).toHaveValue("Draft that fails");
  });

  it("edits an entry and reflects the change in the timeline", async () => {
    const calls = installWorklogApi({
      entries: [buildEntry({ id: 1, title: "Old title", entry_date: "2026-07-18", tags: [], source_ids: [] })],
      sources: [ACME],
    });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Old title");

    await user.click(screen.getByRole("button", { name: "Actions for Old title" }));
    await user.click(screen.getByRole("button", { name: "Edit" }));

    const titleInput = screen.getByLabelText("Title");
    await user.clear(titleInput);
    await user.type(titleInput, "New title");
    await user.click(screen.getByRole("button", { name: "Save entry" }));

    await waitFor(() => expect(calls.updated).toHaveLength(1));
    expect(calls.updated[0].id).toBe(1);
    expect(calls.updated[0].body.title).toBe("New title");
    expect(await screen.findByText("New title")).toBeInTheDocument();
    expect(screen.queryByText("Old title")).not.toBeInTheDocument();
  });

  it("archives an entry and removes it from the timeline", async () => {
    const calls = installWorklogApi({
      entries: [buildEntry({ id: 1, title: "Shipped payments" })],
      sources: [ACME],
    });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Shipped payments");

    await user.click(screen.getByRole("button", { name: "Actions for Shipped payments" }));
    await user.click(screen.getByRole("button", { name: "Archive" }));

    await waitFor(() => expect(screen.queryByText("Shipped payments")).not.toBeInTheDocument());
    expect(calls.archived).toEqual([1]);
  });

  it("surfaces an inline error when archiving fails", async () => {
    installWorklogApi({ entries: [buildEntry({ id: 1, title: "Shipped payments" })], sources: [ACME] });
    // Override archive to fail for this entry.
    const { server } = await import("@/mocks/server");
    const { http, HttpResponse } = await import("msw");
    server.use(http.post("*/worklog/:id/archive", () => new HttpResponse(null, { status: 500 })));

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Shipped payments");

    await user.click(screen.getByRole("button", { name: "Actions for Shipped payments" }));
    await user.click(screen.getByRole("button", { name: "Archive" }));

    expect(await screen.findByText(ARCHIVE_ERROR_MESSAGE)).toBeInTheDocument();
    // The entry stays because the archive did not commit.
    expect(screen.getByText("Shipped payments")).toBeInTheDocument();
  });

  it("lists the bullets that frame an entry and links each into the Library", async () => {
    installWorklogApi({
      entries: [buildEntry({ id: 1, title: "Shipped payments" })],
      sources: [ACME],
      bullets: [
        buildBullet({ id: 100, text: "Cut checkout latency 40%", worklog_ids: [1] }),
        buildBullet({ id: 200, text: "Unrelated bullet", worklog_ids: [999] }),
      ],
    });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Shipped payments");

    await user.click(screen.getByRole("button", { name: "Actions for Shipped payments" }));

    const derivedLink = await screen.findByRole("link", { name: "Cut checkout latency 40%" });
    expect(derivedLink).toHaveAttribute("href", "/library?bullet=100");
    expect(screen.queryByText("Unrelated bullet")).not.toBeInTheDocument();
  });

  it("gives a tag the same color everywhere and distinct colors per label", async () => {
    installWorklogApi({
      entries: [
        buildEntry({ id: 1, title: "A", entry_date: "2026-07-18", tags: ["backend", "payments"], source_ids: [] }),
        buildEntry({ id: 2, title: "B", entry_date: "2026-07-04", tags: ["backend"], source_ids: [] }),
      ],
      sources: [ACME],
    });

    renderWorklog();
    await screen.findByText("A");

    const backendPills = screen.getAllByText("#backend") as HTMLElement[];
    expect(backendPills).toHaveLength(2);
    expect(backendPills[0].style.color).toBe(backendPills[1].style.color);
    expect(backendPills[0].style.color).not.toBe("");

    const paymentsPill = screen.getByText("#payments") as HTMLElement;
    expect(paymentsPill.style.color).not.toBe(backendPills[0].style.color);
  });

  it("clears all active filters", async () => {
    installWorklogApi({
      entries: [
        buildEntry({ id: 1, title: "Shipped payments", source_ids: [10] }),
        buildEntry({ id: 2, title: "Led team", source_ids: [11] }),
      ],
      sources: [ACME, BETA],
    });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Shipped payments");

    await user.selectOptions(screen.getByLabelText("Source"), "11");
    expect(screen.queryByText("Shipped payments")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByText("Shipped payments")).toBeInTheDocument();
    expect(screen.getByText("Led team")).toBeInTheDocument();
  });

  it("cancels the entry form without saving", async () => {
    const calls = installWorklogApi({ entries: [], sources: [ACME] });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Worklog" });

    await user.click(screen.getByRole("button", { name: "+ Add entry" }));
    expect(screen.getByRole("form", { name: "Add entry" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("form", { name: "Add entry" })).not.toBeInTheDocument();
    expect(calls.created).toHaveLength(0);
  });

  it("opens the entry form on arrival when the new-entry flag is set", async () => {
    installWorklogApi({ entries: [], sources: [ACME] });

    renderWithProviders(
      <SWRConfig value={{ provider: () => new Map() }}>
        <WorklogView />
      </SWRConfig>,
      ["/worklog?new=1"],
    );

    // The form is open without any click, because the route carried the signal.
    expect(await screen.findByRole("form", { name: "Add entry" })).toBeInTheDocument();
  });

  it("leaves the entry form closed on arrival without the flag", async () => {
    installWorklogApi({ entries: [buildEntry({ id: 1, title: "Shipped payments" })], sources: [ACME] });

    renderWorklog();
    await screen.findByText("Shipped payments");

    expect(screen.queryByRole("form", { name: "Add entry" })).not.toBeInTheDocument();
  });

  it("surfaces an error when search fails", async () => {
    installWorklogApi({ entries: [buildEntry({ id: 1, title: "Shipped payments" })], sources: [ACME], failSearch: true });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Shipped payments");

    await user.type(screen.getByLabelText("Search worklog and bullets"), "payments");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Search is unavailable right now.");
  });

  it("clears the search results and query", async () => {
    installWorklogApi({
      entries: [buildEntry({ id: 1, title: "Shipped payments" })],
      sources: [ACME],
      search: buildSearchResult({
        ranked: [{ type: "worklog", id: 1, score: 0.9 }],
        graph: {
          worklog: [{ id: 1, title: "Shipped payments", date: "2026-07-18", score: 0.9, source_ids: [10] }],
          bullets: [],
          sources: [],
        },
      }),
    });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Shipped payments");

    const searchBox = screen.getByLabelText("Search worklog and bullets");
    await user.type(searchBox, "payments");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByRole("list", { name: "Search results" });

    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("list", { name: "Search results" })).not.toBeInTheDocument();
    expect(searchBox).toHaveValue("");
  });

  it("keeps a committed create when the follow-up revalidation fails", async () => {
    installWorklogApi({
      entries: [buildEntry({ id: 1, title: "Existing entry" })],
      sources: [ACME],
      failTimelineAfterWrite: true,
    });

    renderWorklog();
    const user = userEvent.setup();
    await screen.findByText("Existing entry");

    await user.click(screen.getByRole("button", { name: "+ Add entry" }));
    await user.type(screen.getByLabelText("Title"), "Committed entry");
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-01" } });
    await user.click(screen.getByRole("button", { name: "Save entry" }));

    // The write committed, so the form closes and no write error is shown, even
    // though the follow-up revalidation read fails (guards against a duplicate re-save).
    await waitFor(() => expect(screen.queryByRole("form", { name: "Add entry" })).not.toBeInTheDocument());
    expect(screen.queryByText(SAVE_ERROR_MESSAGE)).not.toBeInTheDocument();
    // The cached timeline stays visible rather than blanking to the error state.
    expect(screen.getByText("Existing entry")).toBeInTheDocument();
    expect(screen.queryByText(TIMELINE_ERROR_MESSAGE)).not.toBeInTheDocument();
  });

  it("shows an encouraging empty state when there are no entries", async () => {
    installWorklogApi({ entries: [], sources: [] });

    renderWorklog();

    expect(await screen.findByText("Start your worklog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add your first entry" })).toBeInTheDocument();
  });

  it("shows an error state when the timeline fails to load", async () => {
    installWorklogApi({ failTimeline: true });

    renderWorklog();

    expect(await screen.findByText(TIMELINE_ERROR_MESSAGE)).toBeInTheDocument();
  });
});
