import { useAuth } from "@/auth";

import { ActivityFeed } from "./components/ActivityFeed";

/**
 * Protected Home: the authenticated landing surface. Hosts the live activity feed
 * that updates as the human and their agents write. Later slices add the
 * recent-worklog and resumes cards alongside it.
 */
export function HomeView() {
  const { user } = useAuth();

  return (
    <section className="mx-auto flex w-full max-w-[860px] flex-col gap-6 p-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Home</h1>
        <p className="text-muted-foreground">
          {user ? `Signed in as ${user.email}.` : "Signed in."}
        </p>
      </header>
      <ActivityFeed />
    </section>
  );
}
