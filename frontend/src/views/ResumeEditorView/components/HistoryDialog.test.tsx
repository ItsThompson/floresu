import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { buildPublishedVersion } from "@/mocks/resumeFixtures";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/renderWithProviders";

import { HistoryDialog } from "./HistoryDialog";

const PDF_BYTES = new TextEncoder().encode("%PDF-1.4\ntrailer<</Root 1 0 R>>\n%%EOF");

/** MSW handler that serves the presigned R2 object as real PDF bytes. */
function serveR2Pdf() {
  return http.get("https://r2.example/*", () =>
    HttpResponse.arrayBuffer(PDF_BYTES.buffer as ArrayBuffer, {
      headers: { "Content-Type": "application/pdf" },
    }),
  );
}

/** List handler returning the given versions in the order provided (newest-first). */
function listVersions(versions: ReturnType<typeof buildPublishedVersion>[]) {
  return http.get("*/resumes/:resumeId/revisions", ({ params }) =>
    HttpResponse.json({ resume_id: Number(params.resumeId), versions }),
  );
}

function renderDialog(renderPdf = vi.fn().mockResolvedValue(undefined)) {
  renderWithProviders(
    <HistoryDialog isOpen onClose={vi.fn()} resumeId={1} renderPdf={renderPdf} />,
  );
  return renderPdf;
}

describe("HistoryDialog", () => {
  it("lists published versions newest-first with revision number and timestamp", async () => {
    server.use(
      listVersions([
        buildPublishedVersion({ revision_no: 7, created_at: "2026-07-20T00:00:00Z" }),
        buildPublishedVersion({ revision_no: 5, created_at: "2026-07-18T00:00:00Z" }),
      ]),
    );
    renderDialog();

    const rows = await screen.findAllByRole("button", { name: /Revision \d/ });
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("Revision 7"),
      expect.stringContaining("Revision 5"),
    ]);
    expect(rows[0]).toHaveTextContent("Jul 20, 2026");
  });

  it("shows the empty state when the resume has no published versions", async () => {
    server.use(listVersions([]));
    renderDialog();

    expect(
      await screen.findByText(/No published versions yet\. Export or finalize to create one\./),
    ).toBeInTheDocument();
  });

  it("renders the selected version's PDF read-only through the injected boundary", async () => {
    server.use(
      listVersions([buildPublishedVersion({ revision_no: 7 })]),
      http.get("*/resumes/:resumeId/revisions/:revisionNo/pdf", ({ params }) =>
        HttpResponse.json({
          resume_id: 1,
          revision_no: Number(params.revisionNo),
          download_url: "https://r2.example/rev-7.pdf",
        }),
      ),
      serveR2Pdf(),
    );
    const renderPdf = renderDialog();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Revision 7/ }));

    await waitFor(() => expect(renderPdf).toHaveBeenCalledTimes(1));
    const blobArg = renderPdf.mock.calls[0][0] as Blob;
    expect(blobArg.type).toBe("application/pdf");
    expect(blobArg.size).toBeGreaterThan(0);
    expect(await screen.findByLabelText("Revision 7 PDF")).toBeInTheDocument();
  });

  it("surfaces a recoverable per-row error when a version's PDF is unavailable", async () => {
    server.use(
      listVersions([
        buildPublishedVersion({ revision_no: 7 }),
        buildPublishedVersion({ revision_no: 5 }),
      ]),
      http.get("*/resumes/:resumeId/revisions/:revisionNo/pdf", ({ params }) => {
        const revisionNo = Number(params.revisionNo);
        if (revisionNo === 7) {
          return HttpResponse.json({ detail: "no stored PDF" }, { status: 404 });
        }
        return HttpResponse.json({
          resume_id: 1,
          revision_no: revisionNo,
          download_url: "https://r2.example/rev-5.pdf",
        });
      }),
      serveR2Pdf(),
    );
    const renderPdf = renderDialog();
    const user = userEvent.setup();

    // The unavailable version reports on its own row and does not render a PDF.
    await user.click(await screen.findByRole("button", { name: /Revision 7/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/This version's PDF is unavailable/);
    expect(renderPdf).not.toHaveBeenCalled();

    // A different row still opens normally.
    await user.click(screen.getByRole("button", { name: /Revision 5/ }));
    await waitFor(() => expect(renderPdf).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("re-mints a fresh URL when a failed row is selected again", async () => {
    let pdfCalls = 0;
    server.use(
      listVersions([buildPublishedVersion({ revision_no: 7 })]),
      http.get("*/resumes/:resumeId/revisions/:revisionNo/pdf", () => {
        pdfCalls += 1;
        if (pdfCalls === 1) return HttpResponse.json({ detail: "gone" }, { status: 404 });
        return HttpResponse.json({
          resume_id: 1,
          revision_no: 7,
          download_url: "https://r2.example/rev-7-retry.pdf",
        });
      }),
      serveR2Pdf(),
    );
    const renderPdf = renderDialog();
    const user = userEvent.setup();

    const row = await screen.findByRole("button", { name: /Revision 7/ });
    await user.click(row);
    expect(await screen.findByRole("alert")).toHaveTextContent(/unavailable/i);

    // Re-selecting the errored row re-requests the URL and renders on success.
    await user.click(row);
    await waitFor(() => expect(renderPdf).toHaveBeenCalledTimes(1));
    expect(pdfCalls).toBe(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
