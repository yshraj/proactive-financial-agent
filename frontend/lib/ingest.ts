import { api } from "./api";
import type { StoredDocument } from "./types";

/** Upload a document to the ingest API. Throws ApiError on failure (incl. 409 duplicate). */
export async function uploadDocument(file: File): Promise<StoredDocument> {
  const form = new FormData();
  form.append("file", file);
  return api.postForm<StoredDocument>("/api/ingest/upload", form);
}
