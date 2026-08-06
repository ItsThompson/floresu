import { screen } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { AuthUser } from "@/auth";
import { buildAuthUser, mockAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/renderWithProviders";

import { LandingView } from "./LandingView";
import {
  DUAL_MODE_HEADING,
  DUAL_MODE_TRACKS,
  FAQ_HEADING,
  FAQ_ITEMS,
  FINAL_CTA_HEADLINE,
  HEADER_SIGNED_IN_LABEL,
  HERO_HEADLINE,
  HERO_SECONDARY_LABEL,
  HOW_IT_WORKS_HEADING,
  HOW_IT_WORKS_ID,
  HOW_IT_WORKS_STEPS,
  START_LABEL,
  VALUE_HEADLINE,
} from "./constants";

/** Resolve the session as signed in. Defaults to the onboarded demo account. */
function authenticateOnResume(user: AuthUser = mockAuthUser) {
  server.use(http.post("*/auth/refresh", () => HttpResponse.json(user)));
}

/** Hold the resume probe open so the unresolved-session state stays observable. */
function holdSessionResolving() {
  server.use(
    http.post("*/auth/refresh", async () => {
      await delay("infinite");
      return HttpResponse.json(mockAuthUser);
    }),
  );
}

describe("LandingView", () => {
  it("carries exactly one display moment: the hero headline", async () => {
    renderWithProviders(<LandingView />);
    await screen.findAllByRole("link", { name: START_LABEL });

    const hero = screen.getByRole("heading", { level: 1, name: HERO_HEADLINE });
    expect(hero).toHaveClass("display-xl");
    expect(document.querySelectorAll('[class*="display-"]')).toHaveLength(1);
  });

  it("sends an anonymous visitor to signup from every primary action", async () => {
    // The default refresh handler answers 401, so the session resolves anonymous.
    renderWithProviders(<LandingView />);

    // Deliberate repetition: the header, the hero, and the closing band.
    const ctas = await screen.findAllByRole("link", { name: START_LABEL });
    expect(ctas).toHaveLength(3);
    for (const cta of ctas) {
      expect(cta).toHaveAttribute("href", "/signup");
    }
  });

  it("sends a signed-in, onboarded visitor into the app", async () => {
    authenticateOnResume();
    renderWithProviders(<LandingView />);

    expect(await screen.findByRole("link", { name: HEADER_SIGNED_IN_LABEL })).toHaveAttribute(
      "href",
      "/home",
    );
    for (const cta of screen.getAllByRole("link", { name: START_LABEL })) {
      expect(cta).toHaveAttribute("href", "/home");
    }
  });

  it("sends a signed-in visitor who has not finished onboarding back to the wizard", async () => {
    authenticateOnResume(buildAuthUser({ has_completed_onboarding: false }));
    renderWithProviders(<LandingView />);

    expect(await screen.findByRole("link", { name: HEADER_SIGNED_IN_LABEL })).toHaveAttribute(
      "href",
      "/onboarding",
    );
    for (const cta of screen.getAllByRole("link", { name: START_LABEL })) {
      expect(cta).toHaveAttribute("href", "/onboarding");
    }
  });

  it("renders disabled primary actions, and no signup link, while the session resolves", () => {
    holdSessionResolving();
    renderWithProviders(<LandingView />);

    const ctas = screen.getAllByRole("button", { name: START_LABEL });
    expect(ctas).toHaveLength(2);
    for (const cta of ctas) {
      expect(cta).toBeDisabled();
    }
    expect(screen.queryByRole("link", { name: START_LABEL })).not.toBeInTheDocument();
    // The header holds its control back rather than flashing the wrong label.
    expect(screen.queryByRole("link", { name: HEADER_SIGNED_IN_LABEL })).not.toBeInTheDocument();
  });

  it("carries espresso text on the bloom fill, and no reading copy", async () => {
    renderWithProviders(<LandingView />);
    await screen.findAllByRole("link", { name: START_LABEL });

    const bloom = screen.getByRole("heading", { name: VALUE_HEADLINE });
    expect(bloom).toHaveClass("bg-bloom", "text-espresso");
    expect(bloom).not.toHaveClass("text-primary-foreground");
    // A headline only: the supporting sentence sits beside the fill, not on it.
    expect(bloom.textContent).toBe(VALUE_HEADLINE);
  });

  it("anchors the secondary hero action at the explainer section", async () => {
    renderWithProviders(<LandingView />);
    await screen.findAllByRole("link", { name: START_LABEL });

    expect(screen.getByRole("link", { name: HERO_SECONDARY_LABEL })).toHaveAttribute(
      "href",
      `#${HOW_IT_WORKS_ID}`,
    );
    expect(document.getElementById(HOW_IT_WORKS_ID)).toBeInTheDocument();
  });

  it("renders every section: chrome, the five bands, and the footer", async () => {
    renderWithProviders(<LandingView />);
    await screen.findAllByRole("link", { name: START_LABEL });

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: HERO_HEADLINE })).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: HOW_IT_WORKS_HEADING })).toBeInTheDocument();
    for (const step of HOW_IT_WORKS_STEPS) {
      expect(screen.getByRole("heading", { name: step.title })).toBeInTheDocument();
    }

    expect(screen.getByRole("heading", { name: VALUE_HEADLINE })).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: DUAL_MODE_HEADING })).toBeInTheDocument();
    for (const track of DUAL_MODE_TRACKS) {
      expect(screen.getByRole("heading", { name: track.heading })).toBeInTheDocument();
    }

    expect(screen.getByRole("heading", { name: FAQ_HEADING })).toBeInTheDocument();
    for (const item of FAQ_ITEMS) {
      expect(screen.getByRole("heading", { name: item.question })).toBeInTheDocument();
      expect(screen.getByText(item.answer)).toBeInTheDocument();
    }

    expect(screen.getByRole("heading", { name: FINAL_CTA_HEADLINE })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });
});
