import { execFileSync } from "node:child_process";

import { expect, type Page, type APIRequestContext } from "@playwright/test";

/** A password that satisfies the backend strength rule (upper + lower + digit, >= 8). */
export const PASSWORD = "Str0ngPassw0rd";

let counter = 0;

/**
 * A unique, syntactically-valid email. The backend rejects reserved TLDs
 * (`.test`, `.example`), so use a normal-looking domain.
 */
export function uniqueEmail(prefix = "user"): string {
  counter += 1;
  return `${prefix}-${Date.now()}-${counter}@floresu-e2e.com`;
}

export interface Me {
  id: number;
  email: string;
  has_completed_onboarding: boolean;
}

/** Register a fresh account via the API and mark onboarding complete. */
export async function registerAndOnboard(
  page: Page,
  email = uniqueEmail(),
): Promise<{ email: string; password: string }> {
  const registered = await page.request.post("/auth/register", {
    data: { email, password: PASSWORD },
  });
  expect(registered.ok(), await bodyText(registered)).toBeTruthy();
  const onboarded = await page.request.post("/me/onboarding");
  expect(onboarded.ok(), await bodyText(onboarded)).toBeTruthy();
  return { email, password: PASSWORD };
}

/** Read the current session's account (id used for the internal-boundary tests). */
export async function getMe(request: APIRequestContext): Promise<Me> {
  const response = await request.get("/me");
  expect(response.ok(), await bodyText(response)).toBeTruthy();
  return (await response.json()) as Me;
}

/** Create a role source through the API; returns its id and display label. */
export async function createRole(
  request: APIRequestContext,
  company: string,
  jobTitle: string,
): Promise<{ id: number; label: string }> {
  const response = await request.post("/sources", {
    data: {
      kind: "role",
      display_label: `${company} — ${jobTitle}`,
      company,
      job_title: jobTitle,
      title_aliases: [],
      location: null,
      date_start: null,
      date_end: null,
      summary: null,
    },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
  const id = ((await response.json()) as { id: number }).id;
  return { id, label: `${company} — ${jobTitle}` };
}

/** Create a worklog entry through the API; returns its id. */
export async function createWorklog(
  request: APIRequestContext,
  entry: { title: string; entryDate: string; description?: string; sourceIds?: number[] },
): Promise<{ id: number }> {
  const response = await request.post("/worklog", {
    data: {
      title: entry.title,
      entry_date: entry.entryDate,
      description: entry.description ?? null,
      tags: [],
      source_ids: entry.sourceIds ?? [],
    },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
  return (await response.json()) as { id: number };
}

/** Create a library bullet through the API, optionally linked to sources/worklog entries. */
export async function createBullet(
  request: APIRequestContext,
  text: string,
  links: { sourceIds?: number[]; worklogIds?: number[] } = {},
): Promise<{ id: number }> {
  const response = await request.post("/bullets", {
    data: { text, source_ids: links.sourceIds ?? [], worklog_ids: links.worklogIds ?? [] },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
  return (await response.json()) as { id: number };
}

/** Create a living resume through the API; returns its id. */
export async function createLivingResume(
  request: APIRequestContext,
  title: string,
): Promise<number> {
  const response = await request.post("/resumes", {
    data: { kind: "living", title, source: { mode: "blank" } },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
  return ((await response.json()) as { id: number }).id;
}

/**
 * Seed an empty section onto a resume via the full-document PUT (the shape the
 * agent would write over MCP). The web editor can pull bullets into a section but
 * has no add-section control, so tests that exercise the human assemble flow seed
 * the section first, then place bullets through the item endpoint (or the UI).
 */
export async function seedResumeSection(
  request: APIRequestContext,
  resumeId: number,
  options: { title?: string; sectionId?: string } = {},
): Promise<{ sectionId: string }> {
  const current = await request.get(`/resumes/${resumeId}`);
  expect(current.ok(), await bodyText(current)).toBeTruthy();
  const record = (await current.json()) as {
    revision: number;
    title: string;
    document: { template_id: string };
  };
  const sectionId = options.sectionId ?? "sec-experience";
  const section = {
    id: sectionId,
    kind: "work",
    title: options.title ?? "Experience",
    item_order: [],
    items: {},
  };
  const updated = await request.put(`/resumes/${resumeId}`, {
    headers: { "If-Match": String(record.revision) },
    data: { title: record.title, template_id: record.document.template_id, sections: [section] },
  });
  expect(updated.ok(), await bodyText(updated)).toBeTruthy();
  return { sectionId };
}

/**
 * Place a canonical bullet into a resume section via the item endpoint (the path
 * the editor's "pull from library" uses), so the resume-reference count that
 * drives the copy-on-write scope prompt is maintained.
 */
export async function placeBulletViaApi(
  request: APIRequestContext,
  resumeId: number,
  sectionId: string,
  bulletId: number,
): Promise<void> {
  const current = await request.get(`/resumes/${resumeId}`);
  expect(current.ok(), await bodyText(current)).toBeTruthy();
  const revision = ((await current.json()) as { revision: number }).revision;
  const response = await request.post(`/resumes/${resumeId}/items`, {
    headers: { "If-Match": String(revision) },
    data: { section_id: sectionId, item: { kind: "library_ref", bullet_id: bulletId } },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
}

/** Update a library bullet's text through the API (the "later edit" probe). */
export async function updateBullet(
  request: APIRequestContext,
  bulletId: number,
  text: string,
): Promise<void> {
  const response = await request.put(`/bullets/${bulletId}`, {
    data: { text, source_ids: [], worklog_ids: [] },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
}

/**
 * Assert a PDF byte buffer has selectable text containing `expected`. Uses
 * `pdftotext` (poppler); the CI job installs poppler-utils so this always runs.
 */
export function assertPdfSelectableText(pdf: Buffer, expected: string): void {
  expect(pdf.subarray(0, 5).toString("ascii")).toBe("%PDF-");
  const text = execFileSync("pdftotext", ["-", "-"], { input: pdf }).toString("utf8");
  expect(text).toContain(expected);
}

/** Best-effort response body text for assertion messages. */
export async function bodyText(response: { text: () => Promise<string> }): Promise<string> {
  try {
    return await response.text();
  } catch {
    return "<no body>";
  }
}
