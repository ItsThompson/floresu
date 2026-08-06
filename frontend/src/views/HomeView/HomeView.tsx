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
 *
 * A dense reading surface, so the title is grotesque and the accent is spent only
 * on the feed: the live dot, the newest row, and the cold-start actions. The page
 * gutter belongs to the app shell; this view sets the reading measure alone.
 */
export function HomeView() {
  const { user } = useAuth();
  const { worklog, resumes } = useHomeData();

  return (
    <section className="reading-width flex w-full flex-col gap-6">
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
