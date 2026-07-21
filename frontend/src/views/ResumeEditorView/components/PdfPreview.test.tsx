import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PdfPreview } from "./PdfPreview";

const pdfBlob = () => new Blob(["%PDF"], { type: "application/pdf" });

describe("PdfPreview", () => {
  it("renders a clickable thumbnail that expands, and reports ready", async () => {
    const fetchPreview = vi.fn().mockResolvedValue(pdfBlob());
    const renderPdf = vi.fn().mockResolvedValue(undefined);
    const onStatusChange = vi.fn();

    render(
      <PdfPreview previewKey={0} fetchPreview={fetchPreview} renderPdf={renderPdf} onStatusChange={onStatusChange} />,
    );

    const expandButton = await screen.findByRole("button", { name: /click to enlarge/i });
    await waitFor(() => expect(renderPdf).toHaveBeenCalled());
    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith("ready"));

    fireEvent.click(expandButton);
    expect(screen.getByRole("dialog", { name: "Resume preview" })).toBeInTheDocument();
  });

  it("shows an error and reports error when the preview fetch fails", async () => {
    const fetchPreview = vi.fn().mockRejectedValue(new Error("render failed"));
    const onStatusChange = vi.fn();

    render(
      <PdfPreview
        previewKey={0}
        fetchPreview={fetchPreview}
        renderPdf={vi.fn()}
        onStatusChange={onStatusChange}
      />,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to render/i);
    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith("error"));
  });

  it("reports error when PDF.js rendering itself fails", async () => {
    const fetchPreview = vi.fn().mockResolvedValue(pdfBlob());
    const renderPdf = vi.fn().mockRejectedValue(new Error("canvas render failed"));
    const onStatusChange = vi.fn();

    render(
      <PdfPreview previewKey={0} fetchPreview={fetchPreview} renderPdf={renderPdf} onStatusChange={onStatusChange} />,
    );

    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith("error"));
  });
});
