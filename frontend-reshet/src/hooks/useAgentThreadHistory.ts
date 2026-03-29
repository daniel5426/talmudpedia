"use client";

import { useCallback, useEffect, useState } from "react";
import { adminService, agentService, Thread } from "@/services";
import type { ChatMessage } from "@/components/layout/useChatController";
import type { ChatRenderBlock } from "@/services/chat-presentation";
import {
  sortChatRenderBlocks,
} from "@/services/chat-presentation";
import { buildResponseBlocksFromRunTrace } from "@/services/run-trace-blocks";
import type { FileUIPart } from "ai";

type RuntimeAttachmentDto = {
  id: string;
  filename: string;
  mime_type: string;
};

export interface AgentChatHistoryItem {
  id: string;
  threadId: string;
  agentId?: string;
  title: string;
  timestamp: number;
  messages: ChatMessage[];
  hasMoreHistory?: boolean;
  nextBeforeTurnIndex?: number | null;
  isLoadingOlderHistory?: boolean;
}

type ThreadTurn = {
  id?: string;
  run_id?: string;
  turn_index?: number;
  user_input_text?: string | null;
  assistant_output_text?: string | null;
  run_usage?: {
    source?: string | null;
    input_tokens?: number | null;
    output_tokens?: number | null;
    total_tokens?: number | null;
  } | null;
  attachments?: RuntimeAttachmentDto[];
  created_at?: string;
  completed_at?: string;
  metadata?: Record<string, unknown> | null;
};

type ThreadDetails = {
  id?: string;
  agent_id?: string | null;
  title?: string | null;
  updated_at?: string;
  turns?: ThreadTurn[];
  paging?: {
    has_more?: boolean;
    next_before_turn_index?: number | null;
  } | null;
};

const DEFAULT_THREAD_PAGE_SIZE = 20;

const parseTimestamp = (value?: string, fallback: number = Date.now()): number => {
  if (!value) return fallback;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? fallback : parsed;
};

const mapRuntimeAttachment = (attachment: RuntimeAttachmentDto): FileUIPart => ({
  type: "file",
  filename: attachment.filename,
  mediaType: attachment.mime_type,
  url: "",
});

export const sortThreadTurnsForReplay = (turns: ThreadTurn[]): ThreadTurn[] =>
  [...turns].sort((left, right) => {
    const turnIndexDiff = Number(left.turn_index ?? 0) - Number(right.turn_index ?? 0);
    if (turnIndexDiff !== 0) return turnIndexDiff;

    const createdDiff = parseTimestamp(left.created_at, 0) - parseTimestamp(right.created_at, 0);
    if (createdDiff !== 0) return createdDiff;

    const completedDiff = parseTimestamp(left.completed_at, 0) - parseTimestamp(right.completed_at, 0);
    if (completedDiff !== 0) return completedDiff;

    return String(left.id || "").localeCompare(String(right.id || ""));
  });

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

