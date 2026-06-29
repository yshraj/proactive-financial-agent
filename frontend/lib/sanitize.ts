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

const ALLOWED_UPLOAD_MIMES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

/** Client-side MIME allowlist (server must also validate). */
export function isAllowedUploadMime(mime: string): boolean {
  return ALLOWED_UPLOAD_MIMES.has(mime);
}

/** Read first bytes and verify PDF/DOCX magic numbers. */
export async function validateUploadMagic(file: File): Promise<boolean> {
  const buf = await file.slice(0, 8).arrayBuffer();
  const bytes = new Uint8Array(buf);
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".pdf")) {
    const header = String.fromCharCode(...bytes.slice(0, 5));
    return header === "%PDF-";
  }
  if (lower.endsWith(".docx")) {
    return bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 0x03 && bytes[3] === 0x04;
  }
  return false;
}
