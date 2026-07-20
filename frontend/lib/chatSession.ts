// Restore the visible Copilot thread after a reload or server restart.
//
// Messages are persisted server-side (durable, RLS-scoped); this remembers
// WHICH conversation this browser was in (id + client scope) so the page can
// re-fetch and re-render it. Not cross-session memory — just the current thread.

import { api } from "./api";
import type { ChatTurn } from "./ai";

const CONV_KEY = "kritifin.chat.conversationId";
const SCOPE_KEY = "kritifin.chat.clientId";

const hasWindow = (): boolean => typeof window !== "undefined";

export type StoredConversationMessage = { role: string; content: string };
type MessagesResponse = {
  conversation_id: string;
  messages: StoredConversationMessage[];
};

export function saveConversation(conversationId: string, clientId: string): void {
  if (!hasWindow()) return;
  try {
    window.localStorage.setItem(CONV_KEY, conversationId);
    window.localStorage.setItem(SCOPE_KEY, clientId || "");
  } catch {
    /* storage unavailable; thread just won't survive reload */
  }
}

export function clearConversation(): void {
  if (!hasWindow()) return;
  try {
    window.localStorage.removeItem(CONV_KEY);
    window.localStorage.removeItem(SCOPE_KEY);
  } catch {
    /* ignore */
  }
}

export function getStoredConversation(): { id: string | null; clientId: string } {
  if (!hasWindow()) return { id: null, clientId: "" };
  try {
    return {
      id: window.localStorage.getItem(CONV_KEY),
      clientId: window.localStorage.getItem(SCOPE_KEY) || "",
    };
  } catch {
    return { id: null, clientId: "" };
  }
}

/** Fetch a conversation's persisted messages (oldest first). */
export async function fetchConversationMessages(
  conversationId: string
): Promise<StoredConversationMessage[]> {
  const data = await api.get<MessagesResponse>(
    `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`
  );
  return data.messages ?? [];
}

/**
 * Pair persisted user/assistant messages into rendered turns. Sources aren't
 * persisted, so restored turns show text only (empty sources).
 */
export function messagesToTurns(messages: StoredConversationMessage[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  for (let i = 0; i < messages.length; i++) {
    if (messages[i].role !== "user") continue;
    const next = messages[i + 1];
    const answer = next && next.role === "assistant" ? next.content : "";
    turns.push({
      id: `restored-${i}`,
      query: messages[i].content,
      answer,
      sources: [],
    });
    if (next && next.role === "assistant") i++;
  }
  return turns;
}
