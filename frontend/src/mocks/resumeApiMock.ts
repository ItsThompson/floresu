import { http, HttpResponse } from "msw";

import type { components } from "@/api";

import { buildBulletpoint, buildResumeRecord, buildTemplate } from "./resumeFixtures";

type ResumeRecord = components["schemas"]["ResumeRecord"];
type ResumeSummary = components["schemas"]["ResumeSummary"];
type ResumeSection = components["schemas"]["ResumeSection"];
type ResumeItem = components["schemas"]["LibraryRefItem"] | components["schemas"]["LocalItem"];
type BulletpointRecord = components["schemas"]["BulletpointRecord"];
type TemplateInfo = components["schemas"]["TemplateInfo"];

interface ResumeApiSeed {
  resumes?: ResumeRecord[];
  bullets?: BulletpointRecord[];
  templates?: TemplateInfo[];
  variants?: components["schemas"]["IdentityVariantRead"][];
}

/**
 * A stateful in-memory implementation of the resume backend (T12 core, T13
 * copy-on-write, T14 rendering) as MSW handlers. It mirrors the real contract:
 * `If-Match` guards a write and a mismatch is a recoverable 409, item add/remove
 * reindex the shared bullet count, and `bullet-edit` runs the scope resolution
 * that drives the prompt. Tests seed it and register `handlers`, so the views
 * exercise real flows against realistic responses (mock by identity, not order).
 */
