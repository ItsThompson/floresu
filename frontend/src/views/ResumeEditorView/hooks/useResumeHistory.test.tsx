import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ApiClientProvider } from "@/api";
import { buildPublishedVersion } from "@/mocks/resumeFixtures";
import { server } from "@/mocks/server";

import { useResumeHistory } from "./useResumeHistory";

// `useResumeHistory` reads the session client from context, so the only real
// boundary is the API; MSW backs the two revision routes and the hook is
// exercised through its public `list`/`open` promises.
function wrapper({ children }: { children: ReactNode }) {
  return <ApiClientProvider baseUrl="http://localhost">{children}</ApiClientProvider>;
}

function renderResumeHistory(resumeId = 1) {
  return renderHook(() => useResumeHistory(resumeId), { wrapper }).result;
}

describe("useResumeHistory", () => {
  it("lists the resume's published versions from the revisions route", async () => {
    server.use(
      http.get("*/resumes/:resumeId/revisions", ({ params }) =>
        HttpResponse.json({
          resume_id: Number(params.resumeId),
          versions: [
            buildPublishedVersion({ revision_no: 7, created_at: "2026-07-20T00:00:00Z" }),
            buildPublishedVersion({ revision_no: 5, created_at: "2026-07-18T00:00:00Z" }),
          ],
        }),
      ),
    );
    const result = renderResumeHistory();

    const versions = await result.current.list();
    expect(versions.map((version) => version.revision_no)).toEqual([7, 5]);
  });

  it("mints and returns a presigned URL for one version's stored PDF", async () => {
    server.use(
      http.get("*/resumes/:resumeId/revisions/:revisionNo/pdf", ({ params }) =>
        HttpResponse.json({
          resume_id: Number(params.resumeId),
          revision_no: Number(params.revisionNo),
          download_url: "https://r2.example/resume-1-rev-7.pdf",
        }),
      ),
    );
    const result = renderResumeHistory();

    await expect(result.current.open(7)).resolves.toBe("https://r2.example/resume-1-rev-7.pdf");
  });

  it("throws when a version has no stored PDF (404)", async () => {
    server.use(
      http.get("*/resumes/:resumeId/revisions/:revisionNo/pdf", () =>
        HttpResponse.json({ detail: "That version has no stored PDF." }, { status: 404 }),
      ),
    );
    const result = renderResumeHistory();

    await expect(result.current.open(999)).rejects.toThrow(/unavailable/i);
  });

  it("throws when the version list cannot be loaded", async () => {
    server.use(
      http.get("*/resumes/:resumeId/revisions", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    const result = renderResumeHistory();

    await expect(result.current.list()).rejects.toThrow(/version history/i);
  });
});
