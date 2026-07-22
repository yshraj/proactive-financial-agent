import { api, ApiError } from "./api";
import type { JobStatus, StoredDocument, UploadJobResponse } from "./types";

// Poll quickly while the job is fresh, then back off — long waits happen when
// the worker trigger was lost and the 5-minute scheduled drain has to pick the
// job up, so there is no point hammering the status endpoint meanwhile.
const JOB_POLL_FAST_MS = 1200;
const JOB_POLL_SLOW_MS = 5000;
const JOB_POLL_SLOW_AFTER_MS = 30 * 1000;
// Worst case on AWS: lost trigger (recovered by the 5-minute schedule) plus
// processing time. 3 minutes was shorter than that recovery window and
// reported "timed out" for jobs that then completed.
const JOB_TIMEOUT_MS = 8 * 60 * 1000;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Final job state plus a `stalled` flag for jobs that outlived the polling
 * window without failing — they usually finish shortly after. */
export type UploadJobResult = JobStatus & { stalled?: boolean };

export const STILL_PROCESSING_MESSAGE =
  "Your document is still being processed. This can happen during busy periods. " +
  "You can safely leave this page and check back later.";

/** One-off status check for a stalled job ("Check status" button). */
export async function fetchJobStatus(jobId: string): Promise<JobStatus> {
  return api.get<JobStatus>(`/api/ingest/jobs/${encodeURIComponent(jobId)}`);
}

/**
 * Upload via the durable job queue and poll until the pipeline finishes,
 * reporting stage progress along the way. Resolves with the final job
 * (status DONE or ERROR), or with `stalled: true` when the job is still
 * running after the polling window — that is not an error: the document
 * keeps processing server-side and appears in the list when finished.
 * Throws ApiError for upload rejections (409/413/400).
 */
export async function uploadDocumentWithProgress(
  file: File,
  onProgress: (progress: number, message: string) => void
): Promise<UploadJobResult> {
  const form = new FormData();
  form.append("file", file);
  const { job_id } = await api.postForm<UploadJobResponse>(
    "/api/ingest/upload-async",
    form
  );
  onProgress(5, "Queued…");

  const started = Date.now();
  const deadline = started + JOB_TIMEOUT_MS;
  let lastSeen: JobStatus | null = null;
  for (;;) {
    await sleep(Date.now() - started > JOB_POLL_SLOW_AFTER_MS ? JOB_POLL_SLOW_MS : JOB_POLL_FAST_MS);
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
    lastSeen = job;
    if (job.status === "DONE" || job.status === "ERROR") return job;
    onProgress(Math.max(5, Math.min(job.progress, 99)), job.message || "Processing…");
    if (Date.now() > deadline) {
      // Not a failure: the durable queue keeps working after we stop polling.
      return {
        ...(lastSeen ?? {
          id: job_id,
          kind: "upload",
          status: "PROCESSING",
          progress: 99,
          message: "Processing…",
        }),
        stalled: true,
      };
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
