import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ChatRenderBlock, ChatToolCallBlock, ToolBlockStatus } from "@/lib/chat-blocks";
import {
  describeToolIntent,
  extractToolPath,
  formatDetailLabel,
  inferReasoningText,
} from "@/lib/chat-model";
import { createRuntimeClient, type RuntimeEvent } from "@/runtime-sdk";

export type StoredChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  blocks?: ChatRenderBlock[];
};

export type StoredChatSession = {
  id: string;
  threadId: string | null;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: StoredChatMessage[];
};

type BotInputPayload = {
  text: string;
};

const STORAGE_KEY = "talmudpedia-chat-classic.sessions.v2";
const SESSION_QUERY_KEY = "session";

function uid(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function buildSessionTitle(text: string): string {
  const clean = text.trim().replace(/\s+/g, " ");
  if (!clean) return "New conversation";
  return clean.length <= 42 ? clean : `${clean.slice(0, 39)}...`;
}

function readInitialSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return new URL(window.location.href).searchParams.get(SESSION_QUERY_KEY);
}

function syncSessionQuery(sessionId: string | null) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (sessionId) {
    url.searchParams.set(SESSION_QUERY_KEY, sessionId);
  } else {
    url.searchParams.delete(SESSION_QUERY_KEY);
  }
  window.history.replaceState({}, "", url);
}

function readStoredSessions(): StoredChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredChatSession[]) : [];
  } catch {
    return [];
  }
}

function extractTextChunk(event: RuntimeEvent): string {
  const payload = event.payload || event.data || {};
  if (typeof event.content === "string" && event.content) return event.content;
  if (typeof payload.content === "string" && payload.content) return payload.content;
  if (typeof payload.text === "string" && payload.text) return payload.text;
  return "";
}

function getEventKind(event: RuntimeEvent): string {
  return `${event.type || ""}:${event.event || ""}`.toLowerCase();
}

function getEventData(event: RuntimeEvent): Record<string, unknown> {
  return (event.data || event.payload || {}) as Record<string, unknown>;
}

