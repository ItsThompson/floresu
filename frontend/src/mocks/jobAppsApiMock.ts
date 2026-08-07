import { http, HttpResponse } from "msw";

import type { components } from "@/api";

import { createResumeApiMock } from "./resumeApiMock";
import { buildJobApplicationSummary } from "./jobAppsFixtures";

type JobApplicationSummary = components["schemas"]["JobApplicationSummary"];
type JobApplicationStatus = components["schemas"]["JobApplicationStatus"];
type ResumeRecord = components["schemas"]["ResumeRecord"];
type BulletpointRecord = components["schemas"]["BulletpointRecord"];

interface JobAppsApiSeed {
  applications?: JobApplicationSummary[];
  resumes?: ResumeRecord[];
  bullets?: BulletpointRecord[];
}

/**
 * A stateful in-memory implementation of the job-application + resume backend as
 * MSW handlers. It composes the resume mock in `resumeApiMock.ts` so the two share
 * one resume store: forking with a `job_application_id` links a resume to its
 * application, `GET /job-applications` resolves `linked_resume_id` off that link,
 * and marking an application `submitted` finalizes the linked resume (or is
 * rejected 409 when none is linked, leaving the status `added`). Tests seed it and
 * register `handlers` (mock by identity, not order).
 */
export function createJobAppsApiMock(seed: JobAppsApiSeed = {}) {
  const resumeMock = createResumeApiMock({ resumes: seed.resumes, bullets: seed.bullets });
  const applications = new Map<number, JobApplicationSummary>(
    (seed.applications ?? []).map((application) => [application.id, { ...application }]),
  );
  let applicationCounter = Math.max(0, ...applications.keys());

  /** Resolve the 1:1 linked resume id off `resumes.job_application_id`. */
  const linkedResumeId = (applicationId: number): number | null => {
    for (const resume of resumeMock.resumes.values()) {
      if (resume.job_application_id === applicationId) return resume.id;
    }
    return null;
  };

  const summaryOf = (application: JobApplicationSummary): JobApplicationSummary => ({
    ...application,
    linked_resume_id: linkedResumeId(application.id),
  });

  const requireApplication = (id: number): JobApplicationSummary | null =>
    applications.get(id) ?? null;

  const jobAppHandlers = [
    http.get("*/job-applications", () =>
      HttpResponse.json([...applications.values()].map(summaryOf)),
    ),

    http.post("*/job-applications", async ({ request }) => {
      const body = (await request.json()) as components["schemas"]["JobApplicationCreate"];
      const id = (applicationCounter += 1);
      const now = new Date().toISOString();
      const created = buildJobApplicationSummary({
        id,
        company: body.company,
        role_title: body.role_title,
        status: "added",
        linked_resume_id: null,
        created_at: now,
        updated_at: now,
      });
      applications.set(id, created);
      return HttpResponse.json(summaryOf(created), { status: 201 });
    }),

    http.get("*/job-applications/:applicationId", ({ params }) => {
      const application = requireApplication(Number(params.applicationId));
      if (!application) return HttpResponse.json({ detail: "Not found." }, { status: 404 });
      return HttpResponse.json(summaryOf(application));
    }),

    http.patch("*/job-applications/:applicationId", async ({ params, request }) => {
      const application = requireApplication(Number(params.applicationId));
      if (!application) return HttpResponse.json({ detail: "Not found." }, { status: 404 });
      const body = (await request.json()) as components["schemas"]["JobApplicationUpdate"];

      if (typeof body.company === "string") application.company = body.company;
      if (typeof body.role_title === "string") application.role_title = body.role_title;

      if (body.status === "submitted") {
        const resumeId = linkedResumeId(application.id);
        if (resumeId === null) {
          return HttpResponse.json(
            {
              title: "Conflict",
              detail: "Link a resume to this application before marking it submitted.",
            },
            { status: 409 },
          );
        }
        const linked = resumeMock.resumes.get(resumeId);
        if (linked) {
          linked.status = "finalized";
          linked.revision += 1;
          resumeMock.resumes.set(linked.id, linked);
        }
        application.status = "submitted" satisfies JobApplicationStatus;
      }

      application.updated_at = new Date().toISOString();
      applications.set(application.id, application);
      return HttpResponse.json(summaryOf(application));
    }),
  ];

  return {
    handlers: [...jobAppHandlers, ...resumeMock.handlers],
    applications,
    resumes: resumeMock.resumes,
  };
}
