import { Bot, FileText, Library, PenLine, User } from "lucide-react";

import type { DualModeTrackData, FaqItemData, HowItWorksStepData } from "./types";

/** Every string a visitor reads on the public page. Editing copy stops here. */

/** The lowercase serif wordmark: the one place the brand signs its name. */
export const WORDMARK = "floresu";

/** The hero headline, and the footer tagline: one string, stated once. */
export const HERO_HEADLINE = "Every win, worth keeping.";

export const HERO_SUBHEAD =
  "Floresu is a career tracker that keeps a living record of your work, so every resume you send is built from what you actually did.";

/** Shared by the header, the hero, and the closing band: one primary action. */
export const START_LABEL = "Get started";

/** The header's action once a session exists: re-entry, not signup. */
export const HEADER_SIGNED_IN_LABEL = "Open Floresu";

export const HERO_SECONDARY_LABEL = "See how it works";

/** The hero's secondary control is a real anchor, so the target needs an id. */
export const HOW_IT_WORKS_ID = "how-it-works";

export const HOW_IT_WORKS_HEADING = "How it works";

export const HOW_IT_WORKS_STEPS: HowItWorksStepData[] = [
  {
    icon: PenLine,
    title: "Log it while it is fresh",
    body: "Add an entry the moment something goes well: a feature you shipped, a problem you solved, a talk you gave.",
  },
  {
    icon: Library,
    title: "Watch your record grow",
    body: "Your entries become a searchable library of framings you can reuse, so you never write the same win twice.",
  },
  {
    icon: FileText,
    title: "Assemble a resume per role",
    body: "Pull the framings that fit the job into a targeted resume, by hand or through your agent, and export a clean PDF.",
  },
];

/** The bloom block carries this line and nothing else: a headline, never a paragraph. */
export const VALUE_HEADLINE = "Your career, ready for the tools you already work with.";

/** The supporting sentence sits beside the bloom fill, in ink on paper. */
export const VALUE_SUPPORT =
  "Connect the agent you already use over MCP. Floresu keeps the record; your agent reads it, searches it, and drafts from it.";

export const DUAL_MODE_HEADING = "Two ways to write it, one record";

export const DUAL_MODE_NOTE =
  "Floresu runs no AI of its own. It writes nothing for you and reads no uploaded resumes. Your agent does the reasoning; Floresu owns the structured record, the search, and the output.";

export const DUAL_MODE_TRACKS: DualModeTrackData[] = [
  {
    icon: User,
    heading: "You write",
    body: "Log entries, refine your framings, and build resumes in the web app. Everything here works on its own.",
  },
  {
    icon: Bot,
    heading: "Or your agent writes",
    body: "Give your own agent access over MCP and it can log, search, and assemble against the same record you see.",
  },
];

export const DUAL_MODE_FOOTNOTE =
  "The agent connection is a power-up, not a gate. The web app is complete without it.";

export const FAQ_HEADING = "Questions";

export const FAQ_ITEMS: FaqItemData[] = [
  {
    question: "Do I need an AI agent?",
    answer:
      "No. Log your work, keep your library, and build resumes by hand. Connecting an agent adds speed, never access.",
  },
  {
    question: "Does Floresu write my resume for me?",
    answer:
      "No. Your own agent drafts against your record over MCP, and you keep shaping it until it reads the way you want.",
  },
  {
    question: "What happens to my data?",
    answer:
      "Every change is recorded: what changed, when, and whether you or an agent did it. Removing something archives it, so nothing disappears behind your back, and only you can delete it for good.",
  },
  {
    question: "Is the exported resume safe for applicant tracking systems?",
    answer:
      "Yes, by construction. Real selectable text, a logical reading order, standard fonts, and a structure that survives a single-column read. Nothing important hides inside an image.",
  },
  {
    question: "Can I keep more than one resume?",
    answer:
      "Yes. Keep an evergreen resume for each direction you are aiming at, then fork a frozen copy per application, so what you sent can never drift.",
  },
];

export const FINAL_CTA_HEADLINE = "Start the record today.";

export const FINAL_CTA_BODY = "One entry is enough to begin. Your future self takes it from there.";