export function createResumeApiMock(seed: ResumeApiSeed = {}) {
  const resumes = new Map<number, ResumeRecord>(
    (seed.resumes ?? [buildResumeRecord()]).map((resume) => [resume.id, clone(resume)]),
  );
  const bullets = new Map<number, BulletpointRecord>(
    (seed.bullets ?? [buildBulletpoint()]).map((bullet) => [bullet.id, clone(bullet)]),
  );
  const templates = seed.templates ?? [buildTemplate()];
  let itemCounter = 1000;
  let resumeCounter = Math.max(0, ...resumes.keys());

  const summaryOf = (record: ResumeRecord): ResumeSummary => {
    const { document: _document, ...summary } = record;
    return summary;
  };

  const conflict = () =>
    HttpResponse.json(
      { title: "Conflict", detail: "This resume changed since you loaded it. Re-read and retry." },
      { status: 409 },
    );

  const requireResume = (id: number): ResumeRecord | null => resumes.get(id) ?? null;

  const commit = (record: ResumeRecord): ResumeRecord => {
    record.revision += 1;
    record.updated_at = new Date().toISOString();
    resumes.set(record.id, record);
    return record;
  };

  const ifMatch = (request: Request): number | null => {
    const header = request.headers.get("If-Match");
    return header === null ? null : Number(header);
  };

  const handlers = [
    http.get("*/resumes/templates", () => HttpResponse.json(templates)),

    http.get("*/identity-variants", () => HttpResponse.json(seed.variants ?? [])),

    http.post("*/resumes/bullet-edit", async ({ request }) => {
      const body = (await request.json()) as components["schemas"]["ScopeEditRequest"];
      const bullet = bullets.get(body.bullet_id);
      if (!bullet) return HttpResponse.json({ detail: "Bullet not found." }, { status: 404 });

      const scope = body.scope ?? (bullet.used_in_count >= 2 ? null : "everywhere");
      if (scope === null) {
        return HttpResponse.json({
          outcome: "prompt",
          bullet_id: bullet.id,
          used_in_count: bullet.used_in_count,
        });
      }

      if (scope === "everywhere") {
        if (
          body.if_match_bullet_revision != null &&
          body.if_match_bullet_revision !== bullet.revision
        ) {
          return conflict();
        }
        bullet.text = body.new_text;
        bullet.revision += 1;
        bullets.set(bullet.id, bullet);
        return HttpResponse.json({ outcome: "edited_everywhere", bullet: clone(bullet) });
      }

      // this_resume: fork a local copy in the resume and drop the shared reference.
      const record = body.resume_id == null ? null : requireResume(body.resume_id);
      if (!record) return HttpResponse.json({ detail: "Resume not found." }, { status: 404 });
      if (
        body.if_match_resume_revision != null &&
        body.if_match_resume_revision !== record.revision
      ) {
        return conflict();
      }
      forkReferenceToLocal(record, bullet.id, body.new_text, () => `item-${(itemCounter += 1)}`);
      bullet.used_in_count = Math.max(0, bullet.used_in_count - 1);
      bullets.set(bullet.id, bullet);
      return HttpResponse.json({ outcome: "forked_this_resume", resume: clone(commit(record)) });
    }),

    http.get("*/bullets", () => HttpResponse.json([...bullets.values()].map(clone))),

    http.post("*/resumes/:resumeId/preview", () =>
      HttpResponse.arrayBuffer(PDF_BYTES.buffer as ArrayBuffer, {
        headers: { "Content-Type": "application/pdf" },
      }),
    ),

    http.post("*/resumes/:resumeId/export", ({ params }) => {
      const record = requireResume(Number(params.resumeId));
      if (!record) return HttpResponse.json({ detail: "Resume not found." }, { status: 404 });
      return HttpResponse.json({
        resume_id: record.id,
        revision: record.revision,
        object_key: `u/1/r/${record.id}/rev/${record.revision}.pdf`,
        download_url: `https://r2.example/${record.id}-${record.revision}.pdf`,
      });
    }),

    http.post("*/resumes/:resumeId/finalize", ({ params }) => {
      const record = requireResume(Number(params.resumeId));
      if (!record) return HttpResponse.json({ detail: "Resume not found." }, { status: 404 });
      if (record.kind !== "application") {
        return HttpResponse.json(
          { title: "Conflict", detail: "Only application resumes can be finalized." },
          { status: 409 },
        );
      }
      freezeReferences(record, bullets);
      record.status = "finalized";
      commit(record);
      return HttpResponse.json({
        resume_id: record.id,
        status: "finalized",
        pdf_object_key: `u/1/r/${record.id}/rev/${record.revision}.pdf`,
        revision_no: record.revision,
      });
    }),

    http.post("*/resumes/:resumeId/items/:itemId/remove", ({ params, request }) => {
      const record = requireResume(Number(params.resumeId));
      if (!record) return HttpResponse.json({ detail: "Resume not found." }, { status: 404 });
      if (ifMatch(request) !== record.revision) return conflict();
      removeItem(record, String(params.itemId), bullets);
      return HttpResponse.json(clone(commit(record)));
    }),

    http.post("*/resumes/:resumeId/items/:itemId/promote", ({ params, request }) => {
      const record = requireResume(Number(params.resumeId));
      if (!record) return HttpResponse.json({ detail: "Resume not found." }, { status: 404 });
      if (ifMatch(request) !== record.revision) return conflict();
      return HttpResponse.json(clone(commit(record)));
    }),

    http.post("*/resumes/:resumeId/items", async ({ params, request }) => {
      const record = requireResume(Number(params.resumeId));
      if (!record) return HttpResponse.json({ detail: "Resume not found." }, { status: 404 });
      if (ifMatch(request) !== record.revision) return conflict();
      const body = (await request.json()) as components["schemas"]["AddItemRequest"];
      addItem(record, body, `item-${(itemCounter += 1)}`, bullets);
      return HttpResponse.json(clone(commit(record)));
    }),

    http.post("*/resumes/:resumeId/reorder", async ({ params, request }) => {
      const record = requireResume(Number(params.resumeId));
      if (!record) return HttpResponse.json({ detail: "Resume not found." }, { status: 404 });
      if (ifMatch(request) !== record.revision) return conflict();
      const body = (await request.json()) as components["schemas"]["ResumeReorderRequest"];
      applyReorder(record, body);
      return HttpResponse.json(clone(commit(record)));
    }),

    http.get("*/resumes/:resumeId", ({ params }) => {
      const record = requireResume(Number(params.resumeId));
      if (!record) return HttpResponse.json({ detail: "Resume not found." }, { status: 404 });
      return HttpResponse.json(clone(record));
    }),

    http.put("*/resumes/:resumeId", async ({ params, request }) => {
      const record = requireResume(Number(params.resumeId));
      if (!record) return HttpResponse.json({ detail: "Resume not found." }, { status: 404 });
      if (ifMatch(request) !== record.revision) return conflict();
      const body = (await request.json()) as components["schemas"]["ResumeUpdate"];
      record.title = body.title;
      record.document = {
        ...record.document,
        template_id: body.template_id,
        header: body.header ?? record.document.header,
        sections: body.sections ?? record.document.sections,
      };
      return HttpResponse.json(clone(commit(record)));
    }),

    http.delete("*/resumes/:resumeId", ({ params, request }) => {
      const id = Number(params.resumeId);
      const confirmed = new URL(request.url).searchParams.get("confirm") === "true";
      if (!confirmed)
        return HttpResponse.json({ detail: "Confirmation required." }, { status: 422 });
      resumes.delete(id);
      return HttpResponse.json({ entity_type: "resume", entity_id: id, embedding_purged: false });
    }),

    http.get("*/resumes", ({ request }) => {
      const kind = new URL(request.url).searchParams.get("kind");
      const list = [...resumes.values()]
        .filter((record) => (kind ? record.kind === kind : true))
        .map(summaryOf);
      return HttpResponse.json(list);
    }),

    http.post("*/resumes", async ({ request }) => {
      const body = (await request.json()) as components["schemas"]["ResumeCreateRequest"];
      const id = (resumeCounter += 1);
      const created = buildResumeRecord({
        id,
        kind: body.kind,
        status: "draft",
        title: body.title ?? "Untitled resume",
        revision: 1,
        job_application_id: body.job_application_id ?? null,
        document: {
          schema_version: 1,
          template_id: body.template_id ?? "classic",
          header: {},
          sections: [],
        },
      });
      resumes.set(id, created);
      return HttpResponse.json(clone(created), { status: 201 });
    }),
  ];

  return { handlers, resumes, bullets };
}

