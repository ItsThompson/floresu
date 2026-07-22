import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

async function fillAndSubmit(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Create account" }));
}

describe("RegisterForm", () => {
  it("attaches a duplicate-email 409 to the email field and preserves input", async () => {
    server.use(
      http.post("*/auth/register", () =>
        HttpResponse.json(
          {
            detail: "An account with this email already exists.",
            fields: { email: "This email is already registered." },
          },
          { status: 409 },
        ),
      ),
    );
    renderApp(["/signup"]);
    await fillAndSubmit("taken@floresu.com", "Str0ngPass");

    // Await the async error state before asserting the field wiring.
    expect(await screen.findByText("This email is already registered.")).toBeInTheDocument();
    const emailField = screen.getByLabelText("Email");
    expect(emailField).toHaveAttribute("aria-invalid", "true");
    // Entered value preserved for correction.
    expect(emailField).toHaveValue("taken@floresu.com");
  });

  it("attaches a weak-password 422 to the password field", async () => {
    server.use(
      http.post("*/auth/register", () =>
        HttpResponse.json(
          { detail: "Validation failed", fields: { password: "Password must be at least 8 characters." } },
          { status: 422 },
        ),
      ),
    );
    renderApp(["/signup"]);
    await fillAndSubmit("new@floresu.com", "weak");

    expect(await screen.findByText("Password must be at least 8 characters.")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
  });
});
