import Head from "next/head";
import { useRouter } from "next/router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MessageSquare, Send, Sparkles } from "lucide-react";
import ClientSelect from "../components/ClientSelect";
import {
  AiMarkdown,
  AiSourceList,
  AiThinkingCard,
  AiTrustFooter,
  AiBadge,
} from "../components/ai";
import { Card, Button, EmptyState, ErrorState, PageIntro, PageShell } from "../components/ui";
import { usePageSetup } from "../hooks/usePageSetup";
import { useChat, useClients, MAX_LIST_PAGE } from "../hooks/useApi";
import {
  aiErrorMessage,
  getFollowUpSuggestions,
  type ChatTurn,
} from "../lib/ai";
import {
  clearConversation,
  fetchConversationMessages,
  getStoredConversation,
  messagesToTurns,
  saveConversation,
} from "../lib/chatSession";
import { DEMO_COPILOT_QUERY } from "../lib/demo";
import { ActionCost } from "../components/credits";
import { useCredits } from "../contexts/CreditContext";

const BOOK_SUGGESTIONS = [
  DEMO_COPILOT_QUERY,
  "Which clients haven't had a review in over 12 months?",
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

const CLIENT_SUGGESTIONS = [
  "What protection gaps does this client have?",
  "Summarise open action items for this client",
  "What did we discuss in recent meeting notes?",
  "Are there any compliance or estate planning gaps?",
  "What investments or allowances should we revisit?",
  "Summarise this client's financial profile",
];

const CHIPS_VISIBLE = 5;

function newTurnId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function AICopilotPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [selectedClientId, setSelectedClientId] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);
  const [lastFailedQuery, setLastFailedQuery] = useState<string | null>(null);
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [visibleChips, setVisibleChips] = useState<string[]>(() =>
    BOOK_SUGGESTIONS.slice(0, CHIPS_VISIBLE)
  );
  const bottomRef = useRef<HTMLDivElement>(null);
  const autoAskRef = useRef<string | null>(null);
  const chat = useChat();
  const {
    requestAction,
    activeFeature,
    activeCost,
    summary: creditSummary,
    isLoading: creditsLoading,
  } = useCredits();
  const clientsQuery = useClients(MAX_LIST_PAGE);
  const clients = useMemo(
    () => clientsQuery.data?.clients ?? [],
    [clientsQuery.data]
  );

  usePageSetup("AI Copilot");

  const queryClientId =
    typeof router.query.clientId === "string" ? router.query.clientId : "";
  const queryParam = typeof router.query.q === "string" ? router.query.q.trim() : "";

  useEffect(() => {
    if (queryClientId && clients.some((c) => c.id === queryClientId)) {
      setSelectedClientId(queryClientId);
    }
  }, [queryClientId, clients]);

  useEffect(() => {
    const pool = selectedClientId ? CLIENT_SUGGESTIONS : BOOK_SUGGESTIONS;
    setVisibleChips(pool.slice(0, CHIPS_VISIBLE));
  }, [selectedClientId]);

  const scrollToBottom = useCallback(() => {
    setTimeout(
      () => bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }),
      80
    );
  }, []);

  const ask = useCallback(
    (q: string, usedChip?: string) => {
      const text = q.trim();
      if (!text || chat.isPending || creditsLoading || !creditSummary) return;
      requestAction("chat", async () => {
        setPendingQuery(text);
        setLastFailedQuery(null);
        setFollowUps([]);
        try {
          const data = await chat.mutateAsync({
            query: text,
            clientId: selectedClientId || undefined,
            conversationId,
          });
            if (data.conversation_id) {
              setConversationId(data.conversation_id);
              // Remember the thread so a reload can restore it.
              saveConversation(data.conversation_id, selectedClientId);
            }
            setTurns((prev) => [
              ...prev,
              {
                id: newTurnId(),
                query: text,
                answer: data.answer,
                sources: data.sources ?? [],
              },
            ]);
            setPendingQuery(null);
            setQuery("");
            setFollowUps(getFollowUpSuggestions(text, !!selectedClientId));
            scrollToBottom();
            if (usedChip) {
              const pool = selectedClientId ? CLIENT_SUGGESTIONS : BOOK_SUGGESTIONS;
              setVisibleChips((prev) => {
                const replacement = pool.find(
                  (p) => p !== usedChip && !prev.includes(p)
                );
                return replacement
                  ? prev.map((s) => (s === usedChip ? replacement : s))
                  : prev;
              });
            }
        } catch (error) {
          setLastFailedQuery(text);
          setPendingQuery(null);
          throw error;
        }
      });
    },
    [
      chat,
      selectedClientId,
      conversationId,
      requestAction,
      scrollToBottom,
      creditsLoading,
      creditSummary,
    ]
  );

  // Restore the last thread on a plain reload of /chat. Deep links (?q=, ?clientId=)
  // express fresh intent, so they win and we don't restore.
  const restoredRef = useRef(false);
  useEffect(() => {
    if (restoredRef.current || !router.isReady) return;
    if (queryParam || queryClientId) return;
    restoredRef.current = true;
    const { id, clientId } = getStoredConversation();
    if (!id) return;
    (async () => {
      try {
        const messages = await fetchConversationMessages(id);
        const restored = messagesToTurns(messages);
        if (restored.length === 0) {
          clearConversation(); // stale (e.g. data was reset) — forget it
          return;
        }
        setConversationId(id);
        if (clientId) setSelectedClientId(clientId);
        setTurns(restored);
      } catch {
        /* couldn't restore; start fresh */
      }
    })();
  }, [router.isReady, queryParam, queryClientId]);

  useEffect(() => {
    if (
      !router.isReady ||
      !queryParam ||
      chat.isPending ||
      creditsLoading ||
      !creditSummary
    )
      return;
    if (clientsQuery.isLoading) return;
    if (queryClientId && selectedClientId !== queryClientId) return;
    const key = `${queryParam}:${selectedClientId || queryClientId}`;
    if (autoAskRef.current === key) return;
    autoAskRef.current = key;
    setQuery(queryParam);
    ask(queryParam);
  }, [
    router.isReady,
    queryParam,
    queryClientId,
    selectedClientId,
    clientsQuery.isLoading,
    chat.isPending,
    creditsLoading,
    creditSummary,
    ask,
  ]);

  const selectedClientName = clients.find((c) => c.id === selectedClientId)?.full_name;
  const hasConversation = turns.length > 0 || pendingQuery != null;

  return (
    <>
      <Head>
        <title>AI Copilot - KritiFin</title>
      </Head>

      <PageShell>
        <PageIntro>
          Ask grounded questions across clients, alerts, and ingested documents. Answers cite
          source documents where available.
        </PageIntro>

        <div data-testid="ai-copilot-page" className="space-y-6">
          <Card className="overflow-hidden">
            <div className="border-b border-slate-100 bg-gradient-to-br from-ai-50 to-white p-5">
              <div className="mb-4 flex flex-wrap items-end gap-3">
                <div className="min-w-[200px] flex-1">
                  <label htmlFor="copilot-client-filter" className="ui-label mb-2 block">
                    Client scope
                  </label>
                  <ClientSelect
                    id="copilot-client-filter"
                    value={selectedClientId}
                    onChange={(id) => {
                      setSelectedClientId(id);
                      setTurns([]);
                      setConversationId(undefined);
                      clearConversation();
                      setFollowUps([]);
                      autoAskRef.current = null;
                    }}
                    clients={clients}
                    isLoading={clientsQuery.isLoading}
                    disabled={chat.isPending}
                    allowAll
                    className="input w-full"
                    testId="copilot-client-filter"
                  />
                </div>
                {selectedClientName && (
                  <p className="text-sm text-slate-500">
                    Scoped to{" "}
                    <strong className="font-medium text-slate-700">{selectedClientName}</strong>
                  </p>
                )}
              </div>
              {clientsQuery.isError && (
                <p role="alert" className="mb-4 text-sm text-red-600">
                  Couldn&apos;t load your client list — scoping is unavailable.{" "}
                  <button
                    type="button"
                    onClick={() => clientsQuery.refetch()}
                    className="font-medium underline underline-offset-2 hover:text-red-700"
                  >
                    Retry
                  </button>
                </p>
              )}
              <div className="mb-4 flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-ai-600 text-white shadow-xs">
                  <Sparkles className="h-5 w-5" aria-hidden />
                </span>
                <div>
                  <h2 className="text-base font-semibold text-slate-950">AI Copilot</h2>
                  <p className="text-sm text-slate-500">
                    Grounded answers from your client book and ingested documents.
                  </p>
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
                  placeholder={
                    selectedClientId
                      ? "e.g. What open action items does this client have?"
                      : "e.g. Which clients are worried about market volatility?"
                  }
                  aria-label="Ask AI Copilot a question"
                  className="input flex-1"
                  disabled={chat.isPending}
                  data-testid="ai-copilot-input"
                />
                <Button
                  type="submit"
                  loading={chat.isPending}
                  disabled={!query.trim() || creditsLoading || !creditSummary}
                  data-testid="ai-copilot-submit"
                  leftIcon={!chat.isPending ? <Send className="h-4 w-4" aria-hidden /> : undefined}
                >
                  {chat.isPending ? "Thinking…" : "Ask"}
                </Button>
              </form>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                <ActionCost feature="chat" />
                {activeFeature === "chat" && activeCost != null && (
                  <span className="text-xs text-ai-700" role="status">
                    Using {activeCost} credits · charged only when complete
                  </span>
                )}
              </div>
            </div>
            <div className="p-5">
              <p className="ui-label mb-3">
                {hasConversation ? "Suggested follow-ups" : "Suggested questions"}
              </p>
              <div className="flex flex-wrap gap-2">
                {(hasConversation && followUps.length > 0 ? followUps : visibleChips).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => {
                      setQuery(s);
                      ask(s, hasConversation ? undefined : s);
                    }}
                    disabled={chat.isPending || creditsLoading || !creditSummary}
                    className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs text-slate-600 transition-colors hover:border-ai-100 hover:bg-ai-50 hover:text-ai-700 disabled:opacity-60"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </Card>

          {!hasConversation && !chat.isError && (
            <EmptyState
              icon={<MessageSquare className="h-5 w-5" aria-hidden />}
              title="Ask your first question"
              description="Query your client book, alerts, and ingested fact-finds or meeting notes. Answers reference source documents with numbered citations where available."
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => ask(visibleChips[0], visibleChips[0])}
                  leftIcon={<Sparkles className="h-4 w-4" aria-hidden />}
                >
                  Try: {visibleChips[0]?.slice(0, 48)}…
                </Button>
              }
            />
          )}

          {turns.map((turn) => (
            <div key={turn.id} className="space-y-3 animate-fade-in">
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-3 text-sm text-white shadow-xs">
                  {turn.query}
                </div>
              </div>
              <Card
                className="p-6 text-slate-800"
                aria-live="polite"
                data-testid={turn === turns[turns.length - 1] ? "ai-copilot-answer" : undefined}
              >
                <div className="mb-3 flex items-center gap-2">
                  <AiBadge label="Copilot answer" />
                  {turn.sources.length > 0 && (
                    <span className="text-[11px] text-slate-500">
                      {turn.sources.length} source{turn.sources.length !== 1 ? "s" : ""} cited
                    </span>
                  )}
                </div>
                <AiMarkdown compact linkCitations>
                  {turn.answer}
                </AiMarkdown>
                <AiSourceList sources={turn.sources} />
                <AiTrustFooter sourceCount={turn.sources.length} compact />
              </Card>
            </div>
          ))}

          {pendingQuery && (
            <AiThinkingCard query={pendingQuery} />
          )}

          {chat.isError && (
            <ErrorState
              title="Couldn't get an answer"
              message={aiErrorMessage(chat.error, "chat")}
              onRetry={() => ask(lastFailedQuery || query)}
            />
          )}

          <div ref={bottomRef} />
        </div>
      </PageShell>
    </>
  );
}
