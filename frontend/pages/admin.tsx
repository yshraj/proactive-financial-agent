import Head from "next/head";
import { useCallback, useEffect, useRef, useState } from "react";
import { UploadCloud, FileText, CheckCircle2, AlertTriangle, Copy, Loader2 } from "lucide-react";
import { useLayout } from "../contexts/LayoutContext";
import { Card, CardHeader, Button, EmptyState, ErrorState, TableSkeleton } from "../components/ui";
import { useDocuments } from "../hooks/useApi";
import { api, ApiError } from "../lib/api";
import { formatDateTime, formatFileSize } from "../lib/format";
import type { StoredDocument } from "../lib/types";

type UploadState = "processing" | "done" | "duplicate" | "error";
interface UploadItem {
  id: string;
  name: string;
  state: UploadState;
  message?: string;
}

const MAX_FILE_BYTES = 20 * 1024 * 1024; // 20 MB client-side guard

export default function IngestionPage() {
  const { setPageTitle, setHeaderExtra } = useLayout();
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const docsQuery = useDocuments();
  const storedList = docsQuery.data ?? [];

  useEffect(() => {
    setPageTitle("Ingestion");
    setHeaderExtra(null);
    return () => setHeaderExtra(null);
  }, [setPageTitle, setHeaderExtra]);

  const patch = (id: string, p: Partial<UploadItem>) =>
    setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, ...p } : u)));

  const processFile = useCallback(
    async (file: File) => {
      const id = `up-${Date.now()}-${file.name}`;
      const lower = file.name.toLowerCase();
      if (!lower.endsWith(".pdf") && !lower.endsWith(".docx")) {
        setUploads((p) => [...p, { id, name: file.name, state: "error", message: "Only PDF and Word (.docx) files are accepted." }]);
        return;
      }
      if (file.size > MAX_FILE_BYTES) {
        setUploads((p) => [...p, { id, name: file.name, state: "error", message: "File is larger than 20 MB." }]);
        return;
      }

      setUploads((p) => [...p, { id, name: file.name, state: "processing", message: "Uploading, extracting & indexing…" }]);
      const form = new FormData();
      form.append("file", file);
      try {
        const doc = await api.postForm<StoredDocument>("/api/ingest/upload", form);
        patch(id, {
          state: "done",
          message: doc.processing_error ? `Stored, but processing had issues: ${doc.processing_error}` : "Done — extracted and indexed.",
        });
        docsQuery.refetch();
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          const detail = e.detail as { existing_filename?: string } | undefined;
          patch(id, { state: "duplicate", message: `Same content as "${detail?.existing_filename ?? "an existing file"}". Not stored again.` });
          return;
        }
        patch(id, { state: "error", message: e instanceof Error ? e.message : "Upload failed." });
      }
    },
    [docsQuery]
  );

  const onFiles = (files: FileList | null) => {
    if (!files?.length) return;
    Array.from(files).forEach(processFile);
  };

  return (
    <>
      <Head>
        <title>Ingestion — Jarvis</title>
      </Head>

      <p className="mb-8 max-w-2xl text-sm leading-relaxed text-gray-500">
        Upload client PDFs and Word documents (fact-finds, meeting notes) to
        extract structured data and index content for Ask Jarvis. Duplicate
        content is detected by file hash and won&apos;t be stored twice.
      </p>

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        multiple
        className="hidden"
        onChange={(e) => {
          onFiles(e.target.files);
          e.target.value = "";
        }}
      />

      <div
        className={`mb-10 rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
          dragging ? "border-brand-400 bg-brand-50/50" : "border-gray-200 bg-white hover:border-brand-300 hover:bg-brand-50/30"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onFiles(e.dataTransfer?.files ?? null);
        }}
      >
        <div className="mb-4 flex justify-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
            <UploadCloud className="h-6 w-6" aria-hidden />
          </span>
        </div>
        <h2 className="mb-2 text-lg font-semibold text-gray-900">Drop PDFs or Word docs here</h2>
        <p className="mb-6 text-sm text-gray-500">
          Supports PDF and .docx, up to 20 MB. Duplicates (same content) are detected and skipped.
        </p>
        <Button onClick={() => fileInputRef.current?.click()}>Choose files</Button>
      </div>

      {uploads.length > 0 && (
        <div className="mb-10">
          <h2 className="mb-4 text-base font-semibold text-gray-900">Upload status</h2>
          <ul className="space-y-2">
            {uploads.map((f) => (
              <li
                key={f.id}
                className={`flex flex-wrap items-center gap-3 rounded-lg border px-5 py-4 shadow-sm ${
                  f.state === "duplicate"
                    ? "border-amber-200 bg-amber-50/50"
                    : f.state === "error"
                    ? "border-red-200 bg-red-50/40"
                    : "border-gray-200 bg-white"
                }`}
              >
                {f.state === "processing" && <Loader2 className="h-4 w-4 animate-spin text-brand-600" aria-hidden />}
                {f.state === "done" && <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden />}
                {f.state === "duplicate" && <Copy className="h-4 w-4 text-amber-600" aria-hidden />}
                {f.state === "error" && <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden />}
                <span className="flex-1 text-sm font-medium text-gray-900">{f.name}</span>
                <span
                  className={`text-xs ${
                    f.state === "duplicate"
                      ? "text-amber-700"
                      : f.state === "error"
                      ? "text-red-600"
                      : f.state === "done"
                      ? "text-emerald-700"
                      : "text-brand-700"
                  }`}
                >
                  {f.message}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Card className="overflow-hidden">
        <CardHeader title="Stored documents" />
        {docsQuery.isLoading ? (
          <TableSkeleton rows={3} />
        ) : docsQuery.isError ? (
          <div className="p-6">
            <ErrorState message={(docsQuery.error as Error)?.message} onRetry={() => docsQuery.refetch()} />
          </div>
        ) : storedList.length === 0 ? (
          <EmptyState
            icon={<FileText className="h-5 w-5" aria-hidden />}
            title="No documents yet"
            description="Upload a PDF or Word file above to populate your dashboard and power Ask Jarvis."
          />
        ) : (
          <ul className="divide-y divide-gray-100">
            {storedList.map((doc) => (
              <li key={doc.id} className="flex flex-wrap items-center gap-4 px-6 py-4">
                <FileText className="h-4 w-4 flex-shrink-0 text-gray-400" aria-hidden />
                <span className="flex-1 text-sm font-medium text-gray-900">{doc.filename}</span>
                <span className="text-xs text-gray-500">{formatFileSize(doc.file_size_bytes)}</span>
                <span className="text-xs text-gray-500">{formatDateTime(doc.uploaded_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
