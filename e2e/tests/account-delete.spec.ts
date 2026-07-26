import { expect, test } from "@playwright/test";

import {
  completeTokenGrant,
  pkcePair,
  refreshWithToken,
  registerClient,
  startAuthorization,
} from "../harness/oauth";
import { registerAndOnboard } from "../harness/support";

/**
 * Irreversible account deletion, end to end. A throwaway account created in the
 * test connects an agent (the OAuth harness holds its refresh token), then a
 * human drives the destructive delete flow in the browser: the confirm dialog
 * states the action cannot be undone and stays closed behind a typed-email gate.
 * After deletion the account is gone (sign-in fails) and the connected agent's
 * held refresh token is revoked immediately (`invalid_grant`), the direct proof
 * that access is gone rather than the account merely being unreachable.
 *
 * The delete surface lives in `DataPanel` at /settings/data; `/settings/account`
 * is read-only. The account is throwaway so the irreversible flow stays scoped to
 * a single in-test account.
 */
test("delete account: confirm-gated + typed-email, then sign-in fails and the agent is revoked", async ({
  page,
}) => {
  const { email, password } = await registerAndOnboard(page);

  // Connect an agent and hold its refresh token so revoke-on-delete is provable.
  // The token mechanics have no meaningful UI, so drive them through the harness;
  // the browser drives the delete flow, which is the thing under test.
  const clientId = await registerClient(page.request, "E2E Delete Agent");
  const { verifier, challenge } = pkcePair();
  const authRequestId = await startAuthorization(page.request, clientId, challenge);
  const { refreshToken } = await completeTokenGrant(page.request, {
    authRequestId,
    clientId,
    verifier,
  });

  // The destructive operations live in the Data panel, not the read-only Account panel.
  await page.goto("/settings/data");
  await expect(page.getByRole("heading", { name: "Delete account" })).toBeVisible();
  await page.getByRole("button", { name: "Delete my account" }).click();

  // Confirm-gated: the dialog states the action cannot be undone before it can fire.
  const confirm = page.getByRole("alertdialog", { name: "Delete your account?" });
  await expect(confirm).toBeVisible();
  await expect(confirm.getByText(/cannot be undone/i)).toBeVisible();

  // Typed-email gate: the destructive control stays disabled until the exact email
  // is typed, so a wrong value never enables it.
  const confirmButton = confirm.getByRole("button", { name: "Delete account" });
  await expect(confirmButton).toBeDisabled();
  const emailField = confirm.getByRole("textbox", { name: "Confirmation phrase" });
  await emailField.fill("not-the-email");
  await expect(confirmButton).toBeDisabled();
  await emailField.fill(email);
  await expect(confirmButton).toBeEnabled();
  await confirmButton.click();

  // On success the session clears and the now-anonymous user lands on sign-in.
  await expect(page).toHaveURL(/\/signin$/);

  // The account is gone: sign-in with the deleted credentials is unauthorized.
  const login = await page.request.post("/auth/login", { data: { email, password } });
  expect(login.status()).toBe(401);

  // The connected agent's grant is revoked: its held refresh token is rejected
  // immediately with invalid_grant (the direct proof access is gone).
  const refreshed = await refreshWithToken(page.request, { clientId, refreshToken });
  expect(refreshed).toEqual({ status: 400, error: "invalid_grant" });
});
