import Head from "next/head";
import { useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { useLayout } from "../contexts/LayoutContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SUGGESTIONS_POOL = [
  "Which of my clients are underweight in equities relative to their risk profile and time horizon?",
  "Show me everyone with ISA allowance still available this tax year",
  "Show me everyone with Annual allowance still available this tax year",
  "Which clients have cash excess above 6 months expenditure that we should discuss investing?",
  "Flag any clients where their current trajectory won't meet their stated retirement income goals",
  "Which clients have protection gaps based on their family circumstances?",
  "Which retired clients are taking more than 4% withdrawal rates?",
  "Show me which clients would be impacted if interest rates drop to 3%",
  "Which clients are most exposed if we see a 20% market correction?",
  "Which clients haven't had a review in over 12 months?",
  "Show me all business owners who might benefit from the new R&D tax credit changes",
  "Who has children approaching university age but no education planning in place?",
  "Find clients with similar profiles to the Smiths who successfully navigated early retirement",
  "Which high-net-worth clients don't have estate planning in place?",
  "Show me pension clients who might benefit from our cashflow modelling service",
  "Who has investment portfolios but no protection cover?",
  "Which business owner clients haven't discussed exit planning?",
  "Which clients have birthdays this month?",
  "Pull every recommendation I made to David Chen and the rationale I gave",
  "What was my exact wording when discussing risk with the Williams family?",
  "Show me all clients where I recommended Platform X and why",
  "Which client conversations mentioned concerns about market volatility?",
  "Generate a summary of all discussions about sustainable investing preferences",
  "What documents am I still waiting for from clients?",
  "What did I promise to send the Jackson family and when?",
  "What concerns did clients raise in meetings this month?",
  "Which services do my highest-value clients use most?",
  "Show me conversion rates from initial meeting to becoming a client by referral source",
  "What percentage of my book is approaching retirement in the next 5 years?",
  "Which clients generate the most revenue but take the least time to service?",
  "What do my most satisfied long-term clients have in common?",
  "Which types of recommendations get the most pushback and why?",
  "Show me clients whose circumstances are similar to cases where we added significant value",
  "What life events trigger clients to actually implement recommendations?",
  "Draft the follow-up email to yesterday's meeting with the key actions we agreed",
  "Which clients am I waiting on for information or decisions?",
  "Show me all open action items across my client base",
  "What follow-ups did I commit to that are now overdue?",
  "Summarise upcoming deadlines",
];

const CHIPS_VISIBLE = 5;

type Source = { content: string; client_name: string; doc_type: string; date: string };

