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
