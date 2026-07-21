/**
 * The PDF.js boundary. Isolated in its own module (with a dynamic import) so the
 * rest of the view holds no static dependency on `pdfjs-dist`: preview logic is
 * tested with an injected fake renderer, and only real runtime renders load the
 * library and its worker.
 */
export type PdfRenderer = (blob: Blob, canvas: HTMLCanvasElement, scale?: number) => Promise<void>;

/** Render the first page of a PDF blob into a canvas at the given scale. */
export const renderPdfToCanvas: PdfRenderer = async (blob, canvas, scale = 1) => {
  const pdfjs = await import("pdfjs-dist");
  const workerUrl = (await import("pdfjs-dist/build/pdf.worker.min.mjs?url")).default;
  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

  const data = new Uint8Array(await blob.arrayBuffer());
  const document = await pdfjs.getDocument({ data }).promise;
  const page = await document.getPage(1);
  const viewport = page.getViewport({ scale });

  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas 2D context is unavailable.");
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  await page.render({ canvasContext: context, viewport }).promise;
};
