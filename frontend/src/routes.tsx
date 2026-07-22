import type { RouteObject } from "react-router";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/components/RequireAuth";
import { RequireOnboarded } from "@/components/RequireOnboarded";
import { AuthView } from "@/views/AuthView";
import { ConsentView } from "@/views/ConsentView";
import { HomeView } from "@/views/HomeView";
import { IdentityVariantsView } from "@/views/IdentityVariantsView";
import { LibraryView } from "@/views/LibraryView";
import { OnboardingView } from "@/views/OnboardingView";
import { ProfileHubView } from "@/views/ProfileHubView";
import { ProfileSourceDetailView } from "@/views/ProfileSourceDetailView";
import { ResumeEditorView } from "@/views/ResumeEditorView";
import { ResumesListView } from "@/views/ResumesListView";
import { settingsRoute } from "@/views/SettingsView";
import { SkillsView } from "@/views/SkillsView";
import { WorklogView } from "@/views/WorklogView";

/**
 * The application route tree. Kept separate from `App` (the provider
 * composition) so a routing-config test can assert the structural invariants:
 * that `/signin` and `/signup` live OUTSIDE `RequireAuth` (chrome-free, always
 * reachable), the wizard at `/onboarding` is guarded by the session but sits
 * OUTSIDE the app shell (chrome-free), and the in-app routes live behind BOTH
 * the session guard and the onboarding guard, without rendering the views.
 */
export const appRoutes: RouteObject[] = [
  // Chrome-free auth screens, always reachable (no session required).
  { path: "/signin", element: <AuthView mode="login" /> },
  { path: "/signup", element: <AuthView mode="register" /> },

  // Guarded: an anonymous user is redirected to /signin before anything mounts.
  {
    element: <RequireAuth />,
    children: [
      // The onboarding wizard: chrome-free, so it sits outside the app shell.
      { path: "/onboarding", element: <OnboardingView /> },

      // The OAuth consent screen: chrome-free and session-gated, but outside the
      // onboarding guard so a connect-time consent is never bounced to the
      // wizard. The AS 302s the browser here (`/authorize?auth_request_id=...`).
      { path: "/authorize", element: <ConsentView /> },

      // In-app routes: reached only once onboarding is complete; a non-onboarded
      // user is redirected to the wizard before the shell mounts.
      {
        element: <RequireOnboarded />,
        children: [
          {
            path: "/",
            element: <AppShell />,
            children: [
              { index: true, element: <HomeView /> },
              { path: "worklog", element: <WorklogView /> },
              { path: "library", element: <LibraryView /> },
              { path: "resumes", element: <ResumesListView /> },
              { path: "resumes/:resumeId", element: <ResumeEditorView /> },
              // Career Profile: hub, source detail, skills, identities.
              { path: "profile", element: <ProfileHubView /> },
              { path: "profile/skills", element: <SkillsView /> },
              { path: "profile/identities", element: <IdentityVariantsView /> },
              { path: "profile/sources/new", element: <ProfileSourceDetailView /> },
              { path: "profile/sources/:sourceId", element: <ProfileSourceDetailView /> },
              settingsRoute,
            ],
          },
        ],
      },
    ],
  },
];
