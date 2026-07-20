/**
 * Consent-screen copy. The request lifecycle is server-side and one-time (the AS
 * consumes the parked request on any decision), so both failure paths tell the
 * human to restart the connection from their agent rather than offering a retry
 * that cannot succeed.
 */

/** Shown when the `auth_request_id` is missing, invalid, or expired. */
export const INVALID_REQUEST_MESSAGE =
  "This connection request is no longer valid. Ask your agent to start connecting again.";

/** Shown when recording the approve/deny decision fails. */
export const DECISION_FAILED_MESSAGE =
  "We couldn't record your decision. Ask your agent to start connecting again.";
