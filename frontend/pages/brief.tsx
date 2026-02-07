import Head from "next/head";
import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { useLayout } from "../contexts/LayoutContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Client = { id: string; full_name: string };

export default function BriefPage() {
  const { setPageTitle } = useLayout();
  const [clients, setClients] = useState<Client[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [brief, setBrief] = useState<string | null>(null);
  const [talkingPoints, setTalkingPoints] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const briefRef = useRef<HTMLDivElement>(null);
  const printableRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPageTitle("Pre-meeting brief");
    return () => {};
  }, [setPageTitle]);

  useEffect(() => {
    fetch(`${API_BASE}/api/monitor/clients`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("Failed to load clients"))))
      .then((data) => {
        setClients(data.clients ?? []);
        if (data.clients?.length > 0 && !selectedId) setSelectedId(data.clients[0].id);
      })
      .catch(() => setClients([]));
  }, []);

  const downloadBriefPdf = () => {
    if (!printableRef.current || !brief) return;
    const title = "Pre-meeting brief";
    const content = printableRef.current.innerHTML;
    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="utf-8">
          <title>${title} – Jarvis</title>
          <style>
            body { font-family: system-ui, -apple-system, sans-serif; max-width: 700px; margin: 2rem auto; padding: 0 1.5rem; color: #1f2937; line-height: 1.6; }
            .brief-title { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; margin-bottom: 1rem; }
            .prose { font-size: 13px; }
            .prose strong { font-weight: 600; }
            .prose ul { list-style: disc; margin-left: 1.5rem; }
            .prose ol { list-style: decimal; margin-left: 1.5rem; }
            .prose li { margin: 0.25rem 0; }
            .prose p { margin: 0.5rem 0; }
            .prose h1, .prose h2, .prose h3 { font-size: 1rem; margin-top: 1rem; font-weight: 600; }
            @media print { body { margin: 1rem; } }
          </style>
        </head>
        <body>
          <div class="brief-title">${title}</div>
          <div class="prose">${content}</div>
          <script>
            window.onload = function() { window.print(); window.onafterprint = function() { window.close(); }; };
          </script>
        </body>
      </html>
    `);
    win.document.close();
  };

  const generateBrief = () => {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    setBrief(null);
    setTalkingPoints([]);
    fetch(`${API_BASE}/api/chat/brief`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: selectedId }),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((e) => Promise.reject(e));
        return res.json();
      })
      .then((data) => {
        setBrief(data.brief ?? "");
        setTalkingPoints(Array.isArray(data.talking_points) ? data.talking_points : []);
        setTimeout(() => briefRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
      })
      .catch((e) => setError(e?.detail ?? "Failed to generate brief"))
      .finally(() => setLoading(false));
  };

  return (
    <>
      <Head>
        <title>Pre-meeting brief – Jarvis</title>
      </Head>

      <p className="mb-6 text-sm leading-relaxed text-gray-500">
        Get a one-page brief before a client meeting. Jarvis combines their record, upcoming alerts, and notes from ingested documents.
      </p>

      <div className="mx-auto max-w-2xl">
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-card">
          <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-gray-500">Client</label>
          <div className="flex flex-wrap items-end gap-3">
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              className="min-w-[200px] rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
              disabled={loading}
            >
              {clients.length === 0 && <option value="">No clients</option>}
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.full_name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={generateBrief}
              disabled={loading || !selectedId}
              className="rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-60"
            >
              {loading ? "Generating…" : "Generate brief"}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-800">
            {error}
          </div>
        )}

        {loading && (
          <div className="mt-6 flex animate-fade-in items-center gap-3 rounded-xl border border-gray-200 bg-white px-6 py-5 shadow-card">
            <div className="h-2 w-2 animate-pulse rounded-full bg-sky-500" />
            <span className="text-sm text-gray-500">Building your brief…</span>
          </div>
        )}

        {brief !== null && !loading && (
          <div ref={briefRef} className="mt-6 space-y-6">
            <div className="animate-fade-in-slide rounded-xl border border-gray-200 bg-white p-6 shadow-card text-gray-800">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Pre-meeting brief</h2>
                <button
                  type="button"
                  onClick={downloadBriefPdf}
                  className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
                >
                  Download as PDF
                </button>
              </div>
              <div ref={printableRef} className="prose prose-sm max-w-none text-[13px] leading-relaxed [&_strong]:font-semibold [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:ml-4 [&_ol]:ml-4 [&_li]:my-0.5 [&_p]:my-1.5 [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_h1,_h2,_h3]:font-semibold [&_h1,_h2,_h3]:mt-3 [&_h1]:mt-0">
                <ReactMarkdown>{brief}</ReactMarkdown>
              </div>
            </div>
            {talkingPoints.length > 0 && (
              <div className="animate-fade-in-slide rounded-xl border border-sky-100 bg-sky-50/50 p-6 shadow-card">
                <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-sky-900">Jarvis suggests you cover</h2>
                <ul className="space-y-2 text-sm text-sky-900">
                  {talkingPoints.map((point, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="mt-0.5 shrink-0 text-sky-500">•</span>
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
