import { createHash, randomBytes } from "node:crypto";

import { expect, type APIRequestContext } from "@playwright/test";

import { bodyText } from "./support";

/** A loopback redirect the AS accepts (loopback http or https only). */
export const AGENT_REDIRECT_URI = "http://127.0.0.1:8765/callback";

function base64url(input: Buffer): string {
  return input.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** A PKCE verifier + its S256 challenge. */
export function pkcePair(): { verifier: string; challenge: string } {
  const verifier = base64url(randomBytes(32));
  const challenge = base64url(createHash("sha256").update(verifier).digest());
  return { verifier, challenge };
}

/** Dynamic Client Registration: returns the minted client id. */
export async function registerClient(
  request: APIRequestContext,
  clientName: string,
): Promise<string> {
  const response = await request.post("/oauth/register", {
    data: { redirect_uris: [AGENT_REDIRECT_URI], client_name: clientName },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
  return ((await response.json()) as { client_id: string }).client_id;
}

/**
 * Begin an authorization request and return the opaque `auth_request_id` the AS
 * parks for the consent screen. Does not follow the 302 (the browser drives the
 * consent UI at `/authorize?auth_request_id=...`).
 */
export async function startAuthorization(
  request: APIRequestContext,
  clientId: string,
  challenge: string,
): Promise<string> {
  const response = await request.get("/oauth/authorize", {
    params: {
      client_id: clientId,
      redirect_uri: AGENT_REDIRECT_URI,
      response_type: "code",
      code_challenge: challenge,
      code_challenge_method: "S256",
      state: "e2e-state",
    },
    maxRedirects: 0,
  });
  expect(response.status(), await bodyText(response)).toBe(302);
  const location = response.headers()["location"];
  const authRequestId = new URL(location).searchParams.get("auth_request_id");
  expect(authRequestId, `no auth_request_id in ${location}`).toBeTruthy();
  return authRequestId as string;
}

/**
 * Complete the consent decision and exchange the code for tokens. Approves the
 * parked request via `POST /oauth/authorize/decision`, pulls the loopback `code`,
 * then exchanges it at `POST /oauth/token` with the PKCE verifier. Returns the
 * refresh token so the revoke test can prove it stops working after revoke.
 */
export async function completeTokenGrant(
  request: APIRequestContext,
  params: { authRequestId: string; clientId: string; verifier: string },
): Promise<{ accessToken: string; refreshToken: string }> {
  const decision = await request.post("/oauth/authorize/decision", {
    data: { auth_request_id: params.authRequestId, approve: true },
  });
  expect(decision.ok(), await bodyText(decision)).toBeTruthy();
  const { redirect_uri: redirectUri } = (await decision.json()) as { redirect_uri: string };
  const code = new URL(redirectUri).searchParams.get("code");
  expect(code, `no code in ${redirectUri}`).toBeTruthy();

  const token = await request.post("/oauth/token", {
    form: {
      grant_type: "authorization_code",
      client_id: params.clientId,
      code: code as string,
      code_verifier: params.verifier,
      redirect_uri: AGENT_REDIRECT_URI,
    },
  });
  expect(token.ok(), await bodyText(token)).toBeTruthy();
  const body = (await token.json()) as { access_token: string; refresh_token: string };
  return { accessToken: body.access_token, refreshToken: body.refresh_token };
}

/**
 * Attempt a refresh with a held refresh token via `POST /oauth/token`. Returns the
 * raw status and parsed OAuth `error` (when present) without asserting ok, so the
 * caller can observe the `invalid_grant` failure after the grant is revoked.
 */
export async function refreshWithToken(
  request: APIRequestContext,
  params: { clientId: string; refreshToken: string },
): Promise<{ status: number; error?: string }> {
  const response = await request.post("/oauth/token", {
    form: {
      grant_type: "refresh_token",
      client_id: params.clientId,
      refresh_token: params.refreshToken,
    },
  });
  const status = response.status();
  if (response.ok()) return { status };
  const body = (await response.json()) as { error?: string };
  return body.error ? { status, error: body.error } : { status };
}
