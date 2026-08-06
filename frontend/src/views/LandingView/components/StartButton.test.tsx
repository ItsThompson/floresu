import { screen } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { mockAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/renderWithProviders";

import { START_LABEL } from "../constants";
import { StartButton } from "./StartButton";

/** Hold the resume probe open so the unresolved-session state stays observable. */
function holdSessionResolving() {
  server.use(
    http.post("*/auth/refresh", async () => {
      await delay("infinite");
      return HttpResponse.json(mockAuthUser);
    }),
  );
}

describe("StartButton", () => {
  it("links an anonymous visitor to signup, carrying the primary fill", async () => {
    // The default refresh handler answers 401, so the session resolves anonymous.
    renderWithProviders(<StartButton />);

    const cta = await screen.findByRole("link", { name: START_LABEL });
    expect(cta).toHaveAttribute("href", "/signup");
    // `asChild` renders the button styling onto the anchor.
    expect(cta).toHaveClass("bg-primary", "text-primary-foreground");
  });

  it("renders a disabled control, and no link, while the session is resolving", () => {
    holdSessionResolving();
    renderWithProviders(<StartButton />);

    expect(screen.getByRole("button", { name: START_LABEL })).toBeDisabled();
    expect(screen.queryByRole("link", { name: START_LABEL })).not.toBeInTheDocument();
  });
});
