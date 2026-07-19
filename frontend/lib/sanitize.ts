/** Escape HTML special characters for safe insertion into templates. */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Allow only http(s) links and internal citation anchors. */
export function isSafeHref(href: string | undefined): boolean {
  if (!href) return false;
  if (href.startsWith("#source-")) return true;
  try {
    const url = new URL(href, "https://example.invalid");
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

/** Upload formats the ingestion pipeline accepts (keep in sync with backend). */
export const ALLOWED_UPLOAD_EXTENSIONS = [".pdf", ".docx", ".md", ".txt"] as const;

const ALLOWED_UPLOAD_MIMES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "text/markdown",
  // Some browsers/OSes report .md as x-markdown or leave it empty.
  "text/x-markdown",
]);

export function hasAllowedUploadExtension(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ALLOWED_UPLOAD_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/** Client-side MIME allowlist (server must also validate). */
export function isAllowedUploadMime(mime: string): boolean {
  return ALLOWED_UPLOAD_MIMES.has(mime);
}

/**
 * Read first bytes and verify content matches the extension: magic numbers
 * for PDF/DOCX, a binary/NUL check for text formats (which have no magic).
 */
export async function validateUploadMagic(file: File): Promise<boolean> {
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".pdf") || lower.endsWith(".docx")) {
    const buf = await file.slice(0, 8).arrayBuffer();
    const bytes = new Uint8Array(buf);
    if (lower.endsWith(".pdf")) {
      const header = String.fromCharCode(...bytes.slice(0, 5));
      return header === "%PDF-";
    }
    return bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 0x03 && bytes[3] === 0x04;
  }
  if (lower.endsWith(".md") || lower.endsWith(".txt")) {
    const sample = new Uint8Array(await file.slice(0, 64 * 1024).arrayBuffer());
    if (sample.length === 0) return false;
    if (sample.includes(0)) return false; // NUL byte => binary masquerading as text
    try {
      // stream:true buffers a multi-byte sequence truncated by the sample
      // boundary instead of throwing; invalid bytes still throw.
      const truncated = file.size > sample.length;
      new TextDecoder("utf-8", { fatal: true }).decode(sample, { stream: truncated });
      return true;
    } catch {
      return false;
    }
  }
  return false;
}
