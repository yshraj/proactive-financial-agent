import Head from "next/head";
import { useCallback, useRef, useState } from "react";
import { UploadCloud, FileText, CheckCircle2, AlertTriangle, Copy, Loader2, ShieldCheck, MessagesSquare, NotebookPen } from "lucide-react";
import { Card, CardHeader, Button, EmptyState, ErrorState, TableSkeleton, PageIntro, PageShell, Badge, useToast } from "../components/ui";
import { AiMarkdown } from "../components/ai";
import { usePageSetup } from "../hooks/usePageSetup";
import { useComplianceScan, useDocuments, useIngestTranscript, useNoteTemplate, useNoteTemplates } from "../hooks/useApi";
import { ApiError, errorMessage } from "../lib/api";
import { uploadDocument } from "../lib/ingest";
import { isAllowedUploadMime, validateUploadMagic } from "../lib/sanitize";
import { formatDateTime, formatFileSize } from "../lib/format";

type UploadState = "processing" | "done" | "duplicate" | "error";
interface UploadItem {
  id: string;
  name: string;
  state: UploadState;
  message?: string;
}

const MAX_FILE_BYTES = 20 * 1024 * 1024; // 20 MB client-side guard

/** Browse and copy structured adviser note templates. */
function NoteTemplatesCard() {
  const { notify } = useToast();
  const [selected, setSelected] = useState("");
  const templatesQuery = useNoteTemplates();
  const rendered = useNoteTemplate(selected);
  const templates = templatesQuery.data?.templates ?? [];

  const copy = async () => {
    if (!rendered.data?.markdown) return;
    try {
      await navigator.clipboard.writeText(rendered.data.markdown);
      notify("Template copied to clipboard", "success");
    } catch {
      notify("Couldn't copy to clipboard", "error");
    }
  };

  if (templates.length === 0) return null;

  return (
    <Card className="mt-10 p-6" data-testid="note-templates-card">
      <div className="mb-3 flex items-center gap-2">
        <NotebookPen className="h-4 w-4 text-brand-600" aria-hidden />
        <h2 className="text-sm font-semibold text-slate-950">Note templates</h2>
      </div>
      <p className="mb-4 text-sm text-slate-500">
        Structured meeting-note skeletons for discovery, annual review, prospect and suitability discussions.
      </p>
      <select
        className="input max-w-xs"
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        aria-label="Select a note template"
        data-testid="note-template-select"
      >
        <option value="">Choose a template…</option>
        {templates.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name} ({t.section_count} sections)
          </option>
        ))}
      </select>
      {selected && rendered.data && (
        <div className="mt-4" data-testid="note-template-preview">
          <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
            <AiMarkdown linkCitations={false}>{rendered.data.markdown}</AiMarkdown>
          </div>
          <div className="mt-3">
            <Button variant="secondary" size="sm" onClick={copy} data-testid="copy-note-template">
              Copy template
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

/** Paste a meeting transcript to run it through the same extraction pipeline as uploads. */
function TranscriptCard() {
  const { notify } = useToast();
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const ingest = useIngestTranscript();

  const submit = () => {
    ingest.mutate(
      { text, title: title.trim() || undefined },
      {
        onSuccess: () => {
          notify("Transcript ingested — extracting client and alerts.", "success");
          setText("");
          setTitle("");
        },
        onError: (e) =>
          notify(
            e instanceof ApiError && e.status === 409
              ? "This transcript has already been ingested."
              : errorMessage(e, "Transcript ingestion failed."),
            "error"
          ),
      }
    );
  };

  return (
    <Card className="mt-10 p-6" data-testid="transcript-card">
      <div className="mb-3 flex items-center gap-2">
        <MessagesSquare className="h-4 w-4 text-brand-600" aria-hidden />
        <h2 className="text-sm font-semibold text-slate-950">Paste a meeting transcript</h2>
      </div>
      <p className="mb-4 text-sm text-slate-500">
        Paste notes or a transcript and KritiFin extracts the client profile and alerts,
        and indexes it for AI Copilot — the same pipeline as document upload.
      </p>
      <label htmlFor="transcript-title" className="sr-only">
        Transcript title (optional)
      </label>
      <input
        id="transcript-title"
        className="input mb-3 w-full"
        placeholder="Optional title (e.g. Partridge annual review)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        data-testid="transcript-title"
      />
      <label htmlFor="transcript-text" className="sr-only">
        Meeting transcript
      </label>
      <textarea
        id="transcript-text"
        className="input min-h-[140px] w-full"
        placeholder="Paste the meeting transcript here (minimum 50 characters)…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        data-testid="transcript-input"
      />
      <div className="mt-3">
        <Button
          onClick={submit}
          loading={ingest.isPending}
          disabled={text.trim().length < 50}
          data-testid="transcript-submit"
        >
          Ingest transcript
        </Button>
      </div>
    </Card>
  );
}

/** Paste adviser notes and flag vulnerability / Consumer Duty signals (deterministic). */
function ComplianceScanCard() {
  const { notify } = useToast();
  const [text, setText] = useState("");
  const scan = useComplianceScan();
  const result = scan.data;

  const runScan = () => {
    scan.mutate(text, {
      onError: (e) => notify(errorMessage(e, "Scan failed."), "error"),
    });
  };

  const hasResults =
    !!result &&
    (result.vulnerability_signals.length > 0 || result.consumer_duty_flags.length > 0);

  return (
    <Card className="mt-10 p-6" data-testid="compliance-scan-card">
      <div className="mb-3 flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-brand-600" aria-hidden />
        <h2 className="text-sm font-semibold text-slate-950">Compliance signal scan</h2>
      </div>
      <p className="mb-4 text-sm text-slate-500">
        Paste meeting notes to flag vulnerability drivers (FCA FG21/1) and Consumer Duty
        signals for review. Flags are indicative — the adviser makes the assessment.
      </p>
      <label htmlFor="compliance-scan-text" className="sr-only">
        Client meeting notes to scan
      </label>
      <textarea
        id="compliance-scan-text"
        className="input min-h-[120px] w-full"
        placeholder="Paste client meeting notes here…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        data-testid="compliance-scan-input"
      />
      <div className="mt-3">
        <Button
          onClick={runScan}
          loading={scan.isPending}
          disabled={!text.trim()}
          data-testid="compliance-scan-button"
        >
          Scan notes
        </Button>
      </div>

      {result && !hasResults && (
        <p className="mt-4 text-sm text-emerald-700" data-testid="compliance-scan-clear">
          No vulnerability or Consumer Duty signals detected.
        </p>
      )}

      {hasResults && (
        <div className="mt-5 space-y-4" data-testid="compliance-scan-results">
          {result.vulnerability_signals.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Vulnerability signals
              </h3>
              <ul className="space-y-2">
                {result.vulnerability_signals.map((s, i) => (
                  <li key={i} className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3">
                    <Badge className="bg-amber-100 text-amber-800">{s.category}</Badge>
                    <p className="text-xs text-slate-600">{s.excerpt}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {result.consumer_duty_flags.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Consumer Duty signals
              </h3>
              <ul className="space-y-2">
                {result.consumer_duty_flags.map((s, i) => (
                  <li key={i} className="flex items-start gap-3 rounded-xl border border-brand-200 bg-brand-50/50 px-4 py-3">
                    <Badge className="bg-brand-100 text-brand-800">{s.outcome}</Badge>
                    <p className="text-xs text-slate-600">{s.excerpt}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export default function IngestionPage() {
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const docsQuery = useDocuments();
  const storedList = docsQuery.data ?? [];

  usePageSetup("Ingestion");

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
      if (file.type && !isAllowedUploadMime(file.type)) {
        setUploads((p) => [...p, { id, name: file.name, state: "error", message: "Invalid file type. Only PDF and Word (.docx) are accepted." }]);
        return;
      }
      const magicOk = await validateUploadMagic(file);
      if (!magicOk) {
        setUploads((p) => [...p, { id, name: file.name, state: "error", message: "File content does not match its extension." }]);
        return;
      }

      setUploads((p) => [...p, { id, name: file.name, state: "processing", message: "Uploading, extracting & indexing…" }]);
      try {
        const doc = await uploadDocument(file);
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
        if (e instanceof ApiError && e.status === 413) {
          patch(id, { state: "error", message: "File is too large — the server limit is 20 MB." });
          return;
        }
        if (e instanceof ApiError && e.status === 400) {
          patch(id, { state: "error", message: errorMessage(e, "The server rejected this file as invalid.") });
          return;
        }
        patch(id, { state: "error", message: errorMessage(e, "Upload failed.") });
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
        <title>Ingestion - KritiFin</title>
      </Head>

      <PageShell wide>
      <PageIntro>
        Upload client documents. KritiFin extracts the data, indexes it for search, and turns processing into adviser-ready intelligence.
        Duplicates are detected automatically.
      </PageIntro>

      <input
        ref={fileInputRef}
        type="file"
        data-testid="document-upload-input"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        multiple
        className="hidden"
        onChange={(e) => {
          onFiles(e.target.files);
          e.target.value = "";
        }}
      />

      <Card
        className={`mb-10 border-dashed transition-colors ${
          dragging ? "border-brand-400 bg-brand-50/40" : "border-slate-300 hover:border-brand-200 hover:bg-brand-50/20"
        }`}
      >
      <div
        data-testid="document-dropzone"
        className="p-10 text-center sm:p-12"
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
        <h2 className="mb-1.5 text-base font-semibold text-slate-950">Drop PDFs or Word docs here</h2>
        <p className="mb-6 text-sm text-slate-500">
          Supports PDF and .docx, up to 20 MB. Duplicates (same content) are detected and skipped.
        </p>
        <Button size="lg" onClick={() => fileInputRef.current?.click()} data-testid="choose-files-button">
          Choose files
        </Button>
      </div>
      </Card>

      {uploads.length > 0 && (
        <div className="mb-10 animate-fade-in" data-testid="upload-status">
          <h2 className="mb-3 text-sm font-semibold text-slate-950">Upload status</h2>
          <ul className="space-y-2">
            {uploads.map((f) => (
              <li
                key={f.id}
                data-testid="upload-status-item"
                className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 shadow-xs transition-colors ${
                  f.state === "duplicate"
                    ? "border-amber-200 bg-amber-50/60"
                    : f.state === "error"
                    ? "border-red-200 bg-red-50/50"
                    : f.state === "done"
                    ? "border-emerald-200 bg-emerald-50/40"
                    : "border-slate-200 bg-white"
                }`}
              >
                {f.state === "processing" && <Loader2 className="h-4 w-4 animate-spin text-brand-600" aria-hidden />}
                {f.state === "done" && <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden />}
                {f.state === "duplicate" && <Copy className="h-4 w-4 text-amber-600" aria-hidden />}
                {f.state === "error" && <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden />}
                <span className="flex-1 text-sm font-medium text-slate-950">{f.name}</span>
                <span
                  className={`text-xs font-medium ${
                    f.state === "duplicate"
                      ? "text-amber-800"
                      : f.state === "error"
                      ? "text-red-700"
                      : f.state === "done"
                      ? "text-emerald-800"
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

      <Card className="overflow-hidden" data-testid="stored-documents">
        <CardHeader title="Stored documents" />
        {docsQuery.isLoading ? (
          <TableSkeleton rows={3} />
        ) : docsQuery.isError ? (
          <div className="p-6">
            <ErrorState message={errorMessage(docsQuery.error)} onRetry={() => docsQuery.refetch()} />
          </div>
        ) : storedList.length === 0 ? (
          <EmptyState
            icon={<FileText className="h-5 w-5" aria-hidden />}
            title="No documents yet"
            description="Upload a PDF or Word file above to populate your dashboard and power AI Copilot."
            action={
              <Button size="lg" onClick={() => fileInputRef.current?.click()}>
                Upload your first document
              </Button>
            }
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {storedList.map((doc) => (
              <li key={doc.id} className="flex flex-wrap items-center gap-4 px-6 py-4 transition-colors hover:bg-slate-50/60">
                <FileText className="h-4 w-4 flex-shrink-0 text-slate-400" aria-hidden />
                <span className="flex-1 text-sm font-medium text-slate-950">{doc.filename}</span>
                <span className="text-xs text-slate-500">{formatFileSize(doc.file_size_bytes)}</span>
                <span className="text-xs text-slate-500">{formatDateTime(doc.uploaded_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <TranscriptCard />

      <NoteTemplatesCard />

      <ComplianceScanCard />
      </PageShell>
    </>
  );
}
