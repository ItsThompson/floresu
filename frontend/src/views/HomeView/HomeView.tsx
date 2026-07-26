import { useAuth } from "@/auth";

import { ActivityFeed } from "./components/ActivityFeed";
import { MyResumesSection } from "./components/MyResumesSection";
import { RecentWorklogSection } from "./components/RecentWorklogSection";
import { useHomeData } from "./hooks/useHomeData";

/**
 * Protected Home: the authenticated landing surface. Renders three regions: a
 * recent-worklog preview, the account's resumes, and the live activity feed that
 * updates as the human and their agents write. The Home data hook loads the two
 * list regions independently, so one failed read never blanks the other.
 */
export function HomeView() {
  const { user } = useAuth();
  const { worklog, resumes } = useHomeData();

  return (
    <section className="mx-auto flex w-full max-w-[860px] flex-col gap-6 p-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Home</h1>
        <p className="text-muted-foreground">
          {user ? `Signed in as ${user.email}.` : "Signed in."}
        </p>
      </header>
      <RecentWorklogSection section={worklog} />
      <MyResumesSection section={resumes} />
      <ActivityFeed />
    </section>
  );
}