/** Deep clone via structured JSON so a handler never hands out a live reference. */
function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function findSection(record: ResumeRecord, sectionId: string): ResumeSection | undefined {
  return record.document.sections?.find((section) => section.id === sectionId);
}

function addItem(
  record: ResumeRecord,
  body: components["schemas"]["AddItemRequest"],
  itemId: string,
  bullets: Map<number, BulletpointRecord>,
): void {
  const section = findSection(record, body.section_id);
  if (!section) return;
  const item: ResumeItem =
    body.item.kind === "library_ref"
      ? { id: itemId, kind: "library_ref", bullet_id: body.item.bullet_id }
      : {
          id: itemId,
          kind: "local",
          text: body.item.text,
          source_refs: body.item.source_refs ?? undefined,
        };
  section.items = { ...section.items, [itemId]: item };
  section.item_order = [...(section.item_order ?? []), itemId];
  if (item.kind === "library_ref") {
    const bullet = bullets.get(item.bullet_id);
    if (bullet) bullet.used_in_count += 1;
  }
}

function removeItem(
  record: ResumeRecord,
  itemId: string,
  bullets: Map<number, BulletpointRecord>,
): void {
  for (const section of record.document.sections ?? []) {
    const item = section.items?.[itemId];
    if (!item) continue;
    if (item.kind === "library_ref") {
      const bullet = bullets.get(item.bullet_id);
      if (bullet) bullet.used_in_count = Math.max(0, bullet.used_in_count - 1);
    }
    const { [itemId]: _removed, ...rest } = section.items ?? {};
    section.items = rest;
    section.item_order = (section.item_order ?? []).filter((id) => id !== itemId);
  }
}

function forkReferenceToLocal(
  record: ResumeRecord,
  bulletId: number,
  newText: string,
  mintId: () => string,
): void {
  for (const section of record.document.sections ?? []) {
    for (const [id, item] of Object.entries(section.items ?? {})) {
      if (item.kind === "library_ref" && item.bullet_id === bulletId) {
        section.items = {
          ...section.items,
          [id]: { id, kind: "local", text: newText, forked_from_bullet_id: bulletId },
        };
      }
    }
  }
  void mintId;
}

/**
 * Finalize's freeze: every library reference is resolved to inline read-only
 * text (retaining `forked_from_bullet_id`) and stops counting toward its bullet's
 * "used in N", mirroring the backend dropping the resume's bullet refs.
 */
function freezeReferences(record: ResumeRecord, bullets: Map<number, BulletpointRecord>): void {
  for (const section of record.document.sections ?? []) {
    for (const [id, item] of Object.entries(section.items ?? {})) {
      if (item.kind !== "library_ref") continue;
      const bullet = bullets.get(item.bullet_id);
      section.items = {
        ...section.items,
        [id]: {
          id,
          kind: "local",
          text: bullet?.text ?? "",
          forked_from_bullet_id: item.bullet_id,
        },
      };
      if (bullet) {
        bullet.used_in_count = Math.max(0, bullet.used_in_count - 1);
        bullets.set(bullet.id, bullet);
      }
    }
  }
}

function applyReorder(
  record: ResumeRecord,
  body: components["schemas"]["ResumeReorderRequest"],
): void {
  const sections = record.document.sections ?? [];
  if (body.section_order) {
    sections.sort((a, b) => body.section_order!.indexOf(a.id) - body.section_order!.indexOf(b.id));
  }
  for (const [sectionId, order] of Object.entries(body.item_orders ?? {})) {
    const section = findSection(record, sectionId);
    if (section) section.item_order = order;
  }
}

// A tiny valid one-page PDF, enough for the preview fetch to return real bytes.
const PDF_BYTES = new TextEncoder().encode(
  "%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF",
);
