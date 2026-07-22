import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { buildBullet, buildSourceRecord, buildWorklogSummary, mockAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

/**
 * Sociable tests for the source detail: they drive the real route tree, session
 * guard, and detail hooks against the MSW-backed API. `authenticate` makes
 * resume-on-mount sign the demo user in so the guarded route renders.
 */

function authenticate() {
  server.use(http.post("*/auth/refresh", () => HttpResponse.json(mockAuthUser)));
}

const roleRecord = buildSourceRecord({
  id: 100,
  kind: "role",
  display_label: "Acme — Engineer",
  date_start: "2024-01-01",
  date_end: null,
  summary: "Built things.",
  detail: { company: "Acme", job_title: "Engineer", title_aliases: ["SWE II"], location: "Remote" },
});

/** Serve one source's detail plus its (filterable) framings and worklog. */
function mockDetail(options: {
  bullets?: ReturnType<typeof buildBullet>[];
  worklog?: ReturnType<typeof buildWorklogSummary>[];
}) {
  server.use(
    http.get("*/sources/:id", ({ params }) =>
      HttpResponse.json(buildSourceRecord({ ...roleRecord, id: Number(params.id) })),
    ),
    http.get("*/bullets", () => HttpResponse.json(options.bullets ?? [])),
    http.get("*/worklog", () => HttpResponse.json(options.worklog ?? [])),
  );
}

describe("ProfileSourceDetailView", () => {
  it("creates a role from the create route and routes to its detail", async () => {
    authenticate();
    let created: { kind: string; company: string; job_title: string; display_label: string } | null =
      null;
    server.use(
      http.post("*/sources", async ({ request }) => {
        created = (await request.json()) as typeof created;
        return HttpResponse.json(buildSourceRecord({ id: 100 }), { status: 201 });
      }),
    );
    mockDetail({});

    renderApp(["/profile/sources/new?kind=role"]);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Company"), "Acme");
    await user.type(screen.getByLabelText("Job title"), "Engineer");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(created).toEqual({
        kind: "role",
        display_label: "Acme — Engineer",
        company: "Acme",
        job_title: "Engineer",
        title_aliases: [],
        location: null,
        date_start: null,
        date_end: null,
        summary: null,
      }),
    );
    // After create it navigates to the detail (three columns render).
    expect(await screen.findByRole("heading", { name: "Bullet framings" })).toBeInTheDocument();
  });

  it("renders the three columns with a populated form, framings, and month-grouped worklog", async () => {
    authenticate();
    mockDetail({
      bullets: [buildBullet({ id: 400, text: "Improved engagement 35%.", used_in_count: 2 })],
      worklog: [
        buildWorklogSummary({ id: 500, title: "Shipped migration", entry_date: "2025-09-18", tags: ["backend"] }),
        buildWorklogSummary({ id: 501, title: "Fixed cache bug", entry_date: "2025-08-02" }),
      ],
    });

    renderApp(["/profile/sources/100"]);

    expect(await screen.findByDisplayValue("Acme")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Engineer")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Basic information" })).toBeInTheDocument();

    const framings = screen.getByRole("region", { name: "Bullet framings" });
    expect(within(framings).getByText("Improved engagement 35%.")).toBeInTheDocument();
    expect(within(framings).getByText(/used in 2/)).toBeInTheDocument();
    expect(within(framings).getByLabelText("Shared across resumes")).toBeInTheDocument();

    const worklog = screen.getByRole("region", { name: "Work log" });
    expect(within(worklog).getByText("September 2025")).toBeInTheDocument();
    expect(within(worklog).getByText("August 2025")).toBeInTheDocument();
    expect(within(worklog).getByText("Shipped migration")).toBeInTheDocument();
    expect(within(worklog).getByText("backend")).toBeInTheDocument();
  });

  it("adds a worklog entry from the panel pre-attached to the source", async () => {
    authenticate();
    mockDetail({ worklog: [] });
    let entryBody: { title: string; entry_date: string; source_ids: number[] } | null = null;
    server.use(
      http.post("*/worklog", async ({ request }) => {
        entryBody = (await request.json()) as typeof entryBody;
        return HttpResponse.json({ ...buildWorklogSummary({ id: 900 }), bullet_ids: [] }, { status: 201 });
      }),
    );

    renderApp(["/profile/sources/100"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Add entry" }));
    const form = screen.getByRole("form", { name: "Add worklog entry" });
    await user.type(within(form).getByLabelText("Title"), "Paired on rollout");
    await user.type(within(form).getByLabelText("Date"), "2025-09-20");
    await user.click(within(form).getByRole("button", { name: "Add entry" }));

    await waitFor(() =>
      expect(entryBody).toMatchObject({
        title: "Paired on rollout",
        entry_date: "2025-09-20",
        source_ids: [100],
      }),
    );
  });

  it("adds a bullet framing linked to the source", async () => {
    authenticate();
    mockDetail({ bullets: [] });
    let bulletBody: { text: string; source_ids: number[] } | null = null;
    server.use(
      http.post("*/bullets", async ({ request }) => {
        bulletBody = (await request.json()) as typeof bulletBody;
        return HttpResponse.json(buildBullet({ id: 950, text: "New framing" }), { status: 201 });
      }),
    );

    renderApp(["/profile/sources/100"]);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("New framing"), "Reduced load time 42%.");
    await user.click(screen.getByRole("button", { name: "Add framing" }));

    await waitFor(() =>
      expect(bulletBody).toEqual({ text: "Reduced load time 42%.", source_ids: [100] }),
    );
  });

  it("archives the source and returns to the hub", async () => {
    authenticate();
    mockDetail({});
    let archivedId: number | null = null;
    server.use(
      http.post("*/sources/:id/archive", ({ params }) => {
        archivedId = Number(params.id);
        return HttpResponse.json(buildSourceRecord({ id: archivedId }));
      }),
    );

    renderApp(["/profile/sources/100"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Archive" }));

    await waitFor(() => expect(archivedId).toBe(100));
    expect(await screen.findByRole("heading", { name: "Career Profile" })).toBeInTheDocument();
  });
});