function extractString(data: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = data[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function normalizeToolStatus(kind: string, data: Record<string, unknown>): ToolBlockStatus {
  const normalized = extractString(data, ["status", "state"]).toLowerCase();
  if (normalized === "completed" || normalized === "complete" || normalized === "done" || kind.includes("completed")) {
    return "completed";
  }
  if (normalized === "error" || normalized === "failed" || kind.includes("failed") || kind.includes("error")) {
    return "error";
  }
  if (kind.includes("stream")) {
    return "streaming";
  }
  return "running";
}

function upsertAssistantText(blocks: ChatRenderBlock[], chunk: string): ChatRenderBlock[] {
  if (!chunk) return blocks;
  const next = [...blocks];
  const last = next[next.length - 1];
  if (last?.kind === "assistant_text") {
    last.text += chunk;
    return next;
  }
  next.push({
    kind: "assistant_text",
    id: uid("assistant-text"),
    text: chunk,
  });
  return next;
}

function upsertReasoningBlock(
  blocks: ChatRenderBlock[],
  id: string,
  description: string,
  status: ToolBlockStatus,
): ChatRenderBlock[] {
  const next = [...blocks];
  const index = next.findIndex((block) => block.kind === "reasoning_note" && block.id === id);
  const item = {
    kind: "reasoning_note" as const,
    id,
    label: description,
    description,
    status,
  };
  if (index >= 0) {
    next[index] = item;
    return next;
  }
  next.push(item);
  return next;
}

function upsertToolBlock(
  blocks: ChatRenderBlock[],
  id: string,
  block: Omit<ChatToolCallBlock, "kind" | "id">,
): ChatRenderBlock[] {
  const next = [...blocks];
  const index = next.findIndex((entry) => entry.kind === "tool_call" && entry.id === id);
  const item: ChatToolCallBlock = { kind: "tool_call", id, ...block };
  if (index >= 0) {
    next[index] = item;
    return next;
  }
  next.push(item);
  return next;
}

function eventToBlocks(blocks: ChatRenderBlock[], event: RuntimeEvent): ChatRenderBlock[] {
  const kind = getEventKind(event);
  const data = getEventData(event);
  let next = upsertAssistantText(blocks, extractTextChunk(event));

  const toolName = extractString(data, ["tool", "tool_name", "toolName", "name"]);
  if (toolName || kind.includes("tool")) {
    const toolId =
      extractString(data, ["tool_call_id", "toolCallId", "call_id", "callId", "id"]) ||
      `tool-${toolName || kind}-${extractToolPath(data) || "runtime"}`;
    next = upsertToolBlock(next, toolId, {
      status: normalizeToolStatus(kind, data),
      tool: {
        toolName: toolName || "tool",
        title: describeToolIntent(toolName || "tool"),
        displayName: toolName || "tool",
        path: extractToolPath(data),
        detail: formatDetailLabel(data),
        summary: extractString(data, ["summary", "message", "description"]),
      },
    });
  } else {
    const reasoningText = inferReasoningText(kind, data);
    if (reasoningText) {
      const reasoningId =
        extractString(data, ["reasoning_id", "id", "label", "stage"]) ||
        `reasoning-${reasoningText}`;
      next = upsertReasoningBlock(next, reasoningId, reasoningText, normalizeToolStatus(kind, data));
    }
  }

  if (kind.includes("error") && !toolName) {
    next = [
      ...next,
      {
        kind: "error",
        id: uid("error"),
        text: extractString(data, ["message", "detail", "description"]) || event.content || "Runtime error",
      },
    ];
  }

  return next;
}

function syncMessageContent(message: StoredChatMessage): StoredChatMessage {
  const content = (message.blocks || [])
    .filter((block) => block.kind === "assistant_text")
    .map((block) => block.text)
    .join("");
  return { ...message, content: content || message.content };
}

export function useTemplateChat() {
  const runtime = useMemo(() => createRuntimeClient(), []);
  const [sessions, setSessions] = useState<StoredChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingAssistantId, setStreamingAssistantId] = useState<string | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const stored = readStoredSessions();
    const initialSessionId = readInitialSessionId();
    setSessions(stored);
    if (initialSessionId && stored.some((session) => session.id === initialSessionId)) {
      setActiveSessionId(initialSessionId);
    } else if (stored[0]) {
      setActiveSessionId(stored[0].id);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  }, [sessions]);

  useEffect(() => {
    syncSessionQuery(activeSessionId);
  }, [activeSessionId]);

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) || null,
    [sessions, activeSessionId],
  );

  const updateSession = useCallback((sessionId: string, updater: (session: StoredChatSession) => StoredChatSession) => {
    setSessions((current) =>
      current.map((session) => (session.id === sessionId ? updater(session) : session)),
    );
  }, []);

  const selectSession = useCallback((sessionId: string) => {
    setRuntimeError(null);
    setActiveSessionId(sessionId);
  }, []);

  const startNewChat = useCallback(() => {
    setRuntimeError(null);
    setActiveSessionId(null);
  }, []);

  const removeSession = useCallback(
    (sessionId: string) => {
      const remaining = sessions.filter((session) => session.id !== sessionId);
      setSessions(remaining);
      setActiveSessionId((current) => (current === sessionId ? remaining[0]?.id || null : current));
    },
    [sessions],
  );

  const shareSession = useCallback((sessionId: string) => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    url.searchParams.set(SESSION_QUERY_KEY, sessionId);
    void navigator.clipboard.writeText(url.toString());
  }, []);

  const copyMessage = useCallback((content: string) => {
    void navigator.clipboard.writeText(content);
  }, []);

  const stopStreaming = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  const sendPrompt = useCallback(
    async (text: string) => {
      const prompt = text.trim();
      if (!prompt || isStreaming) return;

      setRuntimeError(null);
      const now = new Date().toISOString();
      const userMessage: StoredChatMessage = {
        id: uid("user"),
        role: "user",
        content: prompt,
        createdAt: now,
      };
      const assistantMessage: StoredChatMessage = {
        id: uid("assistant"),
        role: "assistant",
        content: "",
        createdAt: now,
        blocks: [],
      };

      const existingSession = activeSession;
      const session =
        existingSession ||
        ({
          id: uid("session"),
          threadId: null,
          title: buildSessionTitle(prompt),
          createdAt: now,
          updatedAt: now,
          messages: [],
        } satisfies StoredChatSession);

      const nextSession: StoredChatSession = {
        ...session,
        title: session.messages.length === 0 ? buildSessionTitle(prompt) : session.title,
        updatedAt: now,
        messages: [...session.messages, userMessage, assistantMessage],
      };

      setSessions((current) => {
        const hasExisting = current.some((candidate) => candidate.id === nextSession.id);
        if (hasExisting) {
          return current.map((candidate) => (candidate.id === nextSession.id ? nextSession : candidate));
        }
        return [nextSession, ...current];
      });
      setActiveSessionId(nextSession.id);
      setIsStreaming(true);
      setStreamingAssistantId(assistantMessage.id);
      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const result = await runtime.stream(
          {
            input: prompt,
            messages: nextSession.messages
              .filter((message) => message.id !== assistantMessage.id)
              .map((message) => ({ role: message.role, content: message.content })),
            thread_id: nextSession.threadId || undefined,
          },
          (event) => {
            updateSession(nextSession.id, (currentSession) => ({
              ...currentSession,
              updatedAt: new Date().toISOString(),
              messages: currentSession.messages.map((message) => {
                if (message.id !== assistantMessage.id) return message;
                return syncMessageContent({
                  ...message,
                  blocks: eventToBlocks(message.blocks || [], event),
                });
              }),
            }));
          },
          { signal: controller.signal },
        );

        updateSession(nextSession.id, (currentSession) => ({
          ...currentSession,
          threadId: result.threadId || currentSession.threadId,
          updatedAt: new Date().toISOString(),
        }));
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        const message = error instanceof Error ? error.message : "Failed to stream runtime response";
        setRuntimeError(message);
        updateSession(nextSession.id, (currentSession) => ({
          ...currentSession,
          updatedAt: new Date().toISOString(),
          messages: currentSession.messages.map((entry) => {
            if (entry.id !== assistantMessage.id) return entry;
            return syncMessageContent({
              ...entry,
              blocks: [
                ...(entry.blocks || []),
                {
                  kind: "error",
                  id: uid("error"),
                  text: message,
                },
              ],
            });
          }),
        }));
      } finally {
        abortControllerRef.current = null;
        setIsStreaming(false);
        setStreamingAssistantId(null);
      }
    },
    [activeSession, isStreaming, runtime, updateSession],
  );

  const handleSubmit = useCallback(
    ({ text }: BotInputPayload) => sendPrompt(text),
    [sendPrompt],
  );

  const resendPrompt = useCallback(
    async (text: string) => {
      await sendPrompt(text);
    },
    [sendPrompt],
  );

  return {
    sessions,
    activeSession,
    activeSessionId,
    isStreaming,
    streamingAssistantId,
    runtimeError,
    textareaRef,
    selectSession,
    startNewChat,
    removeSession,
    shareSession,
    resendPrompt,
    copyMessage,
    handleSubmit,
    stopStreaming,
  };
}
