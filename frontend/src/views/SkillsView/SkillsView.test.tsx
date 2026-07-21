import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { buildSkill } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/renderWithProviders";

import { SkillsView } from "./SkillsView";

/** Serve the skills list; write handlers are installed per test as needed. */
function mockSkills(skills: ReturnType<typeof buildSkill>[]) {
  server.use(http.get("*/skills", () => HttpResponse.json(skills)));
}

function skillRow(name: string): HTMLElement {
  const li = screen.getByText(name).closest("li");
  if (!li) throw new Error(`No row for ${name}`);
  return li;
}

const react = buildSkill({ id: 1, name: "React", usage_count: 4, sort_order: 0 });
const typescript = buildSkill({ id: 2, name: "TypeScript", usage_count: 2, sort_order: 1 });

describe("SkillsView", () => {
  it("shows skills with their derived usage counts", async () => {
    mockSkills([react]);
    renderWithProviders(<SkillsView />);

    expect(await screen.findByText("React")).toBeInTheDocument();
    expect(screen.getByText("used in 4")).toBeInTheDocument();
  });

  it("adds a skill through the explicit form", async () => {
    mockSkills([]);
    let created: { name: string } | null = null;
    server.use(
      http.post("*/skills", async ({ request }) => {
        created = (await request.json()) as { name: string };
        return HttpResponse.json(buildSkill({ id: 9, name: created.name }), { status: 201 });
      }),
    );

    renderWithProviders(<SkillsView />);
    const user = userEvent.setup();
    await screen.findByText(/no skills yet/i);

    await user.type(screen.getByLabelText("New skill"), "GraphQL");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(created).toEqual({ name: "GraphQL" }));
    expect(await screen.findByText("GraphQL")).toBeInTheDocument();
  });

  it("renames a skill in place", async () => {
    mockSkills([react]);
    let renamed: { name: string } | null = null;
    server.use(
      http.put("*/skills/:id", async ({ request }) => {
        renamed = (await request.json()) as { name: string };
        return HttpResponse.json(buildSkill({ id: 1, name: renamed.name }));
      }),
    );

    renderWithProviders(<SkillsView />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Rename React" }));

    const input = screen.getByLabelText("Rename React");
    await user.clear(input);
    await user.type(input, "React 19");
    await user.click(screen.getByRole("button", { name: "Save name" }));

    await waitFor(() => expect(renamed).toEqual({ name: "React 19" }));
    expect(await screen.findByText("React 19")).toBeInTheDocument();
  });

  it("reorders skills via the reorder endpoint", async () => {
    mockSkills([react, typescript]);
    let reorderBody: { skill_ids: number[] } | null = null;
    server.use(
      http.post("*/skills/reorder", async ({ request }) => {
        reorderBody = (await request.json()) as { skill_ids: number[] };
        return HttpResponse.json([]);
      }),
    );

    renderWithProviders(<SkillsView />);
    await screen.findByText("React");

    fireEvent.dragStart(skillRow("TypeScript"));
    fireEvent.drop(skillRow("React"));

    await waitFor(() => expect(reorderBody).toEqual({ skill_ids: [2, 1] }));
  });

  it("archives a skill and removes it from the list", async () => {
    mockSkills([react, typescript]);
    let archivedId: number | null = null;
    server.use(
      http.post("*/skills/:id/archive", ({ params }) => {
        archivedId = Number(params.id);
        return HttpResponse.json(buildSkill({ id: archivedId }));
      }),
    );

    renderWithProviders(<SkillsView />);
    const user = userEvent.setup();
    await screen.findByText("React");

    await user.click(screen.getByRole("button", { name: "Archive React" }));

    await waitFor(() => expect(screen.queryByText("React")).not.toBeInTheDocument());
    expect(archivedId).toBe(1);
    expect(screen.getByText("TypeScript")).toBeInTheDocument();
  });

  it("surfaces a duplicate-name conflict without adding a skill", async () => {
    mockSkills([react]);
    server.use(
      http.post("*/skills", () =>
        HttpResponse.json({ detail: "That skill already exists." }, { status: 409 }),
      ),
    );

    renderWithProviders(<SkillsView />);
    const user = userEvent.setup();
    await screen.findByText("React");

    await user.type(screen.getByLabelText("New skill"), "React");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByText("That skill already exists.")).toBeInTheDocument();
  });
});
