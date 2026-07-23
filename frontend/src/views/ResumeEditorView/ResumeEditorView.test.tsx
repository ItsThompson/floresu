import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { buildAuthUser } from "@/mocks/data";
import { createResumeApiMock } from "@/mocks/resumeApiMock";
import {
  buildBulletpoint,
  buildLibraryRefItem,
  buildLocalItem,
  buildPublishedVersion,
  buildResumeRecord,
  buildSection,
  buildTemplate,
  buildVariant,
} from "@/mocks/resumeFixtures";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

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

/** A resume with one work section holding a library reference and a local item. */
function seedResume(overrides?: Parameters<typeof buildResumeRecord>[0]) {
  const ref = buildLibraryRefItem({ id: "it-ref", bullet_id: 100 });
  const local = buildLocalItem({ id: "it-loc", text: "Local bullet text" });
  return buildResumeRecord({
    id: 1,
    kind: "living",
    title: "Backend Engineer",
    document: {
      schema_version: 1,
      template_id: "classic",
      header: {},
      sections: [
        buildSection({
          id: "sec-work",
          title: "Work Experience",
          item_order: ["it-ref", "it-loc"],
          items: { "it-ref": ref, "it-loc": local },
        }),
      ],
    },
    ...overrides,
  });
}

describe("ResumeEditorView", () => {
  it("loads the resume and resolves library and local item text", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [
        buildBulletpoint({ id: 100, text: "Cut checkout latency by 40%.", used_in_count: 1 }),
      ],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);

    expect(await screen.findByText("Work Experience")).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Cut checkout latency by 40%.")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Local bullet text")).toBeInTheDocument();
  });

  it("recovers from a failed load via Try again and exposes no stale error", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [
        buildBulletpoint({ id: 100, text: "Cut checkout latency by 40%.", used_in_count: 1 }),
      ],
    });
    // Fail only the first resume fetch; the seeded handler serves the retry.
    server.use(
      http.get("*/resumes/1", () => new HttpResponse(null, { status: 500 }), { once: true }),
      ...handlers,
    );
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    // The failed load surfaces the error and a retry affordance.
    expect(await screen.findByText("Could not load this resume.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));

    // The successful reload renders the resume and leaves no residual load error.
    expect(await screen.findByDisplayValue("Cut checkout latency by 40%.")).toBeInTheDocument();
    expect(screen.queryByText("Could not load this resume.")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("saves a local item edit (guarded by the revision)", async () => {
    authenticate();
    const { handlers, resumes } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    const textarea = await screen.findByDisplayValue("Local bullet text");
    await user.clear(textarea);
    await user.type(textarea, "Edited local text");
    await user.tab();

    await waitFor(() => expect(resumes.get(1)?.revision).toBe(2));
  });

  it("adds a bullet from the library into a section", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [
        buildBulletpoint({ id: 100, text: "Cut checkout latency by 40%.", used_in_count: 1 }),
        buildBulletpoint({ id: 200, text: "Led the platform migration.", used_in_count: 1 }),
      ],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /pull from library/i }));
    await user.click(await screen.findByRole("button", { name: /Led the platform migration/ }));

    await waitFor(() =>
      expect(screen.getByDisplayValue("Led the platform migration.")).toBeInTheDocument(),
    );
  });

  it("prompts for scope when editing a bullet shared by two or more resumes", async () => {
    authenticate();
    const { handlers, bullets } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [
        buildBulletpoint({ id: 100, text: "Cut checkout latency by 40%.", used_in_count: 2 }),
      ],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    const textarea = await screen.findByDisplayValue("Cut checkout latency by 40%.");
    await user.clear(textarea);
    await user.type(textarea, "Cut checkout latency by 60%.");
    await user.tab();

    // The shared bullet triggers the scope prompt rather than applying silently.
    const dialog = await screen.findByRole("dialog", { name: /used in 2 resumes/i });
    await user.click(within(dialog).getByRole("radio", { name: /Everywhere/i }));
    await user.click(within(dialog).getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(bullets.get(100)?.text).toBe("Cut checkout latency by 60%."));
  });

  it("clears the scope prompt and shows the re-read prompt when the scoped edit conflicts", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [
        buildBulletpoint({ id: 100, text: "Cut checkout latency by 40%.", used_in_count: 2 }),
      ],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    const textarea = await screen.findByDisplayValue("Cut checkout latency by 40%.");
    await user.clear(textarea);
    await user.type(textarea, "Cut checkout latency by 80%.");
    await user.tab();

    const scopeDialog = await screen.findByRole("dialog", { name: /used in 2 resumes/i });
    // A concurrent change lands between the prompt and the apply: the scoped edit conflicts.
    server.use(
      http.post("*/resumes/bullet-edit", () =>
        HttpResponse.json({ detail: "stale" }, { status: 409 }),
      ),
    );
    await user.click(within(scopeDialog).getByRole("button", { name: "Apply" }));

    // The scope dialog is dismissed and the re-read prompt shows alone (no stacking).
    expect(await screen.findByRole("dialog", { name: /This resume changed/i })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /used in 2 resumes/i })).not.toBeInTheDocument();
  });

  it("applies an edit to a single-use bullet without prompting", async () => {
    authenticate();
    const { handlers, bullets } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [
        buildBulletpoint({ id: 100, text: "Cut checkout latency by 40%.", used_in_count: 1 }),
      ],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    const textarea = await screen.findByDisplayValue("Cut checkout latency by 40%.");
    await user.clear(textarea);
    await user.type(textarea, "Cut checkout latency by 70%.");
    await user.tab();

    await waitFor(() => expect(bullets.get(100)?.text).toBe("Cut checkout latency by 70%."));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("prompts to re-read after a stale write conflict", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    const textarea = await screen.findByDisplayValue("Local bullet text");
    // Force the next update to be rejected as stale.
    server.use(
      http.put("*/resumes/:resumeId", () =>
        HttpResponse.json({ detail: "stale" }, { status: 409 }),
      ),
    );
    await user.clear(textarea);
    await user.type(textarea, "Edited while stale");
    await user.tab();

    expect(await screen.findByRole("dialog", { name: /This resume changed/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Re-read latest/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("changes the template, re-rendering the same content", async () => {
    authenticate();
    const { handlers, resumes } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
      templates: [
        buildTemplate({ id: "classic", name: "Classic" }),
        buildTemplate({ id: "modern", name: "Modern" }),
      ],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByLabelText("Template"), "modern");
    await waitFor(() => expect(resumes.get(1)?.document.template_id).toBe("modern"));
  });

  it("renders a finalized resume read-only (no editing controls)", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [seedResume({ kind: "application", status: "finalized" })],
      bullets: [
        buildBulletpoint({ id: 100, text: "Cut checkout latency by 40%.", used_in_count: 1 }),
      ],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);

    expect(await screen.findByText("Work Experience")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /pull from library/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Resume title")).toBeDisabled();
  });

  it("finalizes an application draft through the confirm gate, freezing it read-only", async () => {
    authenticate();
    const { handlers, resumes, bullets } = createResumeApiMock({
      resumes: [seedResume({ kind: "application", status: "draft" })],
      bullets: [
        buildBulletpoint({ id: 100, text: "Cut checkout latency by 40%.", used_in_count: 2 }),
      ],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    // The library reference is editable before finalize.
    expect(await screen.findByDisplayValue("Cut checkout latency by 40%.")).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Finalize" }));
    // The confirm gate explains that freezing is permanent.
    expect(await screen.findByText(/cannot be undone/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Finalize permanently/ }));

    // The resume reads back finalized: its references are frozen to inline text,
    // they stop counting toward the bullet's "used in N", and it becomes read-only.
    await waitFor(() => expect(resumes.get(1)?.status).toBe("finalized"));
    expect(resumes.get(1)?.document.sections?.[0].items?.["it-ref"].kind).toBe("local");
    expect(bullets.get(100)?.used_in_count).toBe(1);
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /pull from library/i })).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Resume title")).toBeDisabled();
  });

  it("exports a PDF and surfaces a download link", async () => {
    authenticate();
    vi.spyOn(window, "open").mockReturnValue(null);
    const { handlers } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Export/ }));
    expect(await screen.findByRole("link", { name: /Download exported PDF/ })).toBeInTheDocument();
  });

  it("removes an item from a section", async () => {
    authenticate();
    const { handlers, resumes } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    const localRow = (await screen.findByDisplayValue("Local bullet text")).closest(
      "li",
    ) as HTMLElement;
    await user.click(within(localRow).getByRole("button", { name: "Remove item" }));

    await waitFor(() =>
      expect(screen.queryByDisplayValue("Local bullet text")).not.toBeInTheDocument(),
    );
    expect(resumes.get(1)?.document.sections?.[0].item_order).toEqual(["it-ref"]);
  });

  it("adds a net-new inline item that lives only on the resume", async () => {
    authenticate();
    const { handlers, resumes } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /new/i }));
    await user.type(screen.getByLabelText("New bullet text"), "A fresh inline bullet");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(screen.getByDisplayValue("A fresh inline bullet")).toBeInTheDocument(),
    );
    const items = resumes.get(1)?.document.sections?.[0].items ?? {};
    const added = Object.values(items).find(
      (item) => item.kind === "local" && item.text === "A fresh inline bullet",
    );
    expect(added?.kind).toBe("local");
  });

  it("promotes a resume-local item to the library", async () => {
    authenticate();
    const { handlers, resumes } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    const localRow = (await screen.findByDisplayValue("Local bullet text")).closest(
      "li",
    ) as HTMLElement;
    await user.click(within(localRow).getByRole("button", { name: "Promote" }));

    await waitFor(() => expect(resumes.get(1)?.revision).toBe(2));
  });

  it("forks only this resume when the safe scope is chosen for a shared bullet", async () => {
    authenticate();
    const { handlers, resumes, bullets } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [
        buildBulletpoint({ id: 100, text: "Cut checkout latency by 40%.", used_in_count: 2 }),
      ],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    const textarea = await screen.findByDisplayValue("Cut checkout latency by 40%.");
    await user.clear(textarea);
    await user.type(textarea, "Only-here wording.");
    await user.tab();

    const dialog = await screen.findByRole("dialog", { name: /used in 2 resumes/i });
    // "Only this resume" is the default; apply it directly.
    await user.click(within(dialog).getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // The canonical bullet is untouched; the resume item became a local fork.
    expect(bullets.get(100)?.text).toBe("Cut checkout latency by 40%.");
    expect(resumes.get(1)?.document.sections?.[0].items?.["it-ref"].kind).toBe("local");
  });

  it("sets the header identity variant", async () => {
    authenticate();
    const { handlers, resumes } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
      variants: [buildVariant({ id: 5, label: "Personal" })],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByLabelText("Identity variant"), "5");
    await waitFor(() => expect(resumes.get(1)?.document.header?.identity_variant_id).toBe(5));
  });

  it("reorders items within a section by drag and persists the new order", async () => {
    authenticate();
    const { handlers, resumes } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);

    await screen.findByText("Work Experience");
    const handles = screen.getAllByRole("button", { name: "Drag to reorder item" });
    fireEvent.dragStart(handles[0]);
    fireEvent.drop(handles[1]);

    await waitFor(() =>
      expect(resumes.get(1)?.document.sections?.[0].item_order).toEqual(["it-loc", "it-ref"]),
    );
  });

  it("opens the enabled History control and lists the resume's published versions", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(
      ...handlers,
      http.get("*/resumes/:resumeId/revisions", () =>
        HttpResponse.json({
          resume_id: 1,
          versions: [
            buildPublishedVersion({ revision_no: 4, created_at: "2026-07-20T00:00:00Z" }),
            buildPublishedVersion({ revision_no: 2, created_at: "2026-07-18T00:00:00Z" }),
          ],
        }),
      ),
    );
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    // The control is enabled (no longer the disabled "coming soon" seam).
    const historyButton = await screen.findByRole("button", { name: /History/ });
    expect(historyButton).toBeEnabled();
    await user.click(historyButton);

    const dialog = await screen.findByRole("dialog", { name: "Version history" });
    const rows = await within(dialog).findAllByRole("button", { name: /Revision \d/ });
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("Revision 4"),
      expect.stringContaining("Revision 2"),
    ]);
  });

  it("surfaces the finalize error when finalize fails with a non-409 error", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [seedResume({ kind: "application", status: "draft" })],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Finalize" }));
    // A non-409 failure lands when the confirm fires: the finalize error mapping
    // surfaces its fallback message rather than the stale re-read prompt.
    server.use(
      http.post("*/resumes/:resumeId/finalize", () => new HttpResponse(null, { status: 500 })),
    );
    await user.click(await screen.findByRole("button", { name: /Finalize permanently/ }));

    expect(
      await screen.findByText("This resume could not be finalized. Please try again."),
    ).toBeInTheDocument();
    // It did not freeze: the resume stays an editable draft.
    expect(screen.getByRole("button", { name: /pull from library/i })).toBeInTheDocument();
  });

  it("prompts to re-read when finalize conflicts with a 409", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [seedResume({ kind: "application", status: "draft" })],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(...handlers);
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Finalize" }));
    // A concurrent change makes finalize conflict: the write enters `stale`.
    server.use(
      http.post("*/resumes/:resumeId/finalize", () =>
        HttpResponse.json({ detail: "stale" }, { status: 409 }),
      ),
    );
    await user.click(await screen.findByRole("button", { name: /Finalize permanently/ }));

    expect(await screen.findByRole("dialog", { name: /This resume changed/i })).toBeInTheDocument();
    // The resume stays an editable draft (it did not freeze).
    expect(screen.getByRole("button", { name: /pull from library/i })).toBeInTheDocument();
  });

  it("shows no download link when the export returns no download_url", async () => {
    authenticate();
    const { handlers } = createResumeApiMock({
      resumes: [seedResume()],
      bullets: [buildBulletpoint({ id: 100, used_in_count: 1 })],
    });
    server.use(...handlers);
    server.use(
      http.post("*/resumes/:resumeId/export", () =>
        HttpResponse.json({ resume_id: 1, revision: 1, object_key: "u/1/r/1/rev/1.pdf" }),
      ),
    );
    renderApp(["/resumes/1"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Export/ }));

    // exportPdf() resolves to null: no download link appears and the failure shows.
    expect(await screen.findByText(/Export failed/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Download exported PDF/ })).not.toBeInTheDocument();
  });
});
