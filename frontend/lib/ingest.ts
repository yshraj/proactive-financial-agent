import { api, ApiError } from "./api";
import type { JobStatus, StoredDocument, UploadJobResponse } from "./types";

/** Upload a document to the ingest API. Throws ApiError on failure (incl. 409 duplicate). */
export async function uploadDocument(file: File): Promise<StoredDocument> {
  const form = new FormData();
  form.append("file", file);
  return api.postForm<StoredDocument>("/api/ingest/upload", form);
}

const JOB_POLL_MS = 1200;
const JOB_TIMEOUT_MS = 3 * 60 * 1000;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Upload via the durable job queue and poll until the pipeline finishes,
 * reporting stage progress along the way. Resolves with the final job
 * (status DONE or ERROR); throws ApiError for upload rejections (409/413/400)
 * and a timeout error if the job never settles.
 */
export async function uploadDocumentWithProgress(
  file: File,
  onProgress: (progress: number, message: string) => void
): Promise<JobStatus> {
  const form = new FormData();
  form.append("file", file);
  const { job_id } = await api.postForm<UploadJobResponse>(
    "/api/ingest/upload-async",
    form
  );
  onProgress(5, "Queued…");

  const deadline = Date.now() + JOB_TIMEOUT_MS;
  for (;;) {
    await sleep(JOB_POLL_MS);
    let job: JobStatus;
    try {
      job = await api.get<JobStatus>(`/api/ingest/jobs/${encodeURIComponent(job_id)}`);
    } catch (e) {
      // A missing job after a successful upload means the server lost it.
      if (e instanceof ApiError && e.status === 404) {
        throw new ApiError("Processing job disappeared — please retry the upload.", 404);
      }
      throw e;
    }
    if (job.status === "DONE" || job.status === "ERROR") return job;
    onProgress(Math.max(5, Math.min(job.progress, 99)), job.message || "Processing…");
    if (Date.now() > deadline) {
      throw new ApiError("Processing timed out — check the documents list shortly.", 0);
    }
  }
}

/** Ingest a pasted meeting transcript. Throws ApiError on failure (incl. 409 duplicate). */
export async function ingestTranscript(
  text: string,
  title?: string
): Promise<StoredDocument> {
  return api.post<StoredDocument>("/api/ingest/transcript", { text, title });
}
