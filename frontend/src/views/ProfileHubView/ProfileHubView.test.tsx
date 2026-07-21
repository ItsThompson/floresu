import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildSkill, buildSourceSummary, buildVariant } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/renderWithProviders";

import { SECTION_ORDER_STORAGE_KEY } from "./constants";
import { ProfileHubView } from "./ProfileHubView";

/**
 * Sociable tests for the profile hub: they drive the real hub hooks and drag
 * reorder against the MSW-backed API. Each test installs the source/skill/variant
 * reads it needs; localStorage is cleared so the section order starts at default.
 */

interface HubFixtures {
  sources?: ReturnType<typeof buildSourceSummary>[];
  skills?: ReturnType<typeof buildSkill>[];
  variants?: ReturnType<typeof buildVariant>[];
}

function mockHub({ sources = [], skills = [], variants = [] }: HubFixtures) {
  server.use(
    http.get("*/sources", () => HttpResponse.json(sources)),
    http.get("*/skills", () => HttpResponse.json(skills)),
    http.get("*/identity-variants", () => HttpResponse.json(variants)),
  );
}

const roleAlpha = buildSourceSummary({ id: 1, kind: "role", display_label: "Alpha Co", sort_order: 0 });
const roleBeta = buildSourceSummary({ id: 2, kind: "role", display_label: "Beta Co", sort_order: 1 });

/** The <li> for a source row, located by its display label link. */
function rowFor(label: string): HTMLElement {
  const li = screen.getByText(label).closest("li");
  if (!li) throw new Error(`No row for ${label}`);
  return li;
}

describe("ProfileHubView", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  it("shows section cards previewing sources, skills, and variants", async () => {
    mockHub({
      sources: [
        roleAlpha,
        buildSourceSummary({ id: 3, kind: "project", display_label: "StudyBoost" }),
        buildSourceSummary({ id: 4, kind: "education", display_label: "BSc CS" }),
      ],
      skills: [buildSkill({ id: 10, name: "React", usage_count: 5 })],
      variants: [buildVariant({ id: 20, label: "Primary", is_default: true })],
    });

    renderWithProviders(<ProfileHubView />);

    expect(await screen.findByText("Alpha Co")).toBeInTheDocument();
    expect(screen.getByText("StudyBoost")).toBeInTheDocument();
    expect(screen.getByText("BSc CS")).toBeInTheDocument();
    expect(screen.getByText("React")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Primary")).toBeInTheDocument();
    // Each fixed section renders a card.
    for (const title of ["Work Experience", "Projects", "Skills", "Education & Certifications", "Identity"]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
  });

  it("persists a new item order within a kind via the reorder endpoint", async () => {
    mockHub({ sources: [roleAlpha, roleBeta] });
    let reorderBody: { kind: string; source_ids: number[] } | null = null;
    server.use(
      http.post("*/sources/reorder", async ({ request }) => {
        reorderBody = (await request.json()) as { kind: string; source_ids: number[] };
        return HttpResponse.json([]);
      }),
    );

    renderWithProviders(<ProfileHubView />);
    await screen.findByText("Alpha Co");

    // Drag Beta onto Alpha, so Beta takes Alpha's leading position.
    fireEvent.dragStart(rowFor("Beta Co"));
    fireEvent.drop(rowFor("Alpha Co"));

    await waitFor(() => expect(reorderBody).toEqual({ kind: "role", source_ids: [2, 1] }));
  });

  it("archives a source and removes it from the active list", async () => {
    mockHub({ sources: [roleAlpha, roleBeta] });
    let archivedId: number | null = null;
    server.use(
      http.post("*/sources/:id/archive", ({ params }) => {
        archivedId = Number(params.id);
        return HttpResponse.json(buildSourceSummary({ id: archivedId }));
      }),
    );

    renderWithProviders(<ProfileHubView />);
    await screen.findByText("Alpha Co");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Archive Alpha Co" }));

    await waitFor(() => expect(screen.queryByText("Alpha Co")).not.toBeInTheDocument());
    expect(archivedId).toBe(1);
    expect(screen.getByText("Beta Co")).toBeInTheDocument();
  });

  it("reorders section cards by drag and persists the order to localStorage", async () => {
    mockHub({ sources: [roleAlpha] });

    renderWithProviders(<ProfileHubView />);
    await screen.findByText("Alpha Co");

    // Drag the Projects card onto the Work Experience card.
    fireEvent.dragStart(screen.getByRole("button", { name: "Drag to reorder Projects" }));
    fireEvent.drop(screen.getByRole("article", { name: "Work Experience" }));

    await waitFor(() => {
      const stored = JSON.parse(window.localStorage.getItem(SECTION_ORDER_STORAGE_KEY) ?? "[]");
      expect(stored[0]).toBe("projects");
      expect(stored).toContain("work");
    });
  });

  it("surfaces a failed reorder as a dismissible banner", async () => {
    mockHub({ sources: [roleAlpha, roleBeta] });
    server.use(
      http.post("*/sources/reorder", () =>
        HttpResponse.json({ detail: "Reorder rejected." }, { status: 409 }),
      ),
    );

    renderWithProviders(<ProfileHubView />);
    await screen.findByText("Alpha Co");

    fireEvent.dragStart(rowFor("Beta Co"));
    fireEvent.drop(rowFor("Alpha Co"));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Reorder rejected.")).toBeInTheDocument();
  });

  it("shows an error state when the profile fails to load", async () => {
    server.use(
      http.get("*/sources", () => HttpResponse.error()),
      http.get("*/skills", () => HttpResponse.json([])),
      http.get("*/identity-variants", () => HttpResponse.json([])),
    );

    renderWithProviders(<ProfileHubView />);

    expect(await screen.findByText(/could not load your profile/i)).toBeInTheDocument();
  });
});
