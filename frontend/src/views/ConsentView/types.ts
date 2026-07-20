/**
 * Consent state as a discriminated union on `phase`, so impossible combinations
 * (a `ready` card with no agent, an `error` with no message) are unrepresentable
 * rather than merely render-guarded. Mirrors T3's `useAuthSession` `{status,user}`
 * precedent.
 *
 * `loading`             the parked request's context is being fetched.
 * `ready` / `deciding`  the card is shown; `deciding` disables the actions while
 *                       a decision is in flight.
 * `error`               the request is missing/invalid/expired, or a decision failed.
 */
export type ConsentState =
  | { phase: "loading" }
  | { phase: "ready" | "deciding"; agentName: string }
  | { phase: "error"; message: string };

export interface ConsentActions {
  /** Approve the connection: mint the agent a code and return control to it. */
  approve: () => void;
  /** Deny the connection: issue nothing and return control to the agent. */
  deny: () => void;
}

export interface UseConsentParams {
  /**
   * Navigate the browser to the agent's redirect URL after a decision. Injected
   * so the browser-boundary navigation stays out of the hook and is assertable.
   */
  redirect: (url: string) => void;
}

export interface ConsentCardProps {
  agentName: string;
  userEmail: string;
  /** Disables both actions while a decision is in flight. */
  isDeciding: boolean;
  onApprove: () => void;
  onDeny: () => void;
}

export interface ConsentErrorProps {
  message: string;
}
