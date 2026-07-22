import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/renderWithProviders";

import { LibraryView } from "./LibraryView";
import { SAVE_ERROR_FALLBACK } from "./constants";
import { installLibraryApi } from "./__tests__/api";
import {
  buildBullet,
  buildSearchResult,
  buildSource,
  buildTag,
  buildWorklogEntry,
} from "./__tests__/fixtures";

const acme = buildSource({ id: 1, display_label: "Acme — Senior Engineer", sort_order: 0 });
const floresu = buildSource({ id: 2, kind: "project", display_label: "Floresu", sort_order: 1 });

describe("LibraryView", () => {
  let user: ReturnType<typeof userEvent.setup>;

  beforeEach(() => {
    user = userEvent.setup();
  });
  afterEach(() => server.resetHandlers());

  it("groups bullets by source with usage labels and a shared marker", async () => {
    installLibraryApi({
      sources: [acme, floresu],
      bullets: [
        buildBullet({
          id: 10,
          text: "Cut checkout latency 40%",
          source_ids: [1],
          used_in_count: 2,
        }),
        buildBullet({
          id: 11,
          text: "Owned Stripe integration",
          source_ids: [1],
          used_in_count: 0,
        }),
        buildBullet({ id: 12, text: "Built the MCP server", source_ids: [2], used_in_count: 1 }),
      ],
    });

    renderWithProviders(<LibraryView />);

    expect(
      await screen.findByRole("heading", { name: /Acme — Senior Engineer/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Floresu/ })).toBeInTheDocument();

    // Shared bullet (used in 2) shows the count and the shared marker.
    expect(screen.getByText("Used in 2")).toBeInTheDocument();
    expect(screen.getByText("Shared")).toBeInTheDocument();
    // Unused and single-use bullets do not.
    expect(screen.getByText("Unused")).toBeInTheDocument();
    expect(screen.getByText("Used in 1")).toBeInTheDocument();
  });

  it("lists a bullet linked to two sources under both", async () => {
    installLibraryApi({
      sources: [acme, floresu],
      bullets: [buildBullet({ id: 10, text: "Spanned two sources", source_ids: [1, 2] })],
    });

    renderWithProviders(<LibraryView />);

    await screen.findByRole("heading", { name: /Acme — Senior Engineer/ });
    expect(screen.getAllByText("Spanned two sources")).toHaveLength(2);
  });

  it("shows the empty-library message when there are no bullets", async () => {
    installLibraryApi({ sources: [acme], bullets: [] });
    renderWithProviders(<LibraryView />);
    expect(await screen.findByText(/No bullets yet/)).toBeInTheDocument();
  });

  it("returns nothing for an empty query and keeps browsing", async () => {
    installLibraryApi({
      sources: [acme],
      bullets: [buildBullet({ id: 10, text: "Cut checkout latency 40%", source_ids: [1] })],
    });

    renderWithProviders(<LibraryView />);
    await screen.findByRole("heading", { name: /Acme — Senior Engineer/ });

    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(screen.queryByRole("heading", { name: "Top matches" })).not.toBeInTheDocument();
    expect(screen.getByText("Cut checkout latency 40%")).toBeInTheDocument();
  });

  it("runs hybrid search: ranked list plus grouped-by-source, including an unattached hit", async () => {
    const handle = installLibraryApi({ sources: [acme] });
    handle.setSearchResult(
      buildSearchResult({
        ranked: [
          { type: "source", id: 1, score: 0.9 },
          { type: "worklog", id: 30, score: 0.6 },
          { type: "worklog", id: 31, score: 0.4 },
        ],
        graph: {
          sources: [
            { id: 1, kind: "role", label: "Acme — Senior Engineer", match_score: 0.9, score: 0.95 },
          ],
          worklog: [
            { id: 30, title: "Shipped payments", date: "2026-07-18", score: 0.6, source_ids: [1] },
            {
              id: 31,
              title: "Unattached research note",
              date: "2026-07-10",
              score: 0.4,
              source_ids: [],
            },
          ],
          bullets: [
            {
              id: 20,
              text: "Cut checkout latency 40%",
              score: 0.55,
              worklog_ids: [],
              source_ids: [1],
            },
          ],
        },
      }),
    );

    renderWithProviders(<LibraryView />);
    await screen.findByRole("button", { name: "Search" });

    await user.type(screen.getByRole("searchbox", { name: "Search experience" }), "payments");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("heading", { name: "Top matches" })).toBeInTheDocument();
    const topMatches = screen.getByRole("region", { name: "Top matches" });
    // The unattached worklog hit still appears in the flat ranked list.
    expect(within(topMatches).getByText("Unattached research note")).toBeInTheDocument();

    // Grouped by source: the directly-matched source is called out.
    const grouped = screen.getByRole("region", { name: "Grouped by source" });
    expect(within(grouped).getByText("matched directly")).toBeInTheDocument();
    expect(within(grouped).getByText("Shipped payments")).toBeInTheDocument();
    // Bullets attached to the source appear in its group too (ranked mix).
    expect(within(grouped).getByText("Cut checkout latency 40%")).toBeInTheDocument();
  });

  it("shows an inline error when search fails", async () => {
    installLibraryApi({ sources: [acme] });
    server.use(http.post("*/search", () => new HttpResponse(null, { status: 500 })));

    renderWithProviders(<LibraryView />);
    await screen.findByRole("button", { name: "Search" });

    await user.type(screen.getByRole("searchbox", { name: "Search experience" }), "payments");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Search failed. Try again.");
  });

  it("creates a bullet and shows it in the library", async () => {
    installLibraryApi({
      sources: [acme],
      bullets: [buildBullet({ id: 10, text: "Existing bullet", source_ids: [1] })],
    });

    renderWithProviders(<LibraryView />);
    await screen.findByText("Existing bullet");

    await user.click(screen.getByRole("button", { name: "New bullet" }));
    const form = screen.getByRole("form", { name: "New bullet" });
    await user.type(within(form).getByLabelText("Statement"), "Freshly created framing");
    await user.click(within(form).getByRole("button", { name: "Save bullet" }));

    expect(await screen.findByText("Freshly created framing")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "New bullet" })).not.toBeInTheDocument();
  });

  it("preserves input and shows an inline error when a save fails", async () => {
    installLibraryApi({ sources: [acme], bullets: [] });
    server.use(
      http.post("*/bullets", () =>
        HttpResponse.json({ detail: "Statement is too long" }, { status: 422 }),
      ),
    );

    renderWithProviders(<LibraryView />);
    await screen.findByRole("button", { name: "New bullet" });

    await user.click(screen.getByRole("button", { name: "New bullet" }));
    const statement = screen.getByLabelText("Statement");
    await user.type(statement, "My careful draft");
    await user.click(screen.getByRole("button", { name: "Save bullet" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Statement is too long");
    // The form stays open and the typed text is preserved for a retry.
    expect(screen.getByLabelText("Statement")).toHaveValue("My careful draft");
  });

  it("edits a canonical bullet, updating its text in place", async () => {
    installLibraryApi({
      sources: [acme],
      bullets: [buildBullet({ id: 10, text: "Old framing", source_ids: [1] })],
    });

    renderWithProviders(<LibraryView />);
    await screen.findByText("Old framing");

    await user.click(screen.getByRole("button", { name: "Edit" }));
    const statement = screen.getByLabelText("Statement");
    expect(statement).toHaveValue("Old framing");
    await user.clear(statement);
    await user.type(statement, "Refined framing");
    await user.click(screen.getByRole("button", { name: "Save bullet" }));

    expect(await screen.findByText("Refined framing")).toBeInTheDocument();
    expect(screen.queryByText("Old framing")).not.toBeInTheDocument();
  });

  it("re-seeds the form when the edit target switches, writing to the right bullet", async () => {
    const handle = installLibraryApi({
      sources: [acme],
      bullets: [
        buildBullet({ id: 10, text: "Bullet A text", source_ids: [1] }),
        buildBullet({ id: 11, text: "Bullet B text", source_ids: [1] }),
      ],
    });

    renderWithProviders(<LibraryView />);
    await screen.findByText("Bullet A text");

    const editButtonFor = (text: string) => {
      const row = screen.getByText(text).closest("li") as HTMLElement;
      return within(row).getByRole("button", { name: "Edit" });
    };

    // Edit A: the form seeds with A's text.
    await user.click(editButtonFor("Bullet A text"));
    expect(screen.getByLabelText("Statement")).toHaveValue("Bullet A text");

    // Switch to Edit B without cancelling: the form must re-seed to B, not keep A's text.
    await user.click(editButtonFor("Bullet B text"));
    expect(screen.getByLabelText("Statement")).toHaveValue("Bullet B text");

    // Saving writes A-free content onto B only; A is untouched (no wrong-target write).
    await user.clear(screen.getByLabelText("Statement"));
    await user.type(screen.getByLabelText("Statement"), "Edited B only");
    await user.click(screen.getByRole("button", { name: "Save bullet" }));

    await screen.findByText("Edited B only");
    const bullets = handle.getBullets();
    expect(bullets.find((entry) => entry.id === 11)?.text).toBe("Edited B only");
    expect(bullets.find((entry) => entry.id === 10)?.text).toBe("Bullet A text");
  });

  it("re-seeds to an empty form when 'New bullet' is clicked while editing", async () => {
    installLibraryApi({
      sources: [acme],
      bullets: [buildBullet({ id: 10, text: "Bullet A text", source_ids: [1] })],
    });

    renderWithProviders(<LibraryView />);
    await screen.findByText("Bullet A text");

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Statement")).toHaveValue("Bullet A text");

    await user.click(screen.getByRole("button", { name: "New bullet" }));
    expect(screen.getByRole("form", { name: "New bullet" })).toBeInTheDocument();
    expect(screen.getByLabelText("Statement")).toHaveValue("");
  });

  it("archives a bullet, removing it from the library", async () => {
    installLibraryApi({
      sources: [acme],
      bullets: [
        buildBullet({ id: 10, text: "Keep me", source_ids: [1] }),
        buildBullet({ id: 11, text: "Archive me", source_ids: [1] }),
      ],
    });

    renderWithProviders(<LibraryView />);
    const archiveMe = await screen.findByText("Archive me");
    const row = archiveMe.closest("li");
    expect(row).not.toBeNull();

    await user.click(within(row as HTMLElement).getByRole("button", { name: "Archive" }));

    await waitFor(() => expect(screen.queryByText("Archive me")).not.toBeInTheDocument());
    expect(screen.getByText("Keep me")).toBeInTheDocument();
  });

  it("recovers from an initial load failure via Try again", async () => {
    installLibraryApi({ sources: [acme], bullets: [] });
    server.use(http.get("*/bullets", () => new HttpResponse(null, { status: 500 })));

    renderWithProviders(<LibraryView />);
    expect(await screen.findByText("Could not load your library.")).toBeInTheDocument();

    // Restore a working bullets endpoint, then retry.
    server.use(
      http.get("*/bullets", () =>
        HttpResponse.json([buildBullet({ id: 10, text: "Now it loads", source_ids: [1] })]),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Now it loads")).toBeInTheDocument();
  });

  it("filters search by tag and source without error", async () => {
    installLibraryApi({
      sources: [acme],
      tags: [buildTag({ id: 1, label: "backend" })],
      worklog: [buildWorklogEntry({ id: 30, title: "Shipped payments" })],
    });

    renderWithProviders(<LibraryView />);
    await screen.findByRole("button", { name: "Search" });

    // Toggling a tag filter is reflected in the control state.
    const tagCheckbox = screen.getByRole("checkbox", { name: "backend" });
    await user.click(tagCheckbox);
    expect(tagCheckbox).toBeChecked();
  });

  it("sends If-Match with the loaded bullet revision on an edit save", async () => {
    installLibraryApi({
      sources: [acme],
      bullets: [buildBullet({ id: 10, text: "Old framing", source_ids: [1], revision: 4 })],
    });
    let sentIfMatch: string | null = null;
    server.use(
      http.put("*/bullets/:id", async ({ request }) => {
        sentIfMatch = request.headers.get("If-Match");
        return HttpResponse.json(
          buildBullet({ id: 10, text: "Refined framing", source_ids: [1], revision: 5 }),
        );
      }),
    );

    renderWithProviders(<LibraryView />);
    await screen.findByText("Old framing");

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Statement"));
    await user.type(screen.getByLabelText("Statement"), "Refined framing");
    await user.click(screen.getByRole("button", { name: "Save bullet" }));

    // The successful save closes the editor; assert the sent optimistic token.
    await waitFor(() =>
      expect(screen.queryByRole("form", { name: "Edit bullet" })).not.toBeInTheDocument(),
    );
    expect(sentIfMatch).toBe("4");
  });

  it("opens the stale prompt on a 409 and does not report success", async () => {
    const handle = installLibraryApi({
      sources: [acme],
      bullets: [buildBullet({ id: 10, text: "Loaded framing", source_ids: [1], revision: 1 })],
    });

    renderWithProviders(<LibraryView />);
    await screen.findByText("Loaded framing");

    await user.click(screen.getByRole("button", { name: "Edit" }));
    // A concurrent writer changes the bullet after we loaded it.
    handle.recordExternalEdit(10, "Changed by someone else");

    await user.clear(screen.getByLabelText("Statement"));
    await user.type(screen.getByLabelText("Statement"), "My local edit");
    await user.click(screen.getByRole("button", { name: "Save bullet" }));

    // The recoverable prompt appears; the edit was not applied.
    expect(
      await screen.findByRole("dialog", { name: "This bulletpoint changed" }),
    ).toBeInTheDocument();
    // No false success: the editor stays open and no generic save error shows.
    expect(screen.getByRole("form", { name: "Edit bullet" })).toBeInTheDocument();
    expect(screen.queryByText(SAVE_ERROR_FALLBACK)).not.toBeInTheDocument();
    // The stored bullet still holds the concurrent writer's text (no overwrite).
    expect(handle.getBullets().find((entry) => entry.id === 10)?.text).toBe(
      "Changed by someone else",
    );
  });

  it("re-reads the current bullet and lets a retried save succeed", async () => {
    const handle = installLibraryApi({
      sources: [acme],
      bullets: [buildBullet({ id: 10, text: "Loaded framing", source_ids: [1], revision: 1 })],
    });

    renderWithProviders(<LibraryView />);
    await screen.findByText("Loaded framing");

    await user.click(screen.getByRole("button", { name: "Edit" }));
    handle.recordExternalEdit(10, "Server's newer text");

    await user.clear(screen.getByLabelText("Statement"));
    await user.type(screen.getByLabelText("Statement"), "My stale edit");
    await user.click(screen.getByRole("button", { name: "Save bullet" }));

    await screen.findByRole("dialog", { name: "This bulletpoint changed" });

    // Re-read reopens the editor on the server's current text, not the stale edit.
    await user.click(screen.getByRole("button", { name: "Re-read latest" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Statement")).toHaveValue("Server's newer text"),
    );
    expect(
      screen.queryByRole("dialog", { name: "This bulletpoint changed" }),
    ).not.toBeInTheDocument();

    // A retried save now matches the current revision and succeeds.
    await user.clear(screen.getByLabelText("Statement"));
    await user.type(screen.getByLabelText("Statement"), "Reconciled edit");
    await user.click(screen.getByRole("button", { name: "Save bullet" }));

    await screen.findByText("Reconciled edit");
    expect(screen.queryByRole("form", { name: "Edit bullet" })).not.toBeInTheDocument();
    expect(handle.getBullets().find((entry) => entry.id === 10)?.text).toBe("Reconciled edit");
  });
});
