/**
 * Reads the backend's RFC 9457 problem+json error body into the pieces a view
 * needs: a human message, an optional field-level map, and the structural
 * violations array. `openapi-fetch` puts the parsed error body on `error` for a
 * non-2xx response; a network-level failure throws instead, so a non-object or
 * empty body degrades to the fallback message rather than surfacing `undefined`.
 *
 * The auth forms have their own `toAuthResult` shaped to `AuthResult`; this is
 * the general reader the profile views share.
 */

/** One structural rule failure carried in a 422 problem body's `violations`. */
export interface ProblemViolation {
  rule: string;
  ids: string[];
  message: string;
}

export interface ProblemInfo {
  message: string;
  fields?: Record<string, string>;
  violations: ProblemViolation[];
}

interface ProblemBody {
  title?: unknown;
  detail?: unknown;
  fields?: unknown;
  violations?: unknown;
}

export const PROBLEM_FALLBACK_MESSAGE = "Something went wrong. Please try again.";

export function extractProblem(error: unknown, fallback = PROBLEM_FALLBACK_MESSAGE): ProblemInfo {
  const body = (error ?? {}) as ProblemBody;
  const detail = typeof body.detail === "string" ? body.detail : undefined;
  const title = typeof body.title === "string" ? body.title : undefined;
  return {
    message: detail ?? title ?? fallback,
    fields: isStringRecord(body.fields) ? body.fields : undefined,
    violations: parseViolations(body.violations),
  };
}

function isStringRecord(value: unknown): value is Record<string, string> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.values(value).every((entry) => typeof entry === "string")
  );
}

function parseViolations(value: unknown): ProblemViolation[] {
  if (!Array.isArray(value)) return [];
  return value.reduce<ProblemViolation[]>((acc, entry) => {
    if (
      typeof entry === "object" &&
      entry !== null &&
      typeof (entry as ProblemViolation).rule === "string"
    ) {
      const violation = entry as ProblemViolation;
      acc.push({
        rule: violation.rule,
        ids: Array.isArray(violation.ids) ? violation.ids.map(String) : [],
        message: typeof violation.message === "string" ? violation.message : "",
      });
    }
    return acc;
  }, []);
}