export const mapTurnsToMessages = async (threadId: string, turns: ThreadTurn[]): Promise<ChatMessage[]> => {
  const sortedTurns = sortThreadTurnsForReplay(turns);
  const next: ChatMessage[] = [];
  const priorAssistantParts: string[] = [];
  const responseBlocksByTurnKey = new Map<string, ChatRenderBlock[] | undefined>();

  await Promise.all(
    sortedTurns.map(async (turn, index) => {
      const rawAssistantText = String(turn.assistant_output_text ?? "").trim();
      const runId = String(turn.run_id || "").trim();
      if (!rawAssistantText && !runId) return;
      const turnKey = String(turn.id ?? index);
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
        attachments: (turn.attachments || []).map((attachment) => mapRuntimeAttachment(attachment)),
      });
    } else if ((turn.attachments || []).length > 0) {
      next.push({
        id: `${threadId}:turn:${turnKey}:user`,
        role: "user",
        content: "",
        createdAt: new Date(baseTimestamp),
        attachments: (turn.attachments || []).map((attachment) => mapRuntimeAttachment(attachment)),
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

    const responseBlocks = responseBlocksByTurnKey.get(turnKey);
    if (assistantText || (responseBlocks && responseBlocks.length > 0)) {
      const assistantTimestamp = parseTimestamp(turn.completed_at, baseTimestamp + 1);
      next.push({
        id: `${threadId}:turn:${turnKey}:assistant`,
        role: "assistant",
        content: assistantText,
        createdAt: new Date(assistantTimestamp),
        runId: String(turn.run_id || "").trim() || undefined,
        responseBlocks,
        tokenUsage: turn.run_usage
          ? {
              inputTokens: turn.run_usage.input_tokens ?? null,
              outputTokens: turn.run_usage.output_tokens ?? null,
              totalTokens: turn.run_usage.total_tokens ?? null,
              usageSource: turn.run_usage.source ?? null,
            }
          : undefined,
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
  hasMoreHistory: false,
  nextBeforeTurnIndex: null,
  isLoadingOlderHistory: false,
});

const mapDetailsItem = (
  details: ThreadDetails,
  fallback?: Partial<AgentChatHistoryItem>,
  messages: ChatMessage[] = [],
): AgentChatHistoryItem => ({
  id: String(details.id || fallback?.id || fallback?.threadId || ""),
  threadId: String(details.id || fallback?.threadId || fallback?.id || ""),
  agentId: details.agent_id ? String(details.agent_id) : fallback?.agentId,
  title: String(details.title || fallback?.title || "Untitled thread"),
  timestamp: parseTimestamp(details.updated_at, fallback?.timestamp ?? Date.now()),
  messages,
  hasMoreHistory: Boolean(details.paging?.has_more),
  nextBeforeTurnIndex:
    details.paging?.next_before_turn_index === null || details.paging?.next_before_turn_index === undefined
      ? null
      : Number(details.paging.next_before_turn_index),
  isLoadingOlderHistory: fallback?.isLoadingOlderHistory ?? false,
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
      const details = (await adminService.getThread(item.threadId, { limit: DEFAULT_THREAD_PAGE_SIZE })) as ThreadDetails;
      const mappedMessages = await mapTurnsToMessages(
        item.threadId,
        Array.isArray(details.turns) ? details.turns : [],
      );
      const mapped = mapDetailsItem(details, item, mappedMessages);
      setHistory((prev) =>
        prev.map((entry) => (entry.threadId === mapped.threadId ? mapped : entry))
      );
      return mapped;
    } catch (error) {
      console.error("Failed to load thread details", error);
      return null;
    }
  }, []);

  const loadThreadById = useCallback(async (threadId: string): Promise<AgentChatHistoryItem | null> => {
    if (!threadId) return null;
    const existing = history.find((item) => item.threadId === threadId);
    if (existing) {
      return await loadThreadMessages(existing);
    }

    try {
      const details = (await adminService.getThread(threadId, { limit: DEFAULT_THREAD_PAGE_SIZE })) as ThreadDetails;
      const mappedMessages = await mapTurnsToMessages(
        threadId,
        Array.isArray(details.turns) ? details.turns : [],
      );
      const mapped = mapDetailsItem(details, { threadId, id: threadId }, mappedMessages);
      setHistory((prev) => {
        const filtered = prev.filter((entry) => entry.threadId !== mapped.threadId);
        return [mapped, ...filtered].sort((a, b) => b.timestamp - a.timestamp).slice(0, 50);
      });
      return mapped;
    } catch (error) {
      console.error("Failed to load thread by id", { threadId, error });
      return null;
    }
  }, [history, loadThreadMessages]);

  const upsertHistoryItem = useCallback((input: {
    threadId: string;
    agentId?: string;
    title: string;
    timestamp: number;
    messages: ChatMessage[];
  }) => {
    if (!input.threadId) return;
    setHistory((prev) => {
      const existing = prev.find((entry) => entry.threadId === input.threadId);
      const nextItem: AgentChatHistoryItem = {
        id: input.threadId,
        threadId: input.threadId,
        agentId: input.agentId,
        title: input.title,
        timestamp: input.timestamp,
        messages: input.messages,
        hasMoreHistory: existing?.hasMoreHistory ?? false,
        nextBeforeTurnIndex: existing?.nextBeforeTurnIndex ?? null,
        isLoadingOlderHistory: false,
      };
      const filtered = prev.filter((entry) => entry.threadId !== input.threadId);
      return [nextItem, ...filtered].sort((a, b) => b.timestamp - a.timestamp).slice(0, 50);
    });
  }, []);

  const loadOlderThreadMessages = useCallback(async (threadId: string): Promise<AgentChatHistoryItem | null> => {
    if (!threadId) return null;
    const existing = history.find((item) => item.threadId === threadId);
    if (
      !existing ||
      existing.nextBeforeTurnIndex === null ||
      existing.nextBeforeTurnIndex === undefined ||
      existing.isLoadingOlderHistory
    ) {
      return existing || null;
    }

    setHistory((prev) =>
      prev.map((entry) =>
        entry.threadId === threadId ? { ...entry, isLoadingOlderHistory: true } : entry
      )
    );
    try {
      const details = (await adminService.getThread(threadId, {
        limit: DEFAULT_THREAD_PAGE_SIZE,
        beforeTurnIndex: existing.nextBeforeTurnIndex,
      })) as ThreadDetails;
      const olderMessages = await mapTurnsToMessages(
        threadId,
        Array.isArray(details.turns) ? details.turns : [],
      );
      const mapped = mapDetailsItem(details, existing, [...olderMessages, ...existing.messages]);
      mapped.isLoadingOlderHistory = false;
      setHistory((prev) =>
        prev.map((entry) => (entry.threadId === mapped.threadId ? mapped : entry))
      );
      return mapped;
    } catch (error) {
      console.error("Failed to load older thread details", { threadId, error });
      setHistory((prev) =>
        prev.map((entry) =>
          entry.threadId === threadId ? { ...entry, isLoadingOlderHistory: false } : entry
        )
      );
      return null;
    }
  }, [history]);

  return {
    history,
    historyLoading,
    refreshHistory,
    loadThreadMessages,
    loadThreadById,
    loadOlderThreadMessages,
    upsertHistoryItem,
  };
}
