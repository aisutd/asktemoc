"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useSession } from "next-auth/react";
import { Conversation, Message, MessageContentItem } from "@/types";

type ConversationRow = {
  id: string;
  title: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
};

type StoredMessage = {
  id: string;
  index: number;
  role: string;
  content: { parts?: unknown } | unknown[] | null;
  status: string;
};

type ConversationContextValue = {
  conversations: Conversation[];
  selectedConversationId: string;
  loading: boolean;
  creating: boolean;
  error: string | null;
  selectConversation: (id: string) => void;
  createConversation: () => Promise<void>;
  updateConversation: (conversationId: string, messages: Message[]) => void;
  deleteConversation: (conversationId: string) => void;
};

const ConversationContext = createContext<ConversationContextValue | null>(null);

function redirectToSignIn(): void {
  const back = window.location.pathname + window.location.search;
  window.location.assign(`/signin?callbackUrl=${encodeURIComponent(back)}`);
}

function isContentItem(value: unknown): value is MessageContentItem {
  if (!value || typeof value !== "object") return false;
  const item = value as { type?: unknown; message?: unknown };
  return (
    (item.type === "text" || item.type === "source") &&
    typeof item.message === "string"
  );
}

function partsFromContent(content: StoredMessage["content"]): MessageContentItem[] {
  const raw = Array.isArray(content) ? content : content?.parts;
  if (!Array.isArray(raw)) return [];
  return raw.filter(isContentItem);
}

function messageFromRow(row: StoredMessage, when: string): Message {
  return {
    id: row.id,
    role: row.role === "assistant" ? "assistant" : "user",
    content: partsFromContent(row.content),
    timestamp: new Date(when),
  };
}

function transcriptLength(messages: Message[]): number {
  return messages.reduce(
    (total, message) =>
      total + message.content.reduce((sum, part) => sum + part.message.length, 0),
    0,
  );
}

function toConversation(row: ConversationRow, messages: Message[] = []): Conversation {
  return {
    id: row.id,
    title: row.title?.trim() || "New Chat",
    messages,
    lastMessage: new Date(row.last_message_at ?? row.created_at),
  };
}

async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown; error?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (typeof body.error === "string") return body.error;
  } catch {
    // The body was not JSON.
  }
  return fallback;
}

export function ConversationProvider({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();
  const userId = session?.user?.id;
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "loading") return;
    if (status !== "authenticated" || !userId) {
      setConversations([]);
      setSelectedConversationId("");
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await fetch("/api/conversations", { cache: "no-store" });
        if (res.status === 401) {
          redirectToSignIn();
          return;
        }
        if (!res.ok) {
          throw new Error(await errorMessage(res, "Could not load conversations"));
        }
        const body = (await res.json()) as { conversations: ConversationRow[] };
        if (cancelled) return;
        setConversations((prev) => {
          const existing = new Map(prev.map((conv) => [conv.id, conv]));
          return body.conversations.map((row) => {
            const prior = existing.get(row.id);
            return toConversation(row, prior?.messages ?? []);
          });
        });
        setSelectedConversationId((current) => {
          if (current && body.conversations.some((row) => row.id === current)) return current;
          return body.conversations[0]?.id ?? "";
        });
        setError(null);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load conversations");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [status, userId]);

  useEffect(() => {
    if (!selectedConversationId || status !== "authenticated") return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/conversations/${selectedConversationId}`, {
          cache: "no-store",
        });
        if (res.status === 401) {
          redirectToSignIn();
          return;
        }
        if (!res.ok) {
          throw new Error(await errorMessage(res, "Could not load conversation"));
        }
        const body = (await res.json()) as ConversationRow & { messages: StoredMessage[] };
        if (cancelled) return;
        const when = body.last_message_at ?? body.created_at;
        const loaded = body.messages.map((row) => messageFromRow(row, when));
        setConversations((prev) =>
          prev.map((conv) => {
            if (conv.id !== body.id) return conv;
            if (
              conv.messages.length > loaded.length ||
              transcriptLength(conv.messages) > transcriptLength(loaded)
            ) {
              return conv;
            }
            return {
              ...conv,
              title: body.title?.trim() || conv.title,
              messages: loaded,
              lastMessage: new Date(when),
            };
          }),
        );
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load conversation");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedConversationId, status]);

  const createConversation = useCallback(async () => {
    setCreating(true);
    setError(null);
    try {
      const res = await fetch("/api/conversations", {
        method: "POST",
        cache: "no-store",
      });
      if (res.status === 401) {
        redirectToSignIn();
        return;
      }
      if (!res.ok) {
        throw new Error(await errorMessage(res, "Could not create a conversation"));
      }
      const row = toConversation((await res.json()) as ConversationRow);
      setConversations((prev) => [row, ...prev.filter((conv) => conv.id !== row.id)]);
      setSelectedConversationId(row.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create a conversation");
    } finally {
      setCreating(false);
    }
  }, []);

  const updateConversation = useCallback(
    (conversationId: string, messages: Message[]) => {
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === conversationId
            ? {
                ...conv,
                messages,
                title:
                  messages.length > 0 && conv.title === "New Chat"
                    ? messages[0].content
                        .find((item) => item.type === "text")
                        ?.message.slice(0, 30) + "..." || "New Chat"
                    : conv.title,
                lastMessage: new Date(),
              }
            : conv,
        ),
      );
    },
    [],
  );

  const deleteConversation = useCallback((conversationId: string) => {
    setConversations((prev) => {
      const next = prev.filter((conv) => conv.id !== conversationId);
      setSelectedConversationId((current) => {
        if (current !== conversationId) return current;
        return next[0]?.id ?? "";
      });
      return next;
    });
  }, []);

  return (
    <ConversationContext.Provider
      value={{
        conversations,
        selectedConversationId,
        loading,
        creating,
        error,
        selectConversation: setSelectedConversationId,
        createConversation,
        updateConversation,
        deleteConversation,
      }}
    >
      {children}
    </ConversationContext.Provider>
  );
}

export function useConversations(): ConversationContextValue {
  const value = useContext(ConversationContext);
  if (!value) {
    throw new Error("useConversations must be used within ConversationProvider");
  }
  return value;
}
