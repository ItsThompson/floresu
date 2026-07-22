import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { buildAuthUser } from "@/mocks/data";
import { createJobAppsApiMock } from "@/mocks/jobAppsApiMock";
import { buildJobApplicationSummary } from "@/mocks/jobAppsFixtures";
import { buildBulletpoint, buildResumeRecord } from "@/mocks/resumeFixtures";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

// A linked resume can be opened in the editor; stub the PDF.js boundary so
// navigating into it never loads the real library under jsdom.
vi.mock("@/views/ResumeEditorView/pdf/renderPdf", () => ({
  renderPdfToCanvas: vi.fn().mockResolvedValue(undefined),
}));

function authenticate() {
  server.use(
    http.post("*/auth/refresh", () =>
      HttpResponse.json(buildAuthUser({ has_completed_onboarding: true })),
    ),
  );
}

describe("JobApplicationsView", () => {
  it("lists company, role, linked resume, and added date, and opens a linked resume", async () => {
    authenticate();
    const { handlers } = createJobAppsApiMock({
      applications: [
        buildJobApplicationSummary({
          id: 1,
          company: "Acme Corp",
          role_title: "Backend Engineer",
          created_at: "2026-07-18T09:30:00Z",
        }),
      ],
      resumes: [
        buildResumeRecord({
          id: 50,
          kind: "application",
          title: "Acme — SWE",
          job_application_id: 1,
        }),
      ],
      bullets: [buildBulletpoint({ id: 100 })],
    });
    server.use(...handlers);
    renderApp(["/applications"]);
    const user = userEvent.setup();

    const row = (await screen.findByText("Acme Corp")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Backend Engineer")).toBeInTheDocument();
    expect(within(row).getByText("Added")).toBeInTheDocument();
    expect(within(row).getByText("Jul 18, 2026")).toBeInTheDocument();

    const resumeLink = within(row).getByRole("link", { name: "Acme — SWE" });
    expect(resumeLink).toHaveAttribute("href", "/resumes/50");

    // Selecting the linked resume opens it in the editor.
    await user.click(resumeLink);
    expect(await screen.findByText(/All resumes/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no applications", async () => {
    authenticate();
    const { handlers } = createJobAppsApiMock({ applications: [], resumes: [] });
    server.use(...handlers);
    renderApp(["/applications"]);

    expect(await screen.findByText(/No job applications yet/)).toBeInTheDocument();
  });

  it("adds a job application capturing company and role, starting status added", async () => {
    authenticate();
    const { handlers, applications } = createJobAppsApiMock({ applications: [], resumes: [] });
    server.use(...handlers);
    renderApp(["/applications"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "+ New application" }));
    await user.type(screen.getByLabelText("Company"), "Globex");
    await user.type(screen.getByLabelText("Role title"), "Staff Engineer");
    await user.click(screen.getByRole("button", { name: "Add application" }));

    const row = (await screen.findByText("Globex")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Staff Engineer")).toBeInTheDocument();
    expect(within(row).getByText("Added")).toBeInTheDocument();
    await waitFor(() => expect(applications.size).toBe(1));
    expect([...applications.values()][0].status).toBe("added");
  });

  it("forks a living resume into an application draft linked 1:1 and opens it", async () => {
    authenticate();
    const { handlers, resumes } = createJobAppsApiMock({
      applications: [
        buildJobApplicationSummary({ id: 1, company: "Acme Corp", role_title: "Backend Engineer" }),
      ],
      resumes: [buildResumeRecord({ id: 1, kind: "living", title: "Backend Engineer" })],
      bullets: [buildBulletpoint({ id: 100 })],
    });
    server.use(...handlers);
    renderApp(["/applications"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Create resume" }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByRole("combobox"), "1");
    await user.click(within(dialog).getByRole("button", { name: "Create resume" }));

    // The fork produced an application draft linked 1:1 to the application, and the
    // view opened it in the editor.
    expect(await screen.findByText(/All resumes/)).toBeInTheDocument();
    const forked = [...resumes.values()].find((resume) => resume.kind === "application");
    expect(forked?.job_application_id).toBe(1);
    expect(forked?.status).toBe("draft");
  });

  it("marks an application submitted through the confirm gate, finalizing its resume", async () => {
    authenticate();
    const { handlers, applications, resumes } = createJobAppsApiMock({
      applications: [buildJobApplicationSummary({ id: 1, company: "Acme Corp" })],
      resumes: [
        buildResumeRecord({
          id: 50,
          kind: "application",
          title: "Acme — SWE",
          job_application_id: 1,
        }),
      ],
      bullets: [buildBulletpoint({ id: 100 })],
    });
    server.use(...handlers);
    renderApp(["/applications"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Mark submitted" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/cannot be undone/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Mark submitted" }));

    await waitFor(() => expect(applications.get(1)?.status).toBe("submitted"));
    expect(resumes.get(50)?.status).toBe("finalized");
    const row = (await screen.findByText("Acme Corp")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Submitted")).toBeInTheDocument();
  });

  it("rejects submit with no linked resume, showing a recoverable error and staying added", async () => {
    authenticate();
    const { handlers, applications } = createJobAppsApiMock({
      applications: [buildJobApplicationSummary({ id: 1, company: "Acme Corp" })],
      resumes: [],
    });
    server.use(...handlers);
    renderApp(["/applications"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Mark submitted" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Mark submitted" }));

    expect(await screen.findByText(/Link a resume to this application/)).toBeInTheDocument();
    expect(applications.get(1)?.status).toBe("added");
    const row = (await screen.findByText("Acme Corp")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Added")).toBeInTheDocument();
  });
});
