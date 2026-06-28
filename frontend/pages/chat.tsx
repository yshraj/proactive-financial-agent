import Head from "next/head";
import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { FileText, Send, Sparkles } from "lucide-react";
import { useLayout } from "../contexts/LayoutContext";
import { Card, Button, ErrorState, PageIntro } from "../components/ui";
import { useChat } from "../hooks/useApi";

// Markdown rendering is only needed once an answer arrives, so load it lazily
// to keep it out of the page's initial bundle.
const ReactMarkdown = dynamic(() => import("react-markdown"), { ssr: false });

const SUGGESTIONS_POOL = [
  "Which clients haven't had a review in over 12 months?",
  "Show me everyone with ISA allowance still available this tax year",
  "Which clients have cash excess above 6 months expenditure that we should discuss investing?",
  "Which clients have protection gaps based on their family circumstances?",
  "Which high-net-worth clients don't have estate planning in place?",
  "Who has children approaching university age but no education planning in place?",
  "What follow-ups did I commit to that are now overdue?",
  "Show me all open action items across my client base",
  "What documents am I still waiting for from clients?",
  "Summarise upcoming deadlines",
  "Which clients have birthdays this month?",
  "Which business owner clients haven't discussed exit planning?",
];

const CHIPS_VISIBLE = 5;

export default function AICopilotPage() {
  const { setPageTitle } = useLayout();
  const [query, setQuery] = useState("");
  const [visibleChips, setVisibleChips] = useState<string[]>(() =>
    SUGGESTIONS_POOL.slice(0, CHIPS_VISIBLE)
  );
  const answerRef = useRef<HTMLDivElement>(null);
  const chat = useChat();

  useEffect(() => {
    setPageTitle("AI Copilot");
  }, [setPageTitle]);

  const ask = useCallback(
    (q: string, usedChip?: string) => {
      const text = q.trim();
      if (!text || chat.isPending) return;
      chat.mutate(text, {
        onSuccess: () => {
          setTimeout(
            () =>
              answerRef.current?.scrollIntoView({
                behavior: "smooth",
                block: "start",
              }),
            80
          );
          if (usedChip) {
            setVisibleChips((prev) => {
              const replacement = SUGGESTIONS_POOL.find(
                (p) => p !== usedChip && !prev.includes(p)
              );
              return replacement
                ? prev.map((s) => (s === usedChip ? replacement : s))
                : prev;
            });
          }
        },
      });
    },
    [chat]
  );

  const sources = chat.data?.sources ?? [];

  return (
    <>
      <Head>
        <title>AI Copilot - KritiFin</title>
      </Head>

      <PageIntro>
        Ask grounded questions across clients, alerts, and ingested documents with source-aware answers.
      </PageIntro>

      <div className="mx-auto max-w-4xl" data-testid="ai-copilot-page">
        <Card className="overflow-hidden">
          <div className="border-b border-slate-100 bg-gradient-to-br from-ai-50 to-white p-5">
            <div className="mb-4 flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-ai-600 text-white shadow-xs">
                <Sparkles className="h-5 w-5" aria-hidden />
              </span>
              <div>
                <h2 className="text-base font-semibold text-slate-950">AI Copilot</h2>
                <p className="text-sm text-slate-500">From question to cited client insight.</p>
              </div>
            </div>
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
                aria-label="Ask AI Copilot a question"
                className="input flex-1"
                disabled={chat.isPending}
                data-testid="ai-copilot-input"
              />
              <Button
                type="submit"
                loading={chat.isPending}
                disabled={!query.trim()}
                data-testid="ai-copilot-submit"
                leftIcon={!chat.isPending ? <Send className="h-4 w-4" aria-hidden /> : undefined}
              >
                {chat.isPending ? "Thinking..." : "Ask"}
              </Button>
            </form>
          </div>
          <div className="p-5">
            <p className="ui-label mb-3">Suggestions</p>
            <div className="flex flex-wrap gap-2">
              {visibleChips.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    setQuery(s);
                    ask(s, s);
                  }}
                  disabled={chat.isPending}
                  className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs text-slate-600 transition-colors hover:border-ai-100 hover:bg-ai-50 hover:text-ai-700 disabled:opacity-60"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </Card>

        {chat.isPending && (
          <Card className="mt-6 animate-fade-in">
            <div className="flex items-start gap-4 px-6 py-6">
              <div
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl bg-ai-600 text-sm font-bold text-white shadow-xs"
                aria-hidden
              >
                <Sparkles className="h-5 w-5" aria-hidden />
              </div>
              <div className="min-w-0 flex-1">
                <p className="mb-1 text-sm font-semibold text-gray-900">
                  AI Copilot is thinking
                </p>
                <p className="mb-4 text-xs text-gray-500">
                  Searching your data and documents to answer your question.
                </p>
                <div className="space-y-2">
                  <div className="skeleton h-3 w-3/4" />
                  <div className="skeleton h-3 w-full" />
                  <div className="skeleton h-3 w-5/6" />
                </div>
              </div>
            </div>
          </Card>
        )}

        {chat.isError && (
          <div className="mt-6">
            <ErrorState
              message={(chat.error as Error)?.message}
              onRetry={() => ask(query || chat.variables || "")}
            />
          </div>
        )}

        {chat.data && !chat.isPending && (
          <Card
            className="mt-6 animate-fade-in p-6 text-slate-800"
            aria-live="polite"
            data-testid="ai-copilot-answer"
          >
            <div ref={answerRef} />
            <h2 className="ui-label mb-2">Copilot Answer</h2>
            <div className="prose prose-sm max-w-none text-[13px] leading-relaxed [&_strong]:font-semibold [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:ml-4 [&_ol]:ml-4 [&_li]:my-0.5 [&_p]:my-1.5 [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:mt-3">
              <ReactMarkdown>{chat.data.answer}</ReactMarkdown>
            </div>
            {sources.length > 0 && (
              <>
                <h3 className="ui-label mb-2 mt-6">Expandable Sources</h3>
                <ul className="space-y-1.5 text-xs text-slate-600">
                  {sources.map((src, i) => (
                    <li key={i}>
                      <details className="group rounded-xl border border-slate-200 bg-slate-50/60 p-3">
                        <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-slate-950">
                          <FileText className="h-3.5 w-3.5 text-slate-400" aria-hidden />
                          {src.client_name}
                          {src.doc_type && <span className="text-slate-500">({src.doc_type})</span>}
                          {src.date && <span className="ml-auto text-slate-500">{src.date}</span>}
                        </summary>
                        <p className="mt-2 text-slate-600">{src.content}</p>
                      </details>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>
        )}
      </div>
    </>
  );
}
