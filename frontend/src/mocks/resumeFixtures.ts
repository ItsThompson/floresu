import type { components } from "@/api";

type ResumeSummary = components["schemas"]["ResumeSummary"];
type ResumeRecord = components["schemas"]["ResumeRecord"];
type ResumeSection = components["schemas"]["ResumeSection"];
type LibraryRefItem = components["schemas"]["LibraryRefItem"];
type LocalItem = components["schemas"]["LocalItem"];
type BulletpointRecord = components["schemas"]["BulletpointRecord"];
type TemplateInfo = components["schemas"]["TemplateInfo"];
type IdentityVariant = components["schemas"]["IdentityVariantRead"];

/** Build a resume list-projection fixture (no document). Defaults to a living draft. */
export function buildResumeSummary(overrides?: Partial<ResumeSummary>): ResumeSummary {
  return {
    id: 1,
    kind: "living",
    status: "draft",
    title: "Backend Engineer",
    revision: 1,
    schema_version: 1,
    job_application_id: null,
    forked_from_resume_id: null,
    archived_at: null,
    updated_at: "2026-07-20T12:00:00Z",
    ...overrides,
  };
}

/** Build a library_ref item that resolves to a canonical bullet by id. */
export function buildLibraryRefItem(overrides?: Partial<LibraryRefItem>): LibraryRefItem {
  return { id: "item-ref-1", kind: "library_ref", bullet_id: 100, ...overrides };
}

/** Build a resume-local item (an inline bullet or a copy-on-write fork). */
export function buildLocalItem(overrides?: Partial<LocalItem>): LocalItem {
  return { id: "item-local-1", kind: "local", text: "A local inline bullet.", ...overrides };
}

/** Build one resume section with an explicit item order and id-keyed items map. */
export function buildSection(overrides?: Partial<ResumeSection>): ResumeSection {
  const item = buildLibraryRefItem();
  return {
    id: "sec-work",
    kind: "work",
    title: "Work Experience",
    item_order: [item.id],
    items: { [item.id]: item },
    ...overrides,
  };
}

/** Build a full resume record with its authoritative document. Defaults to a living draft. */
export function buildResumeRecord(overrides?: Partial<ResumeRecord>): ResumeRecord {
  return {
    id: 1,
    kind: "living",
    status: "draft",
    title: "Backend Engineer",
    revision: 1,
    schema_version: 1,
    job_application_id: null,
    forked_from_resume_id: null,
    archived_at: null,
    updated_at: "2026-07-20T12:00:00Z",
    document: {
      schema_version: 1,
      template_id: "classic",
      header: {},
      sections: [buildSection()],
    },
    ...overrides,
  };
}

/** Build a canonical bulletpoint fixture with a usage count that drives the scope prompt. */
export function buildBulletpoint(overrides?: Partial<BulletpointRecord>): BulletpointRecord {
  return {
    id: 100,
    text: "Cut checkout latency by 40%.",
    source_ids: [],
    worklog_ids: [],
    used_in_count: 1,
    revision: 1,
    archived_at: null,
    ...overrides,
  };
}

/** Build a template-registry entry. Defaults to the single P0 template. */
export function buildTemplate(overrides?: Partial<TemplateInfo>): TemplateInfo {
  return { id: "classic", name: "Classic", description: "A clean single-page template.", ...overrides };
}

/** Build an identity-variant fixture for the resume header selector. */
export function buildVariant(overrides?: Partial<IdentityVariant>): IdentityVariant {
  return {
    id: 5,
    label: "Personal",
    full_name: "Tay Example",
    contact: {},
    links: [],
    is_default: true,
    archived_at: null,
    ...overrides,
  };
}
