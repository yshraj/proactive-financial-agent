import Head from "next/head";
import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Send } from "lucide-react";
import { useLayout } from "../contexts/LayoutContext";
import { Card, Button, ErrorState, PageIntro } from "../components/ui";
import { useChat } from "../hooks/useApi";

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

export default function AskJarvisPage() {
  const { setPageTitle } = useLayout();
  const [query, setQuery] = useState("");
  const [visibleChips, setVisibleChips] = useState<string[]>(() =>
    SUGGESTIONS_POOL.slice(0, CHIPS_VISIBLE)
  );
  const answerRef = useRef<HTMLDivElement>(null);
  const chat = useChat();

  useEffect(() => {
    setPageTitle("Ask Jarvis");
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
        <title>Ask Jarvis — Jarvis</title>
      </Head>

      <PageIntro>
        Ask anything across your clients, alerts, and ingested documents.
      </PageIntro>

      <div className="mx-auto max-w-2xl">
        <Card>
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
                aria-label="Ask Jarvis a question"
                className="input flex-1"
                disabled={chat.isPending}
              />
              <Button
                type="submit"
                loading={chat.isPending}
                disabled={!query.trim()}
                leftIcon={!chat.isPending ? <Send className="h-4 w-4" aria-hidden /> : undefined}
              >
                {chat.isPending ? "Asking…" : "Ask"}
              </Button>
            </form>
          </div>
          <div className="p-4">
            <p className="overline mb-3">Suggestions</p>
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
                  className="rounded-full border border-gray-200 bg-white px-3.5 py-1.5 text-xs text-gray-600 transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 disabled:opacity-60"
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
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white shadow-xs"
                aria-hidden
              >
                J
              </div>
              <div className="min-w-0 flex-1">
                <p className="mb-1 text-sm font-semibold text-gray-900">
                  Jarvis is thinking
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
            className="mt-6 animate-fade-in p-6 text-gray-800"
            aria-live="polite"
          >
            <div ref={answerRef} />
            <h2 className="overline mb-2">Answer</h2>
            <div className="prose prose-sm max-w-none text-[13px] leading-relaxed [&_strong]:font-semibold [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:ml-4 [&_ol]:ml-4 [&_li]:my-0.5 [&_p]:my-1.5 [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:mt-3">
              <ReactMarkdown>{chat.data.answer}</ReactMarkdown>
            </div>
            {sources.length > 0 && (
              <>
                <h3 className="overline mb-2 mt-6">Sources</h3>
                <ul className="space-y-1.5 text-xs text-gray-600">
                  {sources.map((src, i) => (
                    <li
                      key={i}
                      className="rounded-lg border border-gray-200 bg-gray-50/60 p-3"
                    >
                      <span className="font-medium text-gray-900">
                        {src.client_name}
                      </span>
                      {src.doc_type && (
                        <span className="ml-1.5 text-gray-500">({src.doc_type})</span>
                      )}
                      {src.date && <span className="ml-1.5 text-gray-500">{src.date}</span>}
                      <p className="mt-0.5 text-gray-600">{src.content}</p>
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
