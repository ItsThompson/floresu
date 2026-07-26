import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildResumeSummary } from "@/mocks/resumeFixtures";
import { server } from "@/mocks/server";
import { buildEntry } from "@/mocks/worklogFixtures";
import { renderWithProviders } from "@/test/renderWithProviders";

import { HomeView } from "./HomeView";

/**
 * The activity feed opens an SSE `EventSource`, absent under jsdom. A no-op fake
 * keeps the feed region mounted without a real stream; this ticket only adds the
 * worklog and resumes regions, so the feed's own behavior is covered elsewhere.
 */
class FakeEventSource {
  addEventListener(): void {}
  close(): void {}
}

function worklogRegion() {
  return screen.getByRole("region", { name: "Recent worklog" });
}

function resumesRegion() {
  return screen.getByRole("region", { name: "My resumes" });
}

describe("HomeView", () => {
  beforeEach(() => vi.stubGlobal("EventSource", FakeEventSource));
  afterEach(() => vi.unstubAllGlobals());

  it("renders three individually assertable regions", async () => {
    renderWithProviders(<HomeView />);

    expect(worklogRegion()).toBeInTheDocument();
    expect(resumesRegion()).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Activity feed" })).toBeInTheDocument();

    // Let the parallel reads settle so the regions leave their loading state.
    await screen.findByText("Shipped payments migration");
  });

  it("renders real worklog and resume items on a seeded account", async () => {
    renderWithProviders(<HomeView />);

    // The default harness seeds one worklog entry and three resumes.
    expect(
      await within(worklogRegion()).findByText("Shipped payments migration"),
    ).toBeInTheDocument();
    const resumeRow = (await within(resumesRegion()).findByText("Backend Engineer")).closest("li");
    expect(resumeRow).not.toBeNull();
    expect(
      within(resumeRow as HTMLElement)
        .getByRole("link", { name: "Open" })
        .getAttribute("href"),
    ).toBe("/resumes/10");
  });

  it("keeps the resumes region when the worklog read fails", async () => {
    server.use(http.get("*/worklog", () => new HttpResponse(null, { status: 500 })));
    renderWithProviders(<HomeView />);

    expect(await within(worklogRegion()).findByRole("alert")).toHaveTextContent(
      "Could not load your recent worklog.",
    );
    expect(await within(resumesRegion()).findByText("Backend Engineer")).toBeInTheDocument();
  });

  it("keeps the worklog region when the resumes read fails", async () => {
    server.use(http.get("*/resumes", () => new HttpResponse(null, { status: 500 })));
    renderWithProviders(<HomeView />);

    expect(await within(resumesRegion()).findByRole("alert")).toHaveTextContent(
      "Could not load your resumes.",
    );
    expect(
      await within(worklogRegion()).findByText("Shipped payments migration"),
    ).toBeInTheDocument();
  });

  it("shows each region's own empty state and does not error when the account is empty", async () => {
    server.use(
      http.get("*/worklog", () => HttpResponse.json([])),
      http.get("*/resumes", () => HttpResponse.json([])),
    );
    renderWithProviders(<HomeView />);

    expect(await within(worklogRegion()).findByText("No worklog entries yet.")).toBeInTheDocument();
    expect(await within(resumesRegion()).findByText("No resumes yet.")).toBeInTheDocument();
    expect(worklogRegion()).toBeInTheDocument();
    expect(resumesRegion()).toBeInTheDocument();
  });

  it("caps the recent worklog to the newest five, newest-first", async () => {
    const entries = Array.from({ length: 7 }, (_, index) =>
      buildEntry({
        id: index + 1,
        title: `Entry ${index + 1}`,
        entry_date: `2026-07-0${index + 1}`,
      }),
    );
    server.use(http.get("*/worklog", () => HttpResponse.json(entries)));
    renderWithProviders(<HomeView />);

    await within(worklogRegion()).findByText("Entry 7");
    const titles = within(worklogRegion())
      .getAllByText(/^Entry \d$/)
      .map((element) => element.textContent);

    expect(titles).toEqual(["Entry 7", "Entry 6", "Entry 5", "Entry 4", "Entry 3"]);
    expect(within(worklogRegion()).queryByText("Entry 2")).not.toBeInTheDocument();
  });

  it("uses distinct resume fixtures without cross-region leakage", async () => {
    server.use(
      http.get("*/resumes", () =>
        HttpResponse.json([buildResumeSummary({ id: 42, title: "Growth PM resume" })]),
      ),
    );
    renderWithProviders(<HomeView />);

    const openLink = await within(resumesRegion()).findByRole("link", { name: "Open" });
    expect(openLink.getAttribute("href")).toBe("/resumes/42");
    expect(within(worklogRegion()).queryByText("Growth PM resume")).not.toBeInTheDocument();
  });
});
