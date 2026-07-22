import type { components } from "@/api";

type JobApplicationSummary = components["schemas"]["JobApplicationSummary"];

/**
 * A job application summary factory for tests. Produces a valid `added`
 * application with no linked resume by default; overrides tailor each case
 * (see "Test Fixtures: Factories Over Inline Objects").
 */
export function buildJobApplicationSummary(
  overrides?: Partial<JobApplicationSummary>,
): JobApplicationSummary {
  return {
    id: 1,
    company: "Acme Corp",
    role_title: "Senior Backend Engineer",
    status: "added",
    linked_resume_id: null,
    created_at: "2026-07-18T09:30:00Z",
    updated_at: "2026-07-18T09:30:00Z",
    ...overrides,
  };
}
