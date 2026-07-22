import { useCallback, useEffect, useState } from "react";

import type { SessionClient } from "@/api";

import { toAuthResult } from "./api-errors";
import type { AuthResult, AuthStatus, AuthUser, LoginInput, RegisterInput } from "./types";

interface SessionState {
  status: AuthStatus;
  user: AuthUser | null;
}

const ANONYMOUS: SessionState = { status: "anonymous", user: null };

export interface UseAuthSession extends SessionState {
  register: (input: RegisterInput) => Promise<AuthResult>;
  login: (input: LoginInput) => Promise<AuthResult>;
  logout: () => Promise<void>;
  completeOnboarding: () => Promise<AuthResult>;
}

/**
 * Owns the session: resumes an existing session once on mount via the rotating
 * refresh token against the shared session client, and exposes
 * register/login/logout. State is a single `{status, user}` so the impossible
 * "authenticated with no user" combination cannot arise.
 */
export function useAuthSession(client: SessionClient): UseAuthSession {
  const [session, setSession] = useState<SessionState>({ status: "loading", user: null });

  const resume = useCallback(async () => {
    try {
      const { data } = await client.POST("/auth/refresh");
      setSession(data ? { status: "authenticated", user: data } : ANONYMOUS);
    } catch {
      // No reachable backend / no session cookie: resolve to anonymous rather
      // than hang in the loading state.
      setSession(ANONYMOUS);
    }
  }, [client]);

  useEffect(() => {
    void resume();
  }, [resume]);

  const register = useCallback(
    async (input: RegisterInput): Promise<AuthResult> => {
      const { data, error } = await client.POST("/auth/register", { body: input });
      if (data) {
        setSession({ status: "authenticated", user: data });
        return { ok: true };
      }
      return toAuthResult(error);
    },
    [client],
  );

  const login = useCallback(
    async (input: LoginInput): Promise<AuthResult> => {
      const { data, error } = await client.POST("/auth/login", { body: input });
      if (data) {
        setSession({ status: "authenticated", user: data });
        return { ok: true };
      }
      return toAuthResult(error);
    },
    [client],
  );

  const logout = useCallback(async () => {
    // Best-effort server revocation: clear the local session regardless of
    // whether the logout POST succeeds, so a failed POST neither strands the user
    // authenticated nor surfaces as an unhandled rejection.
    try {
      await client.POST("/auth/logout");
    } catch {
      // Ignore: local sign-out below is the outcome that matters.
    }
    setSession(ANONYMOUS);
  }, [client]);

  const completeOnboarding = useCallback(async (): Promise<AuthResult> => {
    // Persist onboarding completion so the route guard sends the user into the
    // app and the wizard never reappears on reload (a full reload re-reads the
    // server value via resume-on-mount). On success adopt the returned user;
    // on failure keep the user in the wizard with an inline error.
    const { data, error } = await client.POST("/me/onboarding");
    if (data) {
      setSession({ status: "authenticated", user: data });
      return { ok: true };
    }
    return toAuthResult(error);
  }, [client]);

  return { ...session, register, login, logout, completeOnboarding };
}
