"use client";

import { useCallback, useEffect, useState } from "react";
import { adminService, agentService, Thread } from "@/services";
import type { ChatMessage } from "@/components/layout/useChatController";
import type { ChatRenderBlock } from "@/services/chat-presentation";
import {
  sortChatRenderBlocks,
} from "@/services/chat-presentation";
import { buildResponseBlocksFromRunTrace } from "@/services/run-trace-blocks";

export interface AgentChatHistoryItem {
  id: string;
  threadId: string;
  agentId?: string;
  title: string;
  timestamp: number;
  messages: ChatMessage[];
}

type ThreadTurn = {
  id?: string;
  run_id?: string;
  turn_index?: number;
  user_input_text?: string | null;
  assistant_output_text?: string | null;
  created_at?: string;
  completed_at?: string;
  metadata?: Record<string, unknown> | null;
};

type ThreadDetails = {
  id?: string;
  agent_id?: string | null;
  title?: string | null;
  turns?: ThreadTurn[];
};

const parseTimestamp = (value?: string, fallback: number = Date.now()): number => {
  if (!value) return fallback;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? fallback : parsed;
};

const buildResponseBlocksFromTurn = async (
  turn: ThreadTurn,
  assistantText: string,
): Promise<ChatRenderBlock[] | undefined> => {
  const metadata = turn.metadata && typeof turn.metadata === "object"
    ? (turn.metadata as Record<string, unknown>)
    : {};
  const storedBlocks = Array.isArray(metadata.response_blocks)
    ? (metadata.response_blocks as ChatRenderBlock[])
    : [];
  if (storedBlocks.length > 0) {
    return sortChatRenderBlocks(storedBlocks);
  }

  const runId = String(turn.run_id || "").trim();
  if (!runId) return undefined;

  try {
    return await buildResponseBlocksFromRunTrace(runId, assistantText, agentService.getRunEvents);
  } catch (error) {
    console.error("Failed to load run events for thread turn", { runId, error });
    return undefined;
  }
};

const mapTurnsToMessages = async (threadId: string, turns: ThreadTurn[]): Promise<ChatMessage[]> => {
  const sortedTurns = [...turns].sort(
    (a, b) => Number(a.turn_index ?? 0) - Number(b.turn_index ?? 0)
  );
  const next: ChatMessage[] = [];
  const priorAssistantParts: string[] = [];
  const responseBlocksByTurnKey = new Map<string, ChatRenderBlock[] | undefined>();
  let latestAssistantTurnKey: string | undefined;
  for (let index = sortedTurns.length - 1; index >= 0; index -= 1) {
    const turn = sortedTurns[index];
    if (String(turn.assistant_output_text ?? "").trim() && String(turn.run_id ?? "").trim()) {
      latestAssistantTurnKey = String(turn.id ?? index);
      break;
    }
  }

  await Promise.all(
    sortedTurns.map(async (turn, index) => {
      const rawAssistantText = String(turn.assistant_output_text ?? "").trim();
      if (!rawAssistantText) return;
      const turnKey = String(turn.id ?? index);
      if (turnKey !== latestAssistantTurnKey) return;
      const blocks = await buildResponseBlocksFromTurn(turn, rawAssistantText);
      responseBlocksByTurnKey.set(turnKey, blocks);
    })
  );

  sortedTurns.forEach((turn, index) => {
    const baseTimestamp = parseTimestamp(turn.created_at);
    const userText = String(turn.user_input_text ?? "").trim();
    const rawAssistantText = String(turn.assistant_output_text ?? "").trim();
    const turnKey = String(turn.id ?? index);

    if (userText) {
      next.push({
        id: `${threadId}:turn:${turnKey}:user`,
        role: "user",
        content: userText,
        createdAt: new Date(baseTimestamp),
      });
    }

    let assistantText = rawAssistantText;
    if (assistantText && priorAssistantParts.length > 0) {
      const candidates = [
        priorAssistantParts.join("\n"),
        priorAssistantParts.join(" "),
        priorAssistantParts.join(""),
      ].filter(Boolean);
      for (const prefix of candidates) {
        if (assistantText.startsWith(prefix) && assistantText.length > prefix.length) {
          assistantText = assistantText.slice(prefix.length).trimStart();
          break;
        }
      }
    }

    if (assistantText) {
      const assistantTimestamp = parseTimestamp(turn.completed_at, baseTimestamp + 1);
      const responseBlocks = responseBlocksByTurnKey.get(turnKey);
      next.push({
        id: `${threadId}:turn:${turnKey}:assistant`,
        role: "assistant",
        content: assistantText,
        createdAt: new Date(assistantTimestamp),
        runId: String(turn.run_id || "").trim() || undefined,
        responseBlocks,
      });
      priorAssistantParts.push(assistantText);
    }
  });

  return next;
};

const mapListItem = (thread: Thread): AgentChatHistoryItem => ({
  id: thread.id,
  threadId: thread.id,
  agentId: undefined,
  title: String(thread.title || "Untitled thread"),
  timestamp: parseTimestamp(thread.updated_at),
  messages: [],
});

export function useAgentThreadHistory(userId: string | undefined) {
  const [history, setHistory] = useState<AgentChatHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const refreshHistory = useCallback(async () => {
    if (!userId) {
      setHistory([]);
      return;
    }
    setHistoryLoading(true);
    try {
      const response = await adminService.getUserThreads(userId, 1, 50);
      const next = (response.items || []).map(mapListItem);
      setHistory((prev) => {
        const cachedById = new Map(prev.map((entry) => [entry.threadId, entry]));
        return next.map((entry) => {
          const cached = cachedById.get(entry.threadId);
          if (!cached || cached.messages.length === 0) return entry;
          return { ...entry, messages: cached.messages };
        });
      });
    } catch (error) {
      console.error("Failed to load persistent thread history", error);
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  const loadThreadMessages = useCallback(async (item: AgentChatHistoryItem): Promise<AgentChatHistoryItem | null> => {
    if (!item?.threadId) return null;
    if (item.messages.length > 0) return item;

    try {
      const details = (await adminService.getThread(item.threadId)) as ThreadDetails;
      const mappedMessages = await mapTurnsToMessages(
        item.threadId,
        Array.isArray(details.turns) ? details.turns : [],
      );
      const mapped: AgentChatHistoryItem = {
        ...item,
        agentId: details.agent_id ? String(details.agent_id) : item.agentId,
        title: String(details.title || item.title || "Untitled thread"),
        messages: mappedMessages,
      };
      setHistory((prev) =>
        prev.map((entry) => (entry.threadId === mapped.threadId ? mapped : entry))
      );
      return mapped;
    } catch (error) {
      console.error("Failed to load thread details", error);
      return null;
    }
  }, []);

  const upsertHistoryItem = useCallback((input: {
    threadId: string;
    agentId?: string;
    title: string;
    timestamp: number;
    messages: ChatMessage[];
  }) => {
    if (!input.threadId) return;
    setHistory((prev) => {
      const nextItem: AgentChatHistoryItem = {
        id: input.threadId,
        threadId: input.threadId,
        agentId: input.agentId,
        title: input.title,
        timestamp: input.timestamp,
        messages: input.messages,
      };
      const filtered = prev.filter((entry) => entry.threadId !== input.threadId);
      return [nextItem, ...filtered].sort((a, b) => b.timestamp - a.timestamp).slice(0, 50);
    });
  }, []);

  return {
    history,
    historyLoading,
    refreshHistory,
    loadThreadMessages,
    upsertHistoryItem,
  };
}
