import { useAuth } from "@/auth";

/**
 * Protected Home placeholder: the authenticated landing surface the walking
 * skeleton routes to after sign-in. Later slices replace the placeholder with
 * the recent-worklog and resumes cards and the live activity feed.
 */
export function HomeView() {
  const { user } = useAuth();

  return (
    <section className="mx-auto flex w-full max-w-[860px] flex-col gap-4 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Home</h1>
      <p className="text-muted-foreground">
        {user ? `Signed in as ${user.email}.` : "Signed in."} Your worklog, profile, library, and
        resumes will appear here.
      </p>
    </section>
  );
}
