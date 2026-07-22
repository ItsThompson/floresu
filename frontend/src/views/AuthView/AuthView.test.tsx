import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

describe("AuthView", () => {
  it("renders the sign-in form at /signin", async () => {
    renderApp(["/signin"]);
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("links to the sign-up screen", async () => {
    renderApp(["/signin"]);
    const link = await screen.findByRole("link", { name: "Create an account" });
    expect(link).toHaveAttribute("href", "/signup");
  });

  it("renders the register form at /signup", async () => {
    renderApp(["/signup"]);
    expect(await screen.findByRole("heading", { name: "Create your account" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
  });

  it("routes to Home after a successful sign-in", async () => {
    // Default MSW login returns the demo user.
    renderApp(["/signin"]);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "demo@floresu.com");
    await user.type(screen.getByLabelText("Password"), "Str0ngPass");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
  });

  it("shows a generic error and preserves input on wrong credentials", async () => {
    server.use(
      http.post("*/auth/login", () =>
        HttpResponse.json({ detail: "Invalid email or password." }, { status: 401 }),
      ),
    );
    renderApp(["/signin"]);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "demo@floresu.com");
    await user.type(screen.getByLabelText("Password"), "WrongPass9");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    // Input is preserved for retry; the form never reports a false success.
    expect(screen.getByLabelText("Email")).toHaveValue("demo@floresu.com");
    expect(screen.queryByRole("heading", { name: "Home" })).not.toBeInTheDocument();
  });
});
