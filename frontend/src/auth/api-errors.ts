import { extractProblem } from "@/lib/problemDetail";

import type { AuthResult } from "./types";

/**
 * Turn an openapi-fetch error body into a failed `AuthResult`.
 *
 * The backend renders every error as problem+json. `extractProblem` is the
 * single RFC 9457 reader; this adapter just wraps its `message`/`fields` into
 * the `AuthResult` failure arm. A malformed or empty body degrades to a generic
 * message rather than surfacing `undefined`.
 */
export function toAuthResult(error: unknown): AuthResult {
  const { message, fields } = extractProblem(error);
  return { ok: false, message, fields };
}
