import { useCallback, useEffect, useRef, useState } from "react";
import type { Conversation, ConversationSummary } from "../types";

const PAGE_SIZE = 50;
const POLL_INTERVAL_MS = 3000;

interface UseTraceDataReturn {
  conversations: ConversationSummary[];
  selectedConversation: Conversation | null;
  loading: boolean;
  error: string | null;
  hasMore: boolean;
  selectConversation: (id: string) => void;
  loadMore: () => void;
  refresh: () => void;
}

/**
 * Data-fetching hook for the standalone TracePage.
 *
 * Calls `/api/conversations` and `/api/conversations/:id`.
 * Auto-polls every 3 seconds for real-time updates.
 * External consumers (e.g. yuuagents dashboard) should NOT use this hook —
 * they provide data directly via component props.
 */
export function useTraceData(baseUrl = ""): UseTraceDataReturn {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedConversation, setSelectedConversation] =
    useState<Conversation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const totalRef = useRef(0);
  const loadedRef = useRef(0);
  const loadingMore = useRef(false);
  const selectedIdRef = useRef<string | null>(null);

  const fetchPage = useCallback(
    async (offset: number, append: boolean) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `${baseUrl}/api/conversations?limit=${PAGE_SIZE}&offset=${offset}`,
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const page: ConversationSummary[] = data.conversations ?? [];
        totalRef.current = data.total ?? 0;
        if (append) {
          loadedRef.current += page.length;
          setConversations((prev) => [...prev, ...page]);
        } else {
          loadedRef.current = page.length;
          setConversations(page);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
        loadingMore.current = false;
      }
    },
    [baseUrl],
  );

  const fetchDetail = useCallback(
    async (id: string) => {
      try {
        const res = await fetch(`${baseUrl}/api/conversations/${id}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: Conversation = await res.json();
        setSelectedConversation(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [baseUrl],
  );

  const loadMore = useCallback(() => {
    if (loadingMore.current) return;
    loadingMore.current = true;
    fetchPage(loadedRef.current, true);
  }, [fetchPage]);

  const selectConversation = useCallback(
    async (id: string) => {
      selectedIdRef.current = id;
      setLoading(true);
      setError(null);
      await fetchDetail(id);
      setLoading(false);
    },
    [fetchDetail],
  );

  // Initial fetch
  useEffect(() => {
    fetchPage(0, false);
  }, [fetchPage]);

  // Auto-poll conversation list
  useEffect(() => {
    const id = setInterval(() => {
      fetchPage(0, false);
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchPage]);

  // Auto-poll selected conversation detail
  useEffect(() => {
    if (!selectedIdRef.current) return;
    const convId = selectedIdRef.current;
    const id = setInterval(() => {
      fetchDetail(convId);
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [selectedConversation?.id, fetchDetail]);

  const hasMore = conversations.length < totalRef.current;

  return {
    conversations,
    selectedConversation,
    loading,
    error,
    hasMore,
    selectConversation,
    loadMore,
    refresh: () => fetchPage(0, false),
  };
}