export default function AskJarvisPage() {
  const { setPageTitle } = useLayout();
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visibleChips, setVisibleChips] = useState<string[]>(() => SUGGESTIONS_POOL.slice(0, CHIPS_VISIBLE));
  const [lastUsedChip, setLastUsedChip] = useState<string | null>(null);
  const answerSectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPageTitle("Ask Jarvis");
    return () => {};
  }, [setPageTitle]);

  const scrollToAnswer = useCallback(() => {
    answerSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const ask = useCallback(
    async (q: string, fromChip?: string) => {
      const text = (q || query).trim();
      if (!text) return;
      setLoading(true);
      setError(null);
      setAnswer(null);
      setSources([]);
      if (fromChip) setLastUsedChip(fromChip);
      try {
        const res = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: text }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `Request failed: ${res.status}`);
        }
        const data = await res.json();
        setAnswer(data.answer ?? "");
        setSources(data.sources ?? []);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Something went wrong");
      } finally {
        setLoading(false);
      }
    },
    [query]
  );

  useEffect(() => {
    if (!loading && answer !== null && lastUsedChip) {
      setVisibleChips((prev) => {
        const replacement = SUGGESTIONS_POOL.find((p) => p !== lastUsedChip && !prev.includes(p));
        if (!replacement) return prev;
        return prev.map((s) => (s === lastUsedChip ? replacement : s));
      });
      setLastUsedChip(null);
    }
  }, [loading, answer, lastUsedChip]);

  useEffect(() => {
    if (!loading && answer !== null && answerSectionRef.current) {
      scrollToAnswer();
    }
  }, [loading, answer, scrollToAnswer]);

  return (
    <>
      <Head>
        <title>Ask Jarvis – Jarvis</title>
      </Head>

      <p className="mb-8 text-sm leading-relaxed text-gray-500">
        Ask questions about your client data. Jarvis uses both your client and alert records and ingested documents (PDFs and Word). Upload documents in Ingestion for richer answers.
      </p>

      <div className="mx-auto max-w-2xl">
        <div className="rounded-xl border border-gray-200 bg-white shadow-card transition-shadow">
          <div className="border-b border-gray-100 p-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                ask(query);
              }}
              className="flex gap-2"
            >
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. Which clients are worried about market volatility?"
                className="flex-1 rounded-lg border border-gray-200 px-4 py-2.5 text-sm shadow-sm transition-colors focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20 disabled:bg-gray-50"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading}
                className="flex items-center justify-center gap-1.5 rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-sky-500 disabled:opacity-90 disabled:hover:bg-sky-600"
              >
                {loading ? (
                  <>
                    <span className="sr-only">Asking Jarvis…</span>
                    <span className="inline-flex gap-0.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-white animate-jarvis-bounce" />
                      <span className="h-1.5 w-1.5 rounded-full bg-white animate-jarvis-bounce-delay-1" />
                      <span className="h-1.5 w-1.5 rounded-full bg-white animate-jarvis-bounce-delay-2" />
                    </span>
                    <span className="ml-1">Asking…</span>
                  </>
                ) : (
                  "Ask"
                )}
              </button>
            </form>
          </div>
          <div className="border-b border-gray-100 px-4 pt-4 pb-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">Suggestions</p>
            <div className="flex flex-wrap gap-2">
              {visibleChips.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    setQuery(s);
                    ask(s, s);
                  }}
                  disabled={loading}
                  className="rounded-full border border-gray-200 bg-gray-50 px-3.5 py-1.5 text-xs text-gray-700 transition-all duration-200 hover:border-sky-200 hover:bg-sky-50 hover:text-sky-800 disabled:opacity-60"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading && (
          <div className="mt-6 animate-fade-in overflow-hidden rounded-xl border border-sky-100 bg-gradient-to-b from-sky-50/80 to-white shadow-card">
            <div className="flex items-start gap-5 px-6 py-6">
              <div
                className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl bg-sky-600 text-white shadow-md animate-jarvis-glow"
                aria-hidden
              >
                <span className="text-lg font-bold">J</span>
              </div>
              <div className="min-w-0 flex-1">
                <p className="mb-1 text-sm font-semibold text-gray-900">Jarvis is thinking</p>
                <p className="mb-4 text-xs text-gray-500">Searching your data and documents to answer your question.</p>
                <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500">
                  <span className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-jarvis-bounce" />
                    Searching clients & alerts
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-jarvis-bounce-delay-1" />
                    Reading documents
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-jarvis-bounce-delay-2" />
                    Synthesizing answer
                  </span>
                </div>
                <div className="mt-4 h-1 w-full overflow-hidden rounded-full bg-sky-100">
                  <div
                    className="h-full rounded-full bg-sky-500 animate-jarvis-step"
                    style={{ maxWidth: "100%" }}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-800 transition-opacity">
            {error}
          </div>
        )}

        {answer !== null && !loading && (
          <div
            ref={answerSectionRef}
            className="markdown-answer mt-6 animate-fade-in-slide rounded-xl border border-gray-200 bg-white p-5 shadow-card text-gray-800"
          >
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Answer</h2>
            <div className="prose prose-sm max-w-none text-[13px] leading-relaxed [&_strong]:font-semibold [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:ml-4 [&_ol]:ml-4 [&_li]:my-0.5 [&_p]:my-1.5 [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_h1,_h2,_h3]:font-semibold [&_h1,_h2,_h3]:mt-3 [&_h1]:mt-0">
              <ReactMarkdown>{answer}</ReactMarkdown>
            </div>
            {sources.length > 0 && (
              <>
                <h3 className="mt-5 mb-1.5 text-xs font-semibold uppercase tracking-wider text-gray-500">Sources</h3>
                <ul className="space-y-1.5 text-xs text-gray-600">
                  {sources.map((src, i) => (
                    <li key={i} className="rounded-lg border border-gray-100 bg-gray-50/50 p-2.5">
                      <span className="font-medium text-gray-900">{src.client_name}</span>
                      {src.doc_type && <span className="ml-1.5 text-gray-500">({src.doc_type})</span>}
                      {src.date && <span className="ml-1.5 text-gray-500">{src.date}</span>}
                      <p className="mt-0.5 text-gray-600">{src.content}</p>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}
