import { useCallback, useEffect, useState } from "react";
import type { Conversation, ConversationSummary } from "../types";

interface UseTraceDataReturn {
  conversations: ConversationSummary[];
  selectedConversation: Conversation | null;
  loading: boolean;
  error: string | null;
  selectConversation: (id: string) => void;
  refresh: () => void;
}

/**
 * Data-fetching hook for the standalone TracePage.
 *
 * Calls `/api/conversations` and `/api/conversations/:id`.
 * External consumers (e.g. yuuagents dashboard) should NOT use this hook —
 * they provide data directly via component props.
 */
export function useTraceData(baseUrl = ""): UseTraceDataReturn {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedConversation, setSelectedConversation] =
    useState<Conversation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchConversations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${baseUrl}/api/conversations`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setConversations(data.conversations ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [baseUrl]);

  const selectConversation = useCallback(
    async (id: string) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${baseUrl}/api/conversations/${id}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: Conversation = await res.json();
        setSelectedConversation(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [baseUrl],
  );

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  return {
    conversations,
    selectedConversation,
    loading,
    error,
    selectConversation,
    refresh: fetchConversations,
  };
}
