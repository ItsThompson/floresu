import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { assignLocation } from "@/lib/browserNavigation";
import { mockAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

// The one external boundary this screen touches: the full-page browser
// navigation to the agent's redirect URL, which cannot run under jsdom.
vi.mock("@/lib/browserNavigation", () => ({ assignLocation: vi.fn() }));
const mockAssign = vi.mocked(assignLocation);

/**
 * Sociable tests for the OAuth consent screen: they drive the real route tree,
 * session guard, and consent state machine against the MSW-backed AS. The only
 * boundary stubbed is `assignLocation` (the browser navigation to the agent's
 * redirect URL), which cannot run under jsdom.
 */

const AUTH_REQUEST_ID = "req-abc";
const CONSENT_URL = `/authorize?auth_request_id=${AUTH_REQUEST_ID}`;
const APPROVE_REDIRECT = "http://127.0.0.1:8765/callback?code=one-time-code&state=s";
const DENY_REDIRECT = "http://127.0.0.1:8765/callback?error=access_denied&state=s";

/** Make resume-on-mount authenticate, so the consent route renders for a signed-in user. */
function authenticateOnResume() {
  server.use(http.post("*/auth/refresh", () => HttpResponse.json(mockAuthUser)));
}

/** Serve the parked request's context (the agent name the card renders). */
function mockContext(clientName = "Claude") {
  server.use(
    http.get("*/oauth/authorize/context", () =>
      HttpResponse.json({ client_name: clientName, scopes: ["floresu:full"], authenticated: true }),
    ),
  );
}

interface CapturedDecision {
  approve: boolean;
}

/** Serve the decision endpoint, capturing each decision and echoing the loopback URL. */
function mockDecision(captured: CapturedDecision[]) {
  server.use(
    http.post("*/oauth/authorize/decision", async ({ request }) => {
      const body = (await request.json()) as { auth_request_id: string; approve: boolean };
      captured.push({ approve: body.approve });
      return HttpResponse.json({
        redirect_uri: body.approve ? APPROVE_REDIRECT : DENY_REDIRECT,
      });
    }),
  );
}

describe("ConsentView", () => {
  afterEach(() => {
    mockAssign.mockReset();
  });

  it("shows the agent, the single access statement, and the signed-in email", async () => {
    authenticateOnResume();
    mockContext("Claude");

    renderApp([CONSENT_URL]);

    expect(
      await screen.findByRole("heading", { name: /Connect .Claude. to Floresu/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/read and write your worklog/i)).toBeInTheDocument();
    expect(screen.getByText(mockAuthUser.email)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deny" })).toBeInTheDocument();
  });

  it("approves the connection and returns the browser to the agent", async () => {
    authenticateOnResume();
    mockContext();
    const decisions: CapturedDecision[] = [];
    mockDecision(decisions);

    renderApp([CONSENT_URL]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Approve" }));

    await waitFor(() => expect(mockAssign).toHaveBeenCalledWith(APPROVE_REDIRECT));
    expect(decisions).toEqual([{ approve: true }]);
  });

  it("denies the connection and returns control without a token", async () => {
    authenticateOnResume();
    mockContext();
    const decisions: CapturedDecision[] = [];
    mockDecision(decisions);

    renderApp([CONSENT_URL]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Deny" }));

    await waitFor(() => expect(mockAssign).toHaveBeenCalledWith(DENY_REDIRECT));
    expect(decisions).toEqual([{ approve: false }]);
  });

  it("disables both actions while a decision is in flight", async () => {
    authenticateOnResume();
    mockContext();
    // Hold the decision open so the deciding state stays observable.
    server.use(
      http.post("*/oauth/authorize/decision", async () => {
        await delay("infinite");
        return HttpResponse.json({ redirect_uri: APPROVE_REDIRECT });
      }),
    );

    renderApp([CONSENT_URL]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Approve" }));

    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Deny" })).toBeDisabled();
    expect(mockAssign).not.toHaveBeenCalled();
  });

  it("shows an error instead of an approve action for an invalid or expired request", async () => {
    authenticateOnResume();
    server.use(
      http.get("*/oauth/authorize/context", () =>
        HttpResponse.json(
          { detail: "This authorization request expired or does not exist." },
          { status: 404 },
        ),
      ),
    );

    renderApp([CONSENT_URL]);

    expect(await screen.findByRole("alert")).toHaveTextContent(/no longer valid/i);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("shows an error when the auth_request_id is missing", async () => {
    authenticateOnResume();

    renderApp(["/authorize"]);

    expect(await screen.findByRole("alert")).toHaveTextContent(/no longer valid/i);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("shows an error when the context request fails at the network level", async () => {
    authenticateOnResume();
    server.use(http.get("*/oauth/authorize/context", () => HttpResponse.error()));

    renderApp([CONSENT_URL]);

    expect(await screen.findByRole("alert")).toHaveTextContent(/no longer valid/i);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("shows an error and no redirect when recording the decision fails", async () => {
    authenticateOnResume();
    mockContext();
    server.use(
      http.post("*/oauth/authorize/decision", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderApp([CONSENT_URL]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Approve" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn.t record your decision/i);
    expect(mockAssign).not.toHaveBeenCalled();
  });

  it("shows an error and no redirect when the decision request fails at the network level", async () => {
    authenticateOnResume();
    mockContext();
    server.use(http.post("*/oauth/authorize/decision", () => HttpResponse.error()));

    renderApp([CONSENT_URL]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Approve" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn.t record your decision/i);
    expect(mockAssign).not.toHaveBeenCalled();
  });

  it("sends an anonymous visitor to sign-in and returns to consent after authenticating", async () => {
    // Default refresh is 401 → the deep-linked consent URL resolves anonymous.
    mockContext("Claude");

    renderApp([CONSENT_URL]);

    // The session guard bounces to sign-in rather than rendering consent.
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();

    // Default MSW login returns the demo user; sign-in should land back on consent.
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "demo@floresu.com");
    await user.type(screen.getByLabelText("Password"), "Str0ngPass");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByRole("heading", { name: /Connect .Claude. to Floresu/ }),
    ).toBeInTheDocument();
  });
});
