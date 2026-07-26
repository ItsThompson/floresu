import { expect, test, type APIRequestContext } from "@playwright/test";

import {
  completeTokenGrant,
  pkcePair,
  refreshWithToken,
  registerClient,
  startAuthorization,
} from "../harness/oauth";
import { registerAndOnboard } from "../harness/support";

const AGENT_NAME = "E2E Revoke Agent";

/**
 * Run one authorization-code grant for an already-registered client and return
 * its refresh token. Each call re-consents the same (user, client) grant through
 * the API, so every token it mints belongs to that one grant and a single revoke
 * tears them all down together.
 */
async function mintRefreshToken(request: APIRequestContext, clientId: string): Promise<string> {
  const { verifier, challenge } = pkcePair();
  const authRequestId = await startAuthorization(request, clientId, challenge);
  const { refreshToken } = await completeTokenGrant(request, {
    authRequestId,
    clientId,
    verifier,
  });
  return refreshToken;
}

/**
 * B3: connect an agent through the browser consent screen, then revoke it in
 * Settings and prove the revoke invalidates the client's refresh token
 * immediately. Account-scoped and built on the OAuth harness, so it does not
 * re-implement PKCE or the code exchange.
 *
 * Refresh tokens rotate on use, so a token spent proving pre-revoke liveness is
 * already consumed and would report `invalid_grant` with or without a revoke. To
 * keep the post-revoke assertion attributable to the revoke alone, the test holds
 * a second, never-used token on the same grant and checks that one after revoke.
 */
test("connect an agent via consent, then revoke it and kill its refresh token", async ({
  page,
}) => {
  await registerAndOnboard(page);

  // The post-approval redirect targets the agent's loopback; stub it so the
  // consent navigation lands harmlessly (the grant is recorded at approval).
  await page.route("http://127.0.0.1:8765/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<html>ok</html>" }),
  );

  // Connect the agent by driving the OAuth consent screen to Approve.
  const clientId = await registerClient(page.request, AGENT_NAME);
  const { challenge } = pkcePair();
  const authRequestId = await startAuthorization(page.request, clientId, challenge);
  await page.goto(`/authorize?auth_request_id=${authRequestId}`);
  await expect(
    page.getByRole("heading", { name: new RegExp(`Connect .*${AGENT_NAME}.* to Floresu`) }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();

  // Hold two refresh tokens on the connected grant: one to spend on the
  // pre-revoke liveness check (rotation consumes it), and one held untouched so
  // its post-revoke failure is caused by the revoke, not by prior use.
  const heldToken = await mintRefreshToken(page.request, clientId);
  const probeToken = await mintRefreshToken(page.request, clientId);

  // Pre-revoke: the grant is live, so refreshing the spendable token succeeds.
  const beforeRevoke = await refreshWithToken(page.request, { clientId, refreshToken: probeToken });
  expect(beforeRevoke.status).toBe(200);
  expect(beforeRevoke.error).toBeUndefined();

  // Revoke the client through Settings, confirm-gated.
  await page.goto("/settings/agents");
  const clientRow = page.getByRole("listitem").filter({ hasText: AGENT_NAME });
  await expect(clientRow).toBeVisible();
  await clientRow.getByRole("button", { name: "Revoke" }).click();
  const confirm = page.getByRole("alertdialog");
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "Revoke" }).click();

  // The revoked client leaves the connected list (asserted in the UI).
  await expect(clientRow).toHaveCount(0);

  // The held refresh token is invalidated immediately: refresh returns invalid_grant.
  const afterRevoke = await refreshWithToken(page.request, { clientId, refreshToken: heldToken });
  expect(afterRevoke.error).toBe("invalid_grant");
});
