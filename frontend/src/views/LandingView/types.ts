import type { LucideIcon } from "lucide-react";

/**
 * A session that has finished resolving. `loading` is deliberately not
 * representable: `useStartDestination` gates it, so the resolver can never send a
 * returning visitor to signup while the resume probe is still in flight.
 */
export type ResolvedSession =
  { status: "anonymous" } | { status: "authenticated"; hasCompletedOnboarding: boolean };

/**
 * Where the primary call to action points once the session resolves, plus the one
 * fact the header needs to pick its label without reading the session again.
 */
export interface StartDestination {
  path: string;
  isSignedIn: boolean;
}

/** One "How it works" step: an icon, a title, and a single line. */
export interface HowItWorksStepData {
  icon: LucideIcon;
  title: string;
  body: string;
}

/** One dual-mode track: who does the writing, and what that looks like. */
export interface DualModeTrackData {
  icon: LucideIcon;
  heading: string;
  body: string;
}

/** One question with a plain-language answer. */
export interface FaqItemData {
  question: string;
  answer: string;
}
