import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { buildAuthUser } from "@/mocks/data";
import { createResumeApiMock } from "@/mocks/resumeApiMock";
import { buildResumeRecord } from "@/mocks/resumeFixtures";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

// The editor is reachable after a create; stub the PDF.js boundary so navigating
// into it never loads the real library under jsdom.
vi.mock("@/lib/renderPdf", () => ({
  renderPdfToCanvas: vi.fn().mockResolvedValue(undefined),
}));

function authenticate() {
  server.use(
    http.post("*/auth/refresh", () =>
      HttpResponse.json(buildAuthUser({ has_completed_onboarding: true })),
    ),
  );
}

describe("ResumesListView", () => {
  it("groups living and application resumes under separate headings", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [
        buildResumeRecord({ id: 1, kind: "living", title: "Backend Engineer" }),
        buildResumeRecord({ id: 2, kind: "living", title: "Eng Manager" }),
        buildResumeRecord({ id: 3, kind: "application", status: "finalized", title: "Acme — SWE" }),
      ],
    });
    server.use(...handlers);
    renderApp(["/resumes"]);

    const living = (await screen.findByText("Living (role-targeted)")).closest("section") as HTMLElement;
    expect(within(living).getByText("Backend Engineer")).toBeInTheDocument();
    expect(within(living).getByText("Eng Manager")).toBeInTheDocument();

    const applications = screen.getByText("Applications").closest("section") as HTMLElement;
    expect(within(applications).getByText("Acme — SWE")).toBeInTheDocument();
    expect(within(applications).getByText("Finalized")).toBeInTheDocument();
  });

  it("shows encouraging empty states when there are no resumes", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({ resumes: [] });
    server.use(...handlers);
    renderApp(["/resumes"]);

    expect(await screen.findByText(/No living resumes yet/)).toBeInTheDocument();
    expect(screen.getByText(/No application resumes yet/)).toBeInTheDocument();
  });

  it("creates a living resume and opens it in the editor", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({ resumes: [] });
    server.use(...handlers);
    renderApp(["/resumes"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "+ New resume" }));
    await user.type(screen.getByLabelText("Title"), "Staff Engineer");
    await user.click(screen.getByRole("button", { name: "Create" }));

    // Landing in the editor (its back link) proves the create succeeded and the
    // view navigated to the new resume.
    expect(await screen.findByRole("link", { name: /All resumes/ })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Staff Engineer")).toBeInTheDocument();
  });

  it("permanently deletes a resume after confirmation", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [buildResumeRecord({ id: 1, kind: "living", title: "Backend Engineer" })],
    });
    server.use(...handlers);
    renderApp(["/resumes"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete permanently" }));

    await waitFor(() => expect(screen.queryByText("Backend Engineer")).not.toBeInTheDocument());
    expect(screen.getByText(/No living resumes yet/)).toBeInTheDocument();
  });

  it("keeps the create dialog open without navigating when POST /resumes fails", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({ resumes: [] });
    server.use(...handlers);
    server.use(http.post("*/resumes", () => new HttpResponse(null, { status: 500 })));
    renderApp(["/resumes"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "+ New resume" }));
    await user.type(screen.getByLabelText("Title"), "Staff Engineer");
    await user.click(screen.getByRole("button", { name: "Create" }));

    // create() resolves to null: the dialog stays open with an inline error and
    // the view never navigates into the editor (no "All resumes" back link).
    expect(await screen.findByText(/Could not create the resume/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /All resumes/ })).not.toBeInTheDocument();
  });

  it("keeps the resume listed when DELETE /resumes/{id} fails", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [buildResumeRecord({ id: 1, kind: "living", title: "Backend Engineer" })],
    });
    server.use(...handlers);
    server.use(
      http.delete("*/resumes/:resumeId", () =>
        HttpResponse.json({ detail: "Delete failed." }, { status: 500 }),
      ),
    );
    renderApp(["/resumes"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete permanently" }));

    // remove() resolves to false: the resume stays listed and the dialog surfaces
    // the failure instead of closing.
    expect(await screen.findByText(/Could not delete the resume/)).toBeInTheDocument();
    expect(screen.getByText("Backend Engineer")).toBeInTheDocument();
  });
});
