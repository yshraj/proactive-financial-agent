import Head from "next/head";
import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { Download, FileText, Sparkles } from "lucide-react";
import { useLayout } from "../contexts/LayoutContext";
import { Card, Button, EmptyState, ErrorState, Skeleton, PageIntro } from "../components/ui";
import { useClients, useBrief } from "../hooks/useApi";

// Markdown rendering is only needed once a brief is generated, so load it
// lazily to keep it out of the page's initial bundle.
const ReactMarkdown = dynamic(() => import("react-markdown"), { ssr: false });

export default function BriefPage() {
  const { setPageTitle } = useLayout();
  const [selectedId, setSelectedId] = useState("");
  const briefRef = useRef<HTMLDivElement>(null);
  const printableRef = useRef<HTMLDivElement>(null);

  const clientsQuery = useClients();
  const clients = useMemo(
    () => clientsQuery.data?.clients ?? [],
    [clientsQuery.data]
  );
  const brief = useBrief();

  useEffect(() => {
    setPageTitle("Meeting Brief");
  }, [setPageTitle]);

  // Default to first client once loaded.
  useEffect(() => {
    if (!selectedId && clients.length > 0) setSelectedId(clients[0].id);
  }, [clients, selectedId]);

  const generateBrief = () => {
    if (!selectedId) return;
    brief.mutate(selectedId, {
      onSuccess: () =>
        setTimeout(
          () => briefRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
          100
        ),
    });
  };

  const downloadBriefPdf = () => {
    if (!printableRef.current || !brief.data?.brief) return;
    const content = printableRef.current.innerHTML;
    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>Meeting Brief - KritiFin</title>
      <style>body{font-family:system-ui,-apple-system,sans-serif;max-width:700px;margin:2rem auto;padding:0 1.5rem;color:#1f2937;line-height:1.6}
      .brief-title{font-size:.875rem;font-weight:600;color:#6b7280;margin-bottom:1rem}
      .prose{font-size:13px}.prose strong{font-weight:600}.prose ul{list-style:disc;margin-left:1.5rem}
      .prose ol{list-style:decimal;margin-left:1.5rem}.prose li{margin:.25rem 0}.prose p{margin:.5rem 0}
      .prose h1,.prose h2,.prose h3{font-size:1rem;margin-top:1rem;font-weight:600}@media print{body{margin:1rem}}</style></head>
      <body><div class="brief-title">Meeting Brief</div><div class="prose">${content}</div>
      <script>window.onload=function(){window.print();window.onafterprint=function(){window.close()}}</script></body></html>`);
    win.document.close();
  };

  const proseClasses =
    "prose prose-sm max-w-none text-[13px] leading-relaxed [&_strong]:font-semibold [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:ml-5 [&_ol]:ml-5 [&_li]:my-1 [&_p]:my-2 [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_h2]:mt-4 [&_h3]:mt-3 [&_h1]:mt-0";

  return (
    <>
      <Head>
        <title>Meeting Brief - KritiFin</title>
      </Head>

      <PageIntro>
        Generate an executive client briefing with context, talking points, action checklist, and draftable follow-up.
      </PageIntro>

      <div className="mx-auto max-w-3xl space-y-6" data-testid="meeting-brief-page">
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
              <select
                id="client-select"
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                disabled={brief.isPending || clients.length === 0}
                className="input min-w-[200px] flex-1"
                data-testid="client-select"
              >
                {clientsQuery.isLoading && <option>Loading clients…</option>}
                {!clientsQuery.isLoading && clients.length === 0 && (
                  <option value="">No clients yet</option>
                )}
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.full_name}
                  </option>
                ))}
              </select>
              <Button
                onClick={generateBrief}
                loading={brief.isPending}
                disabled={!selectedId}
                data-testid="generate-brief-button"
                leftIcon={<Sparkles className="h-4 w-4" aria-hidden />}
              >
                {brief.isPending ? "Generating..." : "Generate brief"}
              </Button>
            </div>
          )}
        </Card>

        {brief.isError && (
          <ErrorState
            title="Couldn't generate the brief"
            message={(brief.error as Error)?.message}
            onRetry={generateBrief}
          />
        )}

        {brief.isPending && (
          <Card className="space-y-3 p-6" aria-busy="true">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-5/6" />
          </Card>
        )}

        {!brief.isPending && !brief.data && !brief.isError && (
          <EmptyState
            icon={<FileText className="h-5 w-5" aria-hidden />}
            title="No brief yet"
            description="Pick a client and generate a one-page brief with suggested talking points for your next meeting."
          />
        )}

        {brief.data && !brief.isPending && (
          <div ref={briefRef} className="space-y-6">
            <Card className="animate-fade-in p-6 text-gray-800" data-testid="generated-brief">
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="ui-label">Executive Meeting Brief</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Client snapshot, risk notes, goals, insights, and next actions.
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={downloadBriefPdf}
                  leftIcon={<Download className="h-4 w-4" aria-hidden />}
                >
                  Export PDF
                </Button>
              </div>
              <div className="mb-6 grid gap-3 sm:grid-cols-3">
                {["Client Snapshot", "Risk Profile", "Action Checklist"].map((item) => (
                  <div key={item} className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
                    <p className="text-sm font-medium text-slate-500">
                      {item}
                    </p>
                    <p className="mt-2 text-sm text-slate-600">Included in generated brief</p>
                  </div>
                ))}
              </div>
              <div ref={printableRef} className={proseClasses}>
                <ReactMarkdown>{brief.data.brief}</ReactMarkdown>
              </div>
            </Card>

            {brief.data.talking_points.length > 0 && (
              <Card className="animate-fade-in border-brand-100 bg-brand-50/40 p-6">
                <div className="mb-3 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-brand-600" aria-hidden />
                  <h2 className="text-sm font-semibold text-brand-900">
                    AI insights and talking points
                  </h2>
                </div>
                <ul className="space-y-2 text-sm text-gray-700">
                  {brief.data.talking_points.map((point, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
        )}
      </div>
    </>
  );
}
