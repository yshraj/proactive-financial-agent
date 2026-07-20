// Reusable upload payloads for setInputFiles. Centralizing the byte-level
// fixtures keeps magic buffers out of specs and guarantees every test agrees
// on what a "valid PDF" or a "binary masquerading as text" looks like.

export type UploadFilePayload = {
  name: string;
  mimeType: string;
  buffer: Buffer;
};

/** Client-side upload ceiling — keep in sync with frontend/lib/sanitize.ts. */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

const MINIMAL_PDF = "%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF";
const PNG_MAGIC = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const EXE_MAGIC = [0x4d, 0x5a, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00];

/** A structurally valid (minimal) PDF that passes the client magic check. */
export function pdfFile(name = "sample.pdf"): UploadFilePayload {
  return { name, mimeType: "application/pdf", buffer: Buffer.from(MINIMAL_PDF) };
}

export function markdownFile(
  name = "meeting-notes.md",
  content = "# Client review\n\nDiscussed pension consolidation and ISA top-up."
): UploadFilePayload {
  return { name, mimeType: "text/markdown", buffer: Buffer.from(content) };
}

export function textFile(
  name = "call-summary.txt",
  content = "Call with client about protection cover renewal."
): UploadFilePayload {
  return { name, mimeType: "text/plain", buffer: Buffer.from(content) };
}

/** .pdf extension with plain-text bytes — must fail the client magic check. */
export function fakePdfFile(name = "fake-report.pdf"): UploadFilePayload {
  return {
    name,
    mimeType: "application/pdf",
    buffer: Buffer.from("this is not a pdf at all"),
  };
}

/** Unsupported image type — must be rejected by the extension allowlist. */
export function pngFile(name = "photo.png"): UploadFilePayload {
  return { name, mimeType: "image/png", buffer: Buffer.from(PNG_MAGIC) };
}

/** Executable bytes renamed to .txt — must fail the NUL/binary check. */
export function binaryAsTextFile(name = "innocent.txt"): UploadFilePayload {
  return { name, mimeType: "text/plain", buffer: Buffer.from(EXE_MAGIC) };
}

/**
 * One byte over the 20 MB client-side ceiling. Starts with a valid PDF header
 * so the ONLY reason it can be rejected is size.
 */
export function oversizedPdfFile(name = "huge-factfind.pdf"): UploadFilePayload {
  const padding = Buffer.alloc(MAX_UPLOAD_BYTES + 1 - MINIMAL_PDF.length, 0x20);
  return {
    name,
    mimeType: "application/pdf",
    buffer: Buffer.concat([Buffer.from(MINIMAL_PDF), padding]),
  };
}
