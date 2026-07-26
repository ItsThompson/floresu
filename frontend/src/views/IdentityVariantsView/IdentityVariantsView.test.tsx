import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { buildVariant } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/renderWithProviders";

import { IdentityVariantsView } from "./IdentityVariantsView";

type Variant = ReturnType<typeof buildVariant>;

/**
 * Serve a mutable identity-variants list so create/update/set-default flows see
 * the refetched result. Returns a controller the write handlers mutate.
 */
function mockVariantsList(initial: Variant[]) {
  const state = { list: [...initial] };
  server.use(http.get("*/identity-variants", () => HttpResponse.json(state.list)));
  return state;
}

const primary = buildVariant({ id: 1, label: "Primary", is_default: true });
const alt = buildVariant({ id: 2, label: "Recruiting", is_default: false });

describe("IdentityVariantsView", () => {
  it("lists variants and marks the default", async () => {
    mockVariantsList([primary, alt]);
    renderWithProviders(<IdentityVariantsView />);

    expect(await screen.findByText("Primary")).toBeInTheDocument();
    expect(screen.getByText("Recruiting")).toBeInTheDocument();
    expect(screen.getByText("Default")).toBeInTheDocument();
  });

  it("forces the default on when creating the first variant", async () => {
    const state = mockVariantsList([]);
    let created: { is_default: boolean; label: string } | null = null;
    server.use(
      http.post("*/identity-variants", async ({ request }) => {
        created = (await request.json()) as { is_default: boolean; label: string };
        const variant = buildVariant({ id: 5, label: created.label, is_default: true });
        state.list = [variant];
        return HttpResponse.json(variant, { status: 201 });
      }),
    );

    renderWithProviders(<IdentityVariantsView />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "New variant" }));

    const defaultToggle = screen.getByRole("checkbox");
    expect(defaultToggle).toBeChecked();
    expect(defaultToggle).toBeDisabled();

    await user.type(screen.getByLabelText("Label"), "Primary");
    await user.type(screen.getByLabelText("Full name"), "Taylor Dev");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(created).toMatchObject({ label: "Primary", is_default: true }));
    expect(await screen.findByText("Primary")).toBeInTheDocument();
  });

  it("blocks submit and flags both required fields when they are empty", async () => {
    mockVariantsList([primary, alt]);
    let postCalled = false;
    server.use(
      http.post("*/identity-variants", () => {
        postCalled = true;
        return HttpResponse.json(buildVariant({ id: 9 }), { status: 201 });
      }),
    );

    renderWithProviders(<IdentityVariantsView />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "New variant" }));

    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findAllByText("This field is required.")).toHaveLength(2);
    expect(postCalled).toBe(false);
  });

  it("sets a different variant as default", async () => {
    const state = mockVariantsList([primary, alt]);
    let updateBody: { is_default: boolean } | null = null;
    server.use(
      http.put("*/identity-variants/:id", async ({ request, params }) => {
        updateBody = (await request.json()) as { is_default: boolean };
        state.list = [
          { ...primary, is_default: false },
          { ...alt, is_default: true },
        ];
        return HttpResponse.json(buildVariant({ id: Number(params.id), is_default: true }));
      }),
    );

    renderWithProviders(<IdentityVariantsView />);
    const user = userEvent.setup();
    await screen.findByText("Recruiting");

    await user.click(screen.getByRole("button", { name: "Set default" }));

    await waitFor(() => expect(updateBody).toMatchObject({ is_default: true }));
  });

  it("disables archiving the default variant", async () => {
    mockVariantsList([primary, alt]);
    renderWithProviders(<IdentityVariantsView />);

    await screen.findByText("Primary");
    expect(screen.getByRole("button", { name: "Archive Primary" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Archive Recruiting" })).toBeEnabled();
  });

  it("edits a variant", async () => {
    mockVariantsList([primary, alt]);
    let editBody: { label: string } | null = null;
    server.use(
      http.put("*/identity-variants/:id", async ({ request, params }) => {
        editBody = (await request.json()) as { label: string };
        return HttpResponse.json(buildVariant({ id: Number(params.id), label: editBody.label }));
      }),
    );

    renderWithProviders(<IdentityVariantsView />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit Recruiting" }));

    const label = screen.getByLabelText("Label");
    await user.clear(label);
    await user.type(label, "Recruiting 2025");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(editBody).toMatchObject({ label: "Recruiting 2025" }));
  });

  it("prompts for a replacement when archiving a referenced variant", async () => {
    mockVariantsList([primary, alt]);
    server.use(
      http.post("*/identity-variants/:id/archive", () =>
        HttpResponse.json(
          {
            detail: "This variant is referenced by a living resume.",
            code: "VALIDATION",
            violations: [
              {
                rule: "identity_variant_replacement_required",
                ids: ["7"],
                message: "referenced by resume 7",
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );

    renderWithProviders(<IdentityVariantsView />);
    const user = userEvent.setup();
    await screen.findByText("Recruiting");

    await user.click(screen.getByRole("button", { name: "Archive Recruiting" }));

    const dialog = await screen.findByRole("dialog", { name: "Pick a replacement variant" });
    expect(within(dialog).getByText(/1 living resume/)).toBeInTheDocument();
    // The replacement selector offers the other (non-archived) variant.
    expect(within(dialog).getByRole("option", { name: "Primary" })).toBeInTheDocument();
  });

  it("posts the chosen replacement and closes the prompt on confirm", async () => {
    mockVariantsList([primary, alt]);
    let archiveBody: { replacement_variant_id?: number } | null = null;
    server.use(
      http.post("*/identity-variants/:id/archive", async ({ request, params }) => {
        const raw = await request.text();
        const body = raw ? (JSON.parse(raw) as { replacement_variant_id?: number }) : {};
        if (body.replacement_variant_id == null) {
          return HttpResponse.json(
            {
              detail: "This variant is referenced by a living resume.",
              code: "VALIDATION",
              violations: [
                {
                  rule: "identity_variant_replacement_required",
                  ids: ["7"],
                  message: "referenced by resume 7",
                },
              ],
            },
            { status: 422 },
          );
        }
        archiveBody = body;
        return HttpResponse.json({
          ...alt,
          id: Number(params.id),
          archived_at: "2026-01-01T00:00:00Z",
        });
      }),
    );

    renderWithProviders(<IdentityVariantsView />);
    const user = userEvent.setup();
    await screen.findByText("Recruiting");

    await user.click(screen.getByRole("button", { name: "Archive Recruiting" }));
    const dialog = await screen.findByRole("dialog", { name: "Pick a replacement variant" });
    // The lone candidate (Primary, id 1) is preselected; confirm posts it.
    await user.click(within(dialog).getByRole("button", { name: "Archive and re-point" }));

    await waitFor(() => expect(archiveBody).toMatchObject({ replacement_variant_id: 1 }));
    // The prompt closes and the archived variant leaves the list.
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Pick a replacement variant" })).toBeNull(),
    );
    expect(screen.queryByText("Recruiting")).toBeNull();
  });
});
