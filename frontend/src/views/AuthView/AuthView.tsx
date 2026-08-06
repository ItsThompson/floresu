import { Link, Navigate, useLocation } from "react-router";

import { useAuth } from "@/auth";
import { LoginForm } from "./components/LoginForm";
import { RegisterForm } from "./components/RegisterForm";
import type { AuthMode } from "./types";

interface AuthViewProps {
  mode: AuthMode;
}

/**
 * Sign-in / sign-up screen (chrome-free, mounted outside the AppShell). Once the
 * session resolves to authenticated it redirects to `from` (the location the
 * session guard bounced the user off, e.g. a deep-linked consent URL) or to the
 * app's Home at `/home`, so signing in or registering lands the user where they
 * were headed. The fallback is Home rather than `/`, which is the public page: a
 * user who just signed in belongs in the app. The mode is fixed by the route
 * (`/signin` vs `/signup`); the toggle is a real link to the other route.
 *
 * A centered card on the warm ground, in the calm register: these are the first
 * screens after the public page, so the only accent is the submit control, the
 * focus ring, and the mode-toggle link.
 */
export function AuthView({ mode }: AuthViewProps) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from ?? "/home"} replace />;
  }

  const isLogin = mode === "login";
  return (
    <main className="bg-background text-foreground flex min-h-svh items-center justify-center p-6">
      <section className="bg-card text-card-foreground border-border flex w-full max-w-[26rem] flex-col gap-6 rounded-xl border p-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          {isLogin ? "Welcome back" : "Create your account"}
        </h1>
        {isLogin ? <LoginForm /> : <RegisterForm />}
        <p className="text-muted-foreground text-sm">
          {isLogin ? "New to Floresu? " : "Already have an account? "}
          <Link
            to={isLogin ? "/signup" : "/signin"}
            className="text-primary font-medium underline-offset-4 hover:underline"
          >
            {isLogin ? "Create an account" : "Sign in"}
          </Link>
        </p>
      </section>
    </main>
  );
}
