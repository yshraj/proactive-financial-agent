import Head from "next/head";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLayout } from "../contexts/LayoutContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type StoredDocument = {
  id: string;
  filename: string;
  content_hash: string;
  file_size_bytes: number | null;
  uploaded_at: string;
};

type UploadState = "idle" | "uploading" | "done" | "duplicate" | "error";

type IngestStep = "uploading" | "extracting" | "indexing";

type FileUploadItem = {
  id: string;
  name: string;
  progress: number;
  status: string;
  state: UploadState;
  step?: IngestStep;
  duplicateExisting?: string;
  errorMessage?: string;
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function IngestionPage() {
  const { setPageTitle, setHeaderExtra } = useLayout();
  const [storedList, setStoredList] = useState<StoredDocument[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [uploads, setUploads] = useState<FileUploadItem[]>([]);
  const [duplicateAlert, setDuplicateAlert] = useState<{ filename: string; existing: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = useCallback(async () => {
    setLoadingList(true);
    setListError(null);
    try {
      const res = await fetch(`${API_BASE}/api/ingest/documents`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const msg =
          typeof body.detail === "string"
            ? body.detail
            : body.detail?.message || (res.status === 404 ? "API not found. Is the backend running?" : `Failed to load list: ${res.status}`);
        throw new Error(msg);
      }
      const data = await res.json();
      setStoredList(Array.isArray(data) ? data : []);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to load documents");
      setStoredList([]);
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    setPageTitle("Ingestion");
    setHeaderExtra(null);
    return () => setHeaderExtra(null);
  }, [setPageTitle, setHeaderExtra]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleChooseFiles = () => {
    fileInputRef.current?.click();
  };

  const processFile = async (file: File) => {
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".pdf") && !lower.endsWith(".docx")) {
      setUploads((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}-${file.name}`,
          name: file.name,
          progress: 0,
          status: "Only PDF and Word (.docx) are accepted",
          state: "error",
          errorMessage: "Only PDF and Word (.docx) files are accepted",
        },
      ]);
      return;
    }

    const id = `up-${Date.now()}-${file.name}`;
    setUploads((prev) => [
      ...prev,
      { id, name: file.name, progress: 0, status: "Uploading…", state: "uploading", step: "uploading" },
    ]);

    const formData = new FormData();
    formData.append("file", file);

    const updateUpload = (patch: Partial<FileUploadItem>) =>
      setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, ...patch } : u)));

    const stepTimeouts: ReturnType<typeof setTimeout>[] = [];
    stepTimeouts.push(setTimeout(() => updateUpload({ status: "Extracting…", step: "extracting" }), 800));
    stepTimeouts.push(setTimeout(() => updateUpload({ status: "Indexing…", step: "indexing" }), 2200));

    try {
      const res = await fetch(`${API_BASE}/api/ingest/upload`, {
        method: "POST",
        body: formData,
      });

      stepTimeouts.forEach((t) => clearTimeout(t));

      if (res.status === 409) {
        const body = await res.json().catch(() => ({}));
        const detail = body.detail || {};
        const existingFilename = detail.existing_filename || "an existing file";
        updateUpload({
          progress: 100,
          status: "Duplicate",
          state: "duplicate",
          step: undefined,
          duplicateExisting: existingFilename,
        });
        setDuplicateAlert({ filename: file.name, existing: existingFilename });
        return;
      }

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const msg =
          typeof body.detail === "string"
            ? body.detail
            : body.detail?.message || body.detail || res.statusText;
        updateUpload({
          progress: 0,
          status: "Error",
          state: "error",
          step: undefined,
          errorMessage: typeof msg === "string" ? msg : JSON.stringify(msg),
        });
        return;
      }

      const doc = await res.json();
      updateUpload({
        progress: 100,
        status: doc.processing_error ? "Stored (processing had issues)" : "Done",
        state: "done",
        step: undefined,
        errorMessage: doc.processing_error || undefined,
      });
      setDuplicateAlert(null);
      await fetchDocuments();
    } catch (e) {
      stepTimeouts.forEach((t) => clearTimeout(t));
      setUploads((prev) =>
        prev.map((u) =>
          u.id === id
            ? {
                ...u,
                progress: 0,
                status: "Error",
                state: "error",
                step: undefined,
                errorMessage: e instanceof Error ? e.message : "Network error",
              }
            : u
        )
      );
    }
  };

  const onFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length) return;
    for (let i = 0; i < files.length; i++) {
      processFile(files[i]);
    }
    e.target.value = "";
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.currentTarget.classList.remove("border-sky-400", "bg-sky-50/50");
    const files = e.dataTransfer?.files;
    if (!files?.length) return;
    for (let i = 0; i < files.length; i++) {
      processFile(files[i]);
    }
  };

  return (
    <>
      <Head>
        <title>Ingestion – Jarvis</title>
      </Head>

      <p className="mb-8 text-sm leading-relaxed text-gray-500">
        Upload client PDFs and Word documents (.docx) — fact-finds, meeting notes — to extract structured data into the database and index content for the Ask Jarvis chat. Duplicate content is detected by file hash and will not be stored twice.
      </p>

      {duplicateAlert && (
        <div
          className="mb-6 flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800"
          role="alert"
        >
          <span>
            <strong>Duplicate content.</strong> The file you uploaded has the same content as &quot;{duplicateAlert.existing}&quot;. It was not stored again.
          </span>
          <button
            type="button"
            onClick={() => setDuplicateAlert(null)}
            className="ml-4 shrink-0 rounded-lg px-3 py-1.5 font-medium text-amber-700 hover:bg-amber-100"
          >
            Dismiss
          </button>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        multiple
        className="hidden"
        onChange={onFileSelected}
      />

      <div
        className="mb-10 rounded-xl border-2 border-dashed border-gray-200 bg-white p-12 text-center transition-colors hover:border-sky-300 hover:bg-sky-50/30"
        onDragOver={(e) => {
          e.preventDefault();
          e.currentTarget.classList.add("border-sky-400", "bg-sky-50/50");
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          e.currentTarget.classList.remove("border-sky-400", "bg-sky-50/50");
        }}
        onDrop={onDrop}
      >
        <div className="mb-4 text-4xl opacity-70">📄</div>
        <h2 className="mb-2 text-lg font-semibold text-gray-900">Drop PDFs or Word docs here</h2>
        <p className="mb-6 text-sm text-gray-500">Supports PDF and .docx. Fact-finds, meeting notes and client documents. Duplicates (same content) are detected and skipped.</p>
        <button
          type="button"
          className="rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-sky-500"
          onClick={handleChooseFiles}
        >
          Choose files
        </button>
      </div>

      {uploads.length > 0 && (
        <>
          <h2 className="mb-4 text-base font-semibold text-gray-900">Upload status</h2>
          {uploads.some((u) => u.state === "uploading") && (
            <div className="mb-6 animate-fade-in overflow-hidden rounded-xl border border-sky-200 bg-gradient-to-br from-sky-50 via-white to-sky-50/50 shadow-sm">
              <div className="flex flex-wrap items-center gap-6 p-6 sm:flex-nowrap">
                <div className="relative flex flex-shrink-0" aria-hidden>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="h-16 w-16 rounded-full bg-sky-200/60 animate-ingest-ring" />
                  </div>
                  <div className="relative flex h-20 w-16 flex-col items-center justify-end rounded-lg border-2 border-sky-200 bg-white shadow-md animate-ingest-doc-float">
                    <div className="absolute inset-0 overflow-hidden rounded-md">
                      <div className="h-full w-full bg-gradient-to-r from-transparent via-sky-200/40 to-transparent animate-ingest-shimmer" style={{ width: "50%" }} />
                    </div>
                    <span className="mb-2 text-[10px] font-medium text-sky-600">PDF</span>
                  </div>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="mb-1 text-sm font-semibold text-gray-900">Preparing your data</p>
                  <p className="mb-4 text-xs text-gray-600">
                    We're uploading your file, extracting client & alert data, and indexing it for Ask Jarvis.
                  </p>
                  <div className="flex flex-wrap items-center gap-4 sm:gap-6">
                    {[
                      { key: "uploading", label: "Upload", icon: "↑" },
                      { key: "extracting", label: "Extract", icon: "◇" },
                      { key: "indexing", label: "Index", icon: "◆" },
                    ].map(({ key, label, icon }) => {
                      const activeStep = uploads.find((u) => u.state === "uploading")?.step;
                      const isActive = activeStep === key;
                      const stepOrder = ["uploading", "extracting", "indexing"];
                      const activeIdx = stepOrder.indexOf(activeStep ?? "uploading");
                      const thisIdx = stepOrder.indexOf(key);
                      const isDone = activeIdx > thisIdx;
                      return (
                        <div key={key} className="flex items-center gap-2">
                          <span
                            className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                              isActive ? "bg-sky-600 text-white shadow-md animate-ingest-step-dot" : isDone ? "bg-sky-400 text-white" : "bg-gray-200 text-gray-500"
                            }`}
                          >
                            {isDone ? "✓" : icon}
                          </span>
                          <span className={`text-xs font-medium ${isActive ? "text-sky-700" : "text-gray-500"}`}>
                            {label}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}
          <div className="mb-4 flex items-center gap-6 rounded-lg border border-sky-100 bg-sky-50/50 px-4 py-3 text-xs text-sky-800">
            <span className="font-medium">Pipeline:</span>
            <span className="text-sky-600">1. Upload</span>
            <span className="text-sky-400">→</span>
            <span className="text-sky-600">2. Extract</span>
            <span className="text-sky-400">→</span>
            <span className="text-sky-600">3. Index</span>
          </div>
          <ul className="mb-10 space-y-2">
            {uploads.map((f) => (
              <li
                key={f.id}
                className={`flex flex-wrap items-center gap-4 rounded-lg border bg-white px-5 py-4 shadow-sm ${
                  f.state === "duplicate" ? "border-amber-200 bg-amber-50/50" : f.state === "error" ? "border-red-200 bg-red-50/30" : "border-gray-200"
                }`}
              >
                <span className="flex-1 text-sm font-medium text-gray-900">{f.name}</span>
                {f.state === "uploading" && (
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                      {(["uploading", "extracting", "indexing"] as const).map((s) => (
                        <span
                          key={s}
                          className={`h-2 w-2 rounded-full ${
                            f.step === s ? "bg-sky-500 animate-pulse" : (f.step === "extracting" && s === "uploading") || (f.step === "indexing" && s !== "indexing") ? "bg-sky-300" : "bg-gray-200"
                          }`}
                          title={s === "uploading" ? "Upload" : s === "extracting" ? "Extract" : "Index"}
                        />
                      ))}
                    </div>
                    <span className="text-xs font-medium text-sky-700">{f.status}</span>
                  </div>
                )}
                {f.state !== "uploading" && (
                  <span
                    className={`text-xs font-medium ${
                      f.state === "duplicate" ? "text-amber-700" : f.state === "error" ? "text-red-600" : "text-gray-500"
                    }`}
                  >
                    {f.status}
                  </span>
                )}
                {f.duplicateExisting && (
                  <span className="w-full text-xs text-amber-700">Same content as: {f.duplicateExisting}</span>
                )}
                {f.errorMessage && <span className="w-full text-xs text-red-600">{f.errorMessage}</span>}
                {f.state === "uploading" && (
                  <div className="h-1.5 w-28 overflow-hidden rounded-full bg-gray-100">
                    <div
                      className="h-full animate-pulse rounded-full bg-sky-500 transition-all duration-500"
                      style={{ width: f.step === "uploading" ? "33%" : f.step === "extracting" ? "66%" : "100%" }}
                    />
                  </div>
                )}
                {f.state === "done" && (
                  <div className="h-1.5 w-28 overflow-hidden rounded-full bg-gray-100">
                    <div className="h-full rounded-full bg-sky-500" style={{ width: "100%" }} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      <h2 className="mb-4 text-base font-semibold text-gray-900">Stored documents</h2>
      {loadingList ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : listError ? (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{listError}</p>
      ) : storedList.length === 0 ? (
        <p className="text-sm text-gray-500">No documents stored yet. Upload a PDF or Word file above.</p>
      ) : (
        <ul className="space-y-2">
          {storedList.map((doc) => (
            <li
              key={doc.id}
              className="flex flex-wrap items-center gap-4 rounded-lg border border-gray-200 bg-white px-5 py-4 shadow-sm"
            >
              <span className="flex-1 text-sm font-medium text-gray-900">{doc.filename}</span>
              <span className="text-xs text-gray-500">{doc.file_size_bytes != null ? `${(doc.file_size_bytes / 1024).toFixed(1)} KB` : "—"}</span>
              <span className="text-xs text-gray-500">{formatDate(doc.uploaded_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
