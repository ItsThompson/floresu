import { expect, test } from "@playwright/test";

import { bodyText, createWorklog, registerAndOnboard } from "../harness/support";

/**
 * B5: create the three non-role source kinds through the browser. Only `role` is
 * exercised elsewhere (initialize.spec.ts); this drives project, education, and
 * certification through `/profile/sources/new?kind=<kind>`, filling each kind's
 * kind-specific fields, and proves each persists as a source of the correct kind
 * that a worklog entry can attach to. Creation is driven in the browser; the
 * persisted state and the attachment are asserted through the API.
 */
test("create project, education, and certification through the browser", async ({ page }) => {
  await registerAndOnboard(page);

  // --- Project: display label + links ---
  await page.goto("/profile/sources/new?kind=project");
  await page.getByLabel("Project name").fill("Portfolio Website");
  await page.getByLabel("Links").fill("https://portfolio.example.com, https://github.com/me/site");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/profile\/sources\/\d+$/);
  await expect(page.getByRole("heading", { name: /Portfolio Website/ })).toBeVisible();

  // --- Education: institution, degree, field ---
  await page.goto("/profile/sources/new?kind=education");
  await page.getByLabel("Title").fill("BSc Computer Science");
  await page.getByLabel("Institution").fill("State University");
  await page.getByLabel("Degree").fill("BSc");
  await page.getByLabel("Field").fill("Computer Science");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/profile\/sources\/\d+$/);
  await expect(page.getByRole("heading", { name: /BSc Computer Science/ })).toBeVisible();

  // --- Certification: issuer, credential id ---
  await page.goto("/profile/sources/new?kind=certification");
  await page.getByLabel("Name").fill("AWS Solutions Architect");
  await page.getByLabel("Issuer").fill("Amazon Web Services");
  await page.getByLabel("Credential ID").fill("AWS-SAA-1234");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/profile\/sources\/\d+$/);
  await expect(page.getByRole("heading", { name: /AWS Solutions Architect/ })).toBeVisible();

  // GET /sources returns exactly one source per created kind, each with the
  // correct discriminator (a fresh account starts with no sources).
  interface SourceSummary {
    id: number;
    kind: string;
    display_label: string;
  }
  const listResponse = await page.request.get("/sources");
  expect(listResponse.ok(), await bodyText(listResponse)).toBeTruthy();
  const summaries = (await listResponse.json()) as SourceSummary[];
  const idForKind = (kind: string): number => {
    const matches = summaries.filter((source) => source.kind === kind);
    expect(matches, `exactly one ${kind} source`).toHaveLength(1);
    return matches[0].id;
  };
  expect(summaries).toHaveLength(3);
  const projectId = idForKind("project");
  const educationId = idForKind("education");
  const certificationId = idForKind("certification");

  // The single-record read carries the typed, kind-specific detail: assert each
  // kind's fields persisted through the create form.
  const readRecord = async <Detail>(
    id: number,
  ): Promise<{ display_label: string; detail: Detail }> => {
    const response = await page.request.get(`/sources/${id}`);
    expect(response.ok(), await bodyText(response)).toBeTruthy();
    return (await response.json()) as { display_label: string; detail: Detail };
  };

  const project = await readRecord<{ links: string[] }>(projectId);
  expect(project.display_label).toBe("Portfolio Website");
  expect(project.detail.links).toEqual([
    "https://portfolio.example.com",
    "https://github.com/me/site",
  ]);

  const education = await readRecord<{ institution: string; degree: string; field: string }>(
    educationId,
  );
  expect(education.display_label).toBe("BSc Computer Science");
  expect(education.detail).toMatchObject({
    institution: "State University",
    degree: "BSc",
    field: "Computer Science",
  });

  const certification = await readRecord<{ issuer: string; credential_id: string }>(
    certificationId,
  );
  expect(certification.display_label).toBe("AWS Solutions Architect");
  expect(certification.detail).toMatchObject({
    issuer: "Amazon Web Services",
    credential_id: "AWS-SAA-1234",
  });

  // A created source is a usable source: attach a worklog entry to the project and
  // prove the linkage persisted (an API attachment check, per the cross-flow rule).
  const entry = await createWorklog(page.request, {
    title: "Redesigned the landing page",
    entryDate: "2026-04-15",
    sourceIds: [projectId],
  });
  const entryResponse = await page.request.get(`/worklog/${entry.id}`);
  expect(entryResponse.ok(), await bodyText(entryResponse)).toBeTruthy();
  const entryRecord = (await entryResponse.json()) as { source_ids: number[] };
  expect(entryRecord.source_ids).toContain(projectId);
});
