/** Submit lifecycle for an auth form; `error` carries the message + field map. */
export type SubmitStatus =
  | { phase: "idle" }
  | { phase: "submitting" }
  | { phase: "error"; message: string; fields: Record<string, string> };

/** Which form the AuthView renders; also selects its copy and toggle target. */
export type AuthMode = "login" | "register";
