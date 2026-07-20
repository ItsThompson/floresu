/**
 * `loading`  the parked request's context is being fetched.
 * `ready`    the context loaded; the approve/deny card is shown.
 * `deciding` a decision is in flight; the card's actions are disabled.
 * `error`    the request is missing/invalid/expired, or a decision failed.
 */
export type ConsentPhase = "loading" | "ready" | "deciding" | "error";

export interface ConsentState {
  phase: ConsentPhase;
  /** The requesting agent's display name; set once the parked request loads. */
  agentName: string | null;
  /** Human message for the `error` phase (invalid request or a failed decision). */
  error: string | null;
}

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
