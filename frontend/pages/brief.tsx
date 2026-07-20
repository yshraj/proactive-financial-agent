import Head from "next/head";
import { useRouter } from "next/router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, FileText, Mail, RefreshCw, Sparkles } from "lucide-react";
import LazyDraftEmailModal from "../components/LazyDraftEmailModal";
import ClientSelect from "../components/ClientSelect";
import {
  AiMarkdown,
  AiSourceList,
  AiThinkingCard,
  AiTrustFooter,
  AiBadge,
} from "../components/ai";
import { Card, Button, EmptyState, ErrorState, PageIntro, PageShell } from "../components/ui";
import { useDraftEmailModalState } from "../hooks/useDraftEmailModalState";
import { usePageSetup } from "../hooks/usePageSetup";
import { useClients, useBrief, MAX_LIST_PAGE } from "../hooks/useApi";
import { aiErrorMessage } from "../lib/ai";
import { escapeHtml } from "../lib/sanitize";

const BRIEF_STEPS = [
  "Loading client profile and open alerts",
  "Retrieving fact-find and meeting note excerpts",
  "Drafting executive meeting brief",
  "Preparing talking points",
];

export default function BriefPage() {
  const router = useRouter();
  const [selectedId, setSelectedId] = useState("");
  const { source: draftEmailSource, openBriefDraft, closeDraft } = useDraftEmailModalState();
  const briefRef = useRef<HTMLDivElement>(null);
  const printableRef = useRef<HTMLDivElement>(null);
  const autoTriggered = useRef(false);

  usePageSetup("Meeting Brief");

  const clientsQuery = useClients(MAX_LIST_PAGE);
  const clients = useMemo(
    () => clientsQuery.data?.clients ?? [],
    [clientsQuery.data]
  );
  const brief = useBrief();

  const queryClientId =
    typeof router.query.clientId === "string" ? router.query.clientId : "";
  const shouldAutoGenerate = router.query.auto === "1";
  const selectedClientName = clients.find((c) => c.id === selectedId)?.full_name;

  useEffect(() => {
    if (!queryClientId || clients.length === 0) return;
    if (clients.some((c) => c.id === queryClientId)) {
      setSelectedId(queryClientId);
    }
  }, [queryClientId, clients]);

  useEffect(() => {
    if (queryClientId || selectedId || clients.length === 0) return;
    setSelectedId(clients[0].id);
  }, [clients, selectedId, queryClientId]);

  const scrollToBrief = useCallback(() => {
    setTimeout(
      () => briefRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      100
    );
  }, []);

  const generateBrief = useCallback(
    (refresh = false) => {
      if (!selectedId) return;
      // refresh=true (the Regenerate button) bypasses the server-side cache;
      // the initial generate keeps using it for fast repeat loads.
      brief.mutate({ clientId: selectedId, refresh }, { onSuccess: scrollToBrief });
    },
    [selectedId, brief, scrollToBrief]
  );

  useEffect(() => {
    if (!shouldAutoGenerate || autoTriggered.current || !selectedId || brief.isPending) return;
    if (queryClientId && selectedId !== queryClientId) return;
    if (!clients.some((c) => c.id === selectedId)) return;
    autoTriggered.current = true;
    brief.mutate({ clientId: selectedId }, { onSuccess: scrollToBrief });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once when deep-link params are ready
  }, [shouldAutoGenerate, selectedId, queryClientId, clients.length, brief.isPending, scrollToBrief]);

  const downloadBriefPdf = () => {
    if (!printableRef.current || !brief.data?.brief) return;
    const content = printableRef.current.innerHTML;
    const win = window.open("", "_blank");
    if (!win) return;
    const title = escapeHtml(selectedClientName ?? "Client");
    win.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>Meeting Brief - KritiFin</title>
      <style>body{font-family:system-ui,-apple-system,sans-serif;max-width:700px;margin:2rem auto;padding:0 1.5rem;color:#1f2937;line-height:1.6}
      .brief-title{font-size:.875rem;font-weight:600;color:#6b7280;margin-bottom:1rem}
      .prose{font-size:13px}.prose strong{font-weight:600}.prose ul{list-style:disc;margin-left:1.5rem}
      .prose ol{list-style:decimal;margin-left:1.5rem}.prose li{margin:.25rem 0}.prose p{margin:.5rem 0}
      .prose h1,.prose h2,.prose h3{font-size:1rem;margin-top:1rem;font-weight:600}@media print{body{margin:1rem}}</style></head>
      <body><div class="brief-title">Meeting Brief — ${title}</div><div class="prose">${content}</div>
      <script>window.onload=function(){window.print();window.onafterprint=function(){window.close()}}</script></body></html>`);
    win.document.close();
  };

  const openFollowUpDraft = () => {
    if (!brief.data || !selectedId) return;
    openBriefDraft(selectedId, brief.data.brief, brief.data.talking_points);
  };

  return (
    <>
      <Head>
        <title>Meeting Brief - KritiFin</title>
      </Head>

      <PageShell>
        <PageIntro>
          Generate an executive pre-meeting brief from structured client data and ingested
          documents, with talking points and a draftable follow-up email.
        </PageIntro>

        <div className="space-y-6" data-testid="meeting-brief-page">
          <Card className="p-5">
            <label htmlFor="client-select" className="ui-label mb-2 block">
              Client
            </label>
            {clientsQuery.isError ? (
              <ErrorState
                message="Couldn't load clients."
                onRetry={() => clientsQuery.refetch()}
              />
            ) : (
              <div className="flex flex-wrap items-end gap-3">
                <ClientSelect
                  id="client-select"
                  value={selectedId}
                  onChange={setSelectedId}
                  clients={clients}
                  isLoading={clientsQuery.isLoading}
                  disabled={brief.isPending}
                  testId="client-select"
                />
                <Button
                  onClick={() => generateBrief()}
                  loading={brief.isPending}
                  disabled={!selectedId}
                  data-testid="generate-brief-button"
                  leftIcon={<Sparkles className="h-4 w-4" aria-hidden />}
                >
                  {brief.isPending ? "Generating…" : "Generate brief"}
                </Button>
              </div>
            )}
          </Card>

          {brief.isError && (
            <ErrorState
              title="Couldn't generate the brief"
              message={aiErrorMessage(brief.error, "brief")}
              onRetry={() => generateBrief()}
            />
          )}

          {brief.isPending && (
            <Card className="p-6" aria-busy="true">
              <AiThinkingCard
                title="Preparing your meeting brief"
                steps={BRIEF_STEPS}
                compact={false}
              />
            </Card>
          )}

          {!brief.isPending && !brief.data && !brief.isError && (
            <EmptyState
              icon={<FileText className="h-5 w-5" aria-hidden />}
              title="No brief yet"
              description="Pick a client and generate a one-page pre-meeting brief with suggested talking points grounded in their profile and uploaded documents."
              action={
                selectedId ? (
                  <Button
                    onClick={() => generateBrief()}
                    leftIcon={<Sparkles className="h-4 w-4" aria-hidden />}
                  >
                    Generate brief for {selectedClientName ?? "client"}
                  </Button>
                ) : undefined
              }
            />
          )}

          {brief.data && !brief.isPending && (
            <div ref={briefRef} className="space-y-6">
              <Card className="animate-fade-in p-6 text-slate-800" data-testid="generated-brief">
                <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <h2 className="ui-label">Executive meeting brief</h2>
                      <AiBadge />
                    </div>
                    <p className="text-sm text-slate-500">
                      {selectedClientName
                        ? `Prepared for ${selectedClientName} — client snapshot, priorities, document insights, and suggested agenda.`
                        : "Client snapshot, priorities, document insights, and suggested agenda."}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => generateBrief(true)}
                      leftIcon={<RefreshCw className="h-4 w-4" aria-hidden />}
                      data-testid="regenerate-brief-button"
                    >
                      Regenerate
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={openFollowUpDraft}
                      leftIcon={<Mail className="h-4 w-4" aria-hidden />}
                      data-testid="draft-follow-up-button"
                    >
                      Draft follow-up email
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={downloadBriefPdf}
                      leftIcon={<Download className="h-4 w-4" aria-hidden />}
                    >
                      Export PDF
                    </Button>
                  </div>
                </div>
                <div ref={printableRef}>
                  <AiMarkdown linkCitations={false}>{brief.data.brief}</AiMarkdown>
                </div>
                {(brief.data.sources?.length ?? 0) > 0 && (
                  <AiSourceList sources={brief.data.sources ?? []} title="Document sources" />
                )}
                <AiTrustFooter sourceCount={brief.data.sources?.length} />
              </Card>

              {brief.data.talking_points.length > 0 && (
                <Card className="animate-fade-in border-brand-100 bg-brand-50/40 p-6">
                  <div className="mb-3 flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-brand-600" aria-hidden />
                    <h2 className="text-sm font-semibold text-brand-900">
                      Key talking points
                    </h2>
                  </div>
                  <ul className="space-y-2.5 text-sm text-slate-700">
                    {brief.data.talking_points.map((point, i) => (
                      <li key={i} className="flex items-start gap-2.5">
                        <span
                          className="mt-1.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-600 text-[10px] font-bold text-white"
                          aria-hidden
                        >
                          {i + 1}
                        </span>
                        <span className="leading-relaxed">{point}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
            </div>
          )}

          {draftEmailSource && (
            <LazyDraftEmailModal source={draftEmailSource} onClose={closeDraft} />
          )}
        </div>
      </PageShell>
    </>
  );
}
