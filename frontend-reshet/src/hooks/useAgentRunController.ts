"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { flushSync } from "react-dom";
import { nanoid } from "nanoid";
import { agentService } from "@/services";
import type { AgentExecutionEvent, AgentRunStatus } from "@/services";
import { ChatController, ChatMessage, Citation } from "@/components/layout/useChatController";
import type { ChatRenderBlock } from "@/services/chat-presentation";
import type { FileUIPart } from "ai";
import {
  adaptRunStreamEvent,
  applyRunStreamEventToBlocks,
  extractStructuredAssistantText,
  finalizeAssistantRenderBlocks,
  sortChatRenderBlocks,
} from "@/services/chat-presentation";
import {
  buildExecutionStepsFromRunTrace,
  type ExecutionStep,
} from "@/services/run-trace-steps";
import { useAuthStore } from "@/lib/store/useAuthStore";
import { AgentChatHistoryItem, useAgentThreadHistory } from "./useAgentThreadHistory";

export type { ExecutionStep } from "@/services/run-trace-steps";

const resolveArchitectResponse = (content: string) => {
  return extractStructuredAssistantText(content) || content;
};

const logRunControllerDebug = (event: string, details?: Record<string, unknown>) => {
  if (process.env.NODE_ENV === "production") return;
  console.debug("[playground-controller-debug]", event, details || {});
};

const normalizeExecutionEvent = (rawEvent: Record<string, unknown>): AgentExecutionEvent => {
  const payload =
    rawEvent.payload && typeof rawEvent.payload === "object"
      ? (rawEvent.payload as Record<string, unknown>)
      : null;

  const topLevelData =
    rawEvent.data && typeof rawEvent.data === "object"
      ? (rawEvent.data as Record<string, unknown>)
      : null;
  const topLevelMetadata =
    rawEvent.metadata && typeof rawEvent.metadata === "object"
      ? (rawEvent.metadata as Record<string, unknown>)
      : null;

  return {
    event: typeof rawEvent.event === "string" ? rawEvent.event : undefined,
    type: typeof rawEvent.type === "string" ? rawEvent.type : undefined,
    run_id: typeof rawEvent.run_id === "string" ? rawEvent.run_id : undefined,
    seq: typeof rawEvent.seq === "number" ? rawEvent.seq : undefined,
    ts: typeof rawEvent.ts === "string" ? rawEvent.ts : undefined,
    span_id:
      typeof rawEvent.span_id === "string"
        ? rawEvent.span_id
        : typeof payload?.span_id === "string"
          ? payload.span_id
          : undefined,
    name:
      typeof rawEvent.name === "string"
        ? rawEvent.name
        : typeof payload?.name === "string"
          ? payload.name
          : undefined,
    data:
      topLevelData ||
      (payload?.data && typeof payload.data === "object"
        ? (payload.data as Record<string, unknown>)
        : undefined),
    metadata:
      topLevelMetadata ||
      (payload?.metadata && typeof payload.metadata === "object"
        ? (payload.metadata as Record<string, unknown>)
        : undefined),
  };
};

export function useAgentRunController(agentId: string | undefined): ChatController & {
  executionSteps: ExecutionStep[];
  executionEvents: AgentExecutionEvent[];
  currentResponseBlocks: ChatRenderBlock[];
  currentRunId: string | null;
  currentRunStatus: AgentRunStatus["status"] | null;
  currentThreadId: string | null;
  isPaused: boolean;
  pendingApproval: boolean;
  historyLoading: boolean;
  history: AgentChatHistoryItem[];
  startNewChat: () => void;
  loadHistoryChat: (item: AgentChatHistoryItem) => Promise<AgentChatHistoryItem | null>;
  loadHistoryChatById: (threadId: string) => Promise<AgentChatHistoryItem | null>;
} {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [currentReasoning, setCurrentReasoning] = useState<ChatMessage["reasoningSteps"]>([]);
  const [currentResponseBlocks, setCurrentResponseBlocks] = useState<ChatRenderBlock[]>([]);
  const [liveExecutionSteps, setLiveExecutionSteps] = useState<ExecutionStep[]>([]);
  const [inspectedTraceSteps, setInspectedTraceSteps] = useState<ExecutionStep[] | null>(null);
  const [liked, setLiked] = useState<Record<string, boolean>>({});
  const [disliked, setDisliked] = useState<Record<string, boolean>>({});
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [lastThinkingDurationMs, setLastThinkingDurationMs] = useState<number | null>(null);
  const [activeStreamingId, setActiveStreamingId] = useState<string | null>(null);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [currentRunStatus, setCurrentRunStatus] = useState<AgentRunStatus["status"] | null>(null);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [pendingApproval, setPendingApproval] = useState(false);
  const [executionEvents, setExecutionEvents] = useState<AgentExecutionEvent[]>([]);
  const [traceLoadingByMessageId, setTraceLoadingByMessageId] = useState<Record<string, boolean>>({});

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const thinkingStartRef = useRef<number | null>(null);
  // Use refs to capture current state for final message (avoids stale closure bug)
  const reasoningRef = useRef<ChatMessage["reasoningSteps"]>([]);
  const lastReasoningRef = useRef<ChatMessage["reasoningSteps"]>([]);
  const responseBlocksRef = useRef<ChatRenderBlock[]>([]);
  const thinkingDurationRef = useRef<number | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const streamingContentRef = useRef<string>("");
  const activeStreamingIdRef = useRef<string | null>(null);
  const currentRunIdRef = useRef<string | null>(null);
  const currentThreadIdRef = useRef<string | null>(null);
  const lastAgentIdRef = useRef<string | undefined>(agentId);
  const authUserId = useAuthStore((state) => state.user?.id);
  const {
    history,
    historyLoading,
    refreshHistory,
    loadThreadMessages,
    loadThreadById,
    upsertHistoryItem,
  } = useAgentThreadHistory(authUserId);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    streamingContentRef.current = streamingContent;
  }, [streamingContent]);

  useEffect(() => {
    activeStreamingIdRef.current = activeStreamingId;
  }, [activeStreamingId]);

  useEffect(() => {
    currentRunIdRef.current = currentRunId;
  }, [currentRunId]);

  useEffect(() => {
    currentThreadIdRef.current = currentThreadId;
  }, [currentThreadId]);

  useEffect(() => {
    logRunControllerDebug("thread-id.changed", {
      agentId,
      currentThreadId,
    });
  }, [agentId, currentThreadId]);

  // Reset state when agentId changes
  useEffect(() => {
    lastAgentIdRef.current = agentId;
    setMessages([]);
    setIsLoading(false);
    setStreamingContent("");
    setCurrentReasoning([]);
    setCurrentResponseBlocks([]);
    setLiveExecutionSteps([]);
    setInspectedTraceSteps(null);
    setLastThinkingDurationMs(null);
    setActiveStreamingId(null);
    setCurrentRunId(null);
    setCurrentRunStatus(null);
    setCurrentThreadId(null);
    setIsPaused(false);
    setPendingApproval(false);
    setExecutionEvents([]);
    setTraceLoadingByMessageId({});
    reasoningRef.current = [];
    lastReasoningRef.current = [];
    responseBlocksRef.current = [];
    thinkingDurationRef.current = null;
    currentThreadIdRef.current = null;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, [agentId]);

  const persistHistory = useCallback((nextMessages: ChatMessage[]) => {
    if (nextMessages.length === 0) return;
    const threadId = currentThreadIdRef.current;
    if (!threadId) return;
    const lastMessage = nextMessages[nextMessages.length - 1];
    if (lastMessage.role !== "assistant") return;
    const firstUser = nextMessages.find((msg) => msg.role === "user");
    if (!firstUser) return;

    upsertHistoryItem({
      threadId,
      agentId: agentId || undefined,
      title: firstUser.content.trim().slice(0, 80) || "New chat",
      timestamp: Date.now(),
      messages: nextMessages,
    });
  }, [agentId, upsertHistoryItem]);

  const commitStreamingMessage = useCallback(
    (reason?: "stop" | "interrupt" | "new") => {
      const streamingId = activeStreamingIdRef.current;
      if (!streamingId) return;
      if (messagesRef.current.some((msg) => msg.id === streamingId)) return;

      const content = streamingContentRef.current;
      const trimmedContent = content.trim();
      const reasoning =
        (lastReasoningRef.current && lastReasoningRef.current.length > 0)
          ? lastReasoningRef.current
          : reasoningRef.current;
      const responseBlocks = responseBlocksRef.current;

      if (!trimmedContent && (!reasoning || reasoning.length === 0) && responseBlocks.length === 0) return;

      const assistantMsg: ChatMessage = {
        id: streamingId,
        role: "assistant",
        content: trimmedContent,
        createdAt: new Date(),
        responseBlocks: responseBlocks.length > 0 ? responseBlocks : undefined,
        reasoningSteps: reasoning && reasoning.length > 0 ? reasoning : undefined,
        thinkingDurationMs: thinkingDurationRef.current || undefined,
      };

      setMessages((prev) => {
        const next = [...prev, assistantMsg];
        persistHistory(next);
        return next;
      });
    },
    [persistHistory]
  );

  const handleStop = useCallback(() => {
    const partialText = streamingContentRef.current.trim();
    const runId = currentRunIdRef.current;
    commitStreamingMessage("stop");
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (runId) {
      void agentService.cancelRun(runId, {
        assistantOutputText: partialText || undefined,
      }).catch((error) => {
        console.error("Failed to cancel run", { runId, error });
      });
    }
    setActiveStreamingId(null);
    setStreamingContent("");
    setCurrentReasoning([]);
    setCurrentResponseBlocks([]);
    setCurrentRunStatus("cancelled");
    setIsLoading(false);
  }, [commitStreamingMessage]);

  const resetExecutionState = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    setStreamingContent("");
    setCurrentReasoning([]);
    setCurrentResponseBlocks([]);
    setLiveExecutionSteps([]);
    setExecutionEvents([]);
    setLastThinkingDurationMs(null);
    setActiveStreamingId(null);
    setCurrentRunId(null);
    setCurrentRunStatus(null);
    setCurrentThreadId(null);
    setIsPaused(false);
    setPendingApproval(false);
    setInspectedTraceSteps(null);
    reasoningRef.current = [];
    lastReasoningRef.current = [];
    responseBlocksRef.current = [];
    thinkingDurationRef.current = null;
    currentThreadIdRef.current = null;
  }, []);

  const startNewChat = useCallback(() => {
    logRunControllerDebug("start-new-chat", {
      agentId,
      currentThreadId: currentThreadIdRef.current,
      messageCount: messagesRef.current.length,
    });
    resetExecutionState();
    setMessages([]);
  }, [resetExecutionState]);

  const loadHistoryChat = useCallback(async (item: AgentChatHistoryItem): Promise<AgentChatHistoryItem | null> => {
    if (!item) return null;
    logRunControllerDebug("load-history-chat.start", {
      agentId,
      requestedThreadId: item.threadId,
      cachedMessageCount: item.messages.length,
      currentThreadId: currentThreadIdRef.current,
    });
    const resolved = await loadThreadMessages(item);
    if (!resolved) return null;
    resetExecutionState();
    setCurrentThreadId(resolved.threadId || item.threadId || null);
    setMessages(resolved.messages || []);
    logRunControllerDebug("load-history-chat.done", {
      agentId,
      resolvedThreadId: resolved.threadId || item.threadId || null,
      resolvedMessageCount: resolved.messages?.length || 0,
    });
    return resolved;
  }, [loadThreadMessages, resetExecutionState]);

  const loadHistoryChatById = useCallback(async (threadId: string): Promise<AgentChatHistoryItem | null> => {
    if (!threadId) return null;
    logRunControllerDebug("load-history-chat-by-id.start", {
      agentId,
      requestedThreadId: threadId,
      currentThreadId: currentThreadIdRef.current,
    });
    const resolved = await loadThreadById(threadId);
    if (!resolved) return null;
    resetExecutionState();
    setCurrentThreadId(resolved.threadId || threadId);
    setMessages(resolved.messages || []);
    logRunControllerDebug("load-history-chat-by-id.done", {
      agentId,
      resolvedThreadId: resolved.threadId || threadId,
      resolvedMessageCount: resolved.messages?.length || 0,
    });
    return resolved;
  }, [agentId, loadThreadById, resetExecutionState]);

  const serializeConversationMessages = useCallback((source: ChatMessage[]) => {
    return source
      .filter((msg) => (msg.role === "user" || msg.role === "assistant") && typeof msg.content === "string")
      .map((msg) => ({
        role: msg.role,
        content: msg.content,
      }));
  }, []);

  const handleSubmit = async (message: { text: string; files: FileUIPart[] }) => {
    if ((!message.text.trim() && message.files.length === 0) || !agentId) return;

    const isApprovalResume = isPaused && pendingApproval;
    const approvalDecision = isApprovalResume ? message.text.trim().toLowerCase() : null;

    commitStreamingMessage("new");
    handleStop();
    setInspectedTraceSteps(null);
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const userMsg: ChatMessage = {
      id: nanoid(),
      role: "user",
      content: message.text,
      createdAt: new Date(),
      attachments: message.files,
    };

    setMessages(prev => [...prev, userMsg]);
    flushSync(() => {
      setIsLoading(true);
      setStreamingContent("");
      setCurrentReasoning([]);
      setCurrentResponseBlocks([]);
      setLiveExecutionSteps([]);
      setExecutionEvents([]);
      setCurrentRunId(null);
      setCurrentRunStatus(null);
      setLastThinkingDurationMs(null);
    });
    const newStreamingId = nanoid();
    setActiveStreamingId(newStreamingId);
    thinkingStartRef.current = Date.now();
    responseBlocksRef.current = [];

    try {
      let attachmentIds: string[] = [];
      if (message.files.length > 0) {
        const uploaded = await agentService.uploadAgentAttachments(agentId, {
          files: message.files,
          threadId: currentThreadIdRef.current || undefined,
        });
        attachmentIds = (uploaded.items || []).map((item) => item.id);
      }
      // New runs must include full prior conversation history; the backend will append request.input as the latest user turn.
      const priorMessages = !isPaused ? serializeConversationMessages(messagesRef.current) : undefined;
      const response = await agentService.streamAgent(
        agentId,
        {
          text: message.text,
          messages: priorMessages,
          attachmentIds,
          runId: isPaused ? currentRunId || undefined : undefined,
          threadId: currentThreadIdRef.current || undefined,
          context: isPaused && pendingApproval ? { approval: message.text } : undefined,
        },
        'debug'
      );
      const responseThreadId = response.headers.get("X-Thread-ID");
      if (responseThreadId) {
        setCurrentThreadId(responseThreadId);
      }
      setIsPaused(false); // Reset pause state when starting/resuming
      setPendingApproval(false);
      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";
      let fullAiContent = "";
      let terminalError: string | null = null;
      let streamEventIndex = 0;
      let latestRunId: string | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        console.log(`[useAgentRunController] RAW CHUNK: Received ${value?.length} bytes at ${new Date().toLocaleTimeString()}`);

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const dataStr = line.slice(6).trim();
          console.log("[useAgentRunController] Received event:", dataStr.slice(0, 50));
          if (dataStr === "[DONE]") break;

          try {
            const rawEvent = JSON.parse(dataStr) as Record<string, unknown>;
            const normalizedEvent = normalizeExecutionEvent(rawEvent);
            const eventName = String(rawEvent.event || "");
            const payload =
              rawEvent.payload && typeof rawEvent.payload === "object"
                ? (rawEvent.payload as Record<string, unknown>)
                : {};
            if (typeof rawEvent.run_id === "string" && rawEvent.run_id.trim().length > 0) {
              latestRunId = rawEvent.run_id;
              setCurrentRunId(rawEvent.run_id);
            }

            if (eventName.startsWith("orchestration.") || eventName === "node_end") {
              setExecutionEvents((prev) => [...prev, { ...normalizedEvent, received_at: Date.now() }]);
            }

            const nextBlocks = sortChatRenderBlocks(
              applyRunStreamEventToBlocks(
                responseBlocksRef.current,
                adaptRunStreamEvent(rawEvent, streamEventIndex++),
              ),
            );
            responseBlocksRef.current = nextBlocks;
            setCurrentResponseBlocks(nextBlocks);

            if (eventName === "run.failed") {
              terminalError = String(payload.error || (Array.isArray(rawEvent.diagnostics) ? (rawEvent.diagnostics[0] as Record<string, unknown> | undefined)?.message : "") || "Agent error");
              setCurrentRunStatus("failed");
              break;
            }

            if (eventName === "assistant.delta") {
              const content = String(payload.content || "");
              if (content) {
                fullAiContent += content;
                flushSync(() => setStreamingContent(fullAiContent));

                if (thinkingStartRef.current) {
                  const duration = Date.now() - thinkingStartRef.current;
                  thinkingDurationRef.current = duration;
                  setLastThinkingDurationMs(duration);
                  thinkingStartRef.current = null;
                }
              }
            } else if (
              eventName === "run.accepted" ||
              eventName === "run.completed" ||
              eventName === "run.paused" ||
              eventName === "run.cancelled"
            ) {
              const status =
                eventName === "run.completed"
                  ? "completed"
                  : eventName === "run.paused"
                    ? "paused"
                    : eventName === "run.cancelled"
                      ? "cancelled"
                      : String(payload.status || "running");
              const threadIdFromStatus = payload.thread_id;
              if (typeof threadIdFromStatus === "string" && threadIdFromStatus.trim().length > 0) {
                setCurrentThreadId(threadIdFromStatus);
              }
              setCurrentRunStatus(status as AgentRunStatus["status"]);
              if (status === "paused") {
                setIsPaused(true);
                const nextNodes = Array.isArray(payload.next_nodes) ? payload.next_nodes : [];
                const next = payload.next;
                const nextList = Array.isArray(next) ? next : [];
                const nextTypes = nextNodes.map((node: any) => node?.type).filter(Boolean);
                const hasApproval = nextTypes.includes("user_approval") || nextList.includes("user_approval");
                setPendingApproval(hasApproval);
              } else {
                setIsPaused(false);
                setPendingApproval(false);
              }
            } else if (eventName === "tool.started") {
              const stepId = String(payload.span_id || rawEvent.run_id || nanoid());
              setLiveExecutionSteps(prev => [...prev, {
                id: stepId,
                name: String(payload.display_name || payload.summary || payload.tool || "Tool"),
                type: "tool",
                status: "running",
                input: payload.input,
                timestamp: new Date(),
              }]);
            } else if (eventName === "tool.completed") {
              const stepId = String(payload.span_id || rawEvent.run_id || "");
              setLiveExecutionSteps(prev => prev.map(s => s.id === stepId ? {
                ...s,
                status: "completed",
                output: payload.output,
              } : s));
            } else if (eventName === "node_start" || eventName === "on_chain_start") {
              const data = normalizedEvent.data || {};
              const stepId = String(normalizedEvent.span_id || normalizedEvent.run_id || nanoid());
              setLiveExecutionSteps(prev => [...prev, {
                id: stepId,
                name: String(normalizedEvent.name || "Node"),
                type: "node",
                status: "running",
                input: data.input,
                timestamp: new Date(),
              }]);
            } else if (eventName === "node_end" || eventName === "on_chain_end") {
              const data = normalizedEvent.data || {};
              const stepId = String(normalizedEvent.span_id || normalizedEvent.run_id || "");
              setLiveExecutionSteps(prev => prev.map(s => s.id === stepId ? {
                ...s,
                status: "completed",
                output: data.output,
              } : s));
            }
          } catch (e) {
            console.error("Error parsing event:", e);
          }
        }
        if (terminalError) break;
      }

      // Use the local newStreamingId to ensure it matches exactly what was used during the stream
      if (terminalError) {
        fullAiContent = `Error: ${terminalError}`;
      }
      const resolvedContent = resolveArchitectResponse(fullAiContent);
      const finalizedBlocks = sortChatRenderBlocks(
        finalizeAssistantRenderBlocks(responseBlocksRef.current, resolvedContent, {
          runId: latestRunId || currentRunId || newStreamingId,
          fallbackSeq: streamEventIndex + 1,
        }),
      );
      responseBlocksRef.current = finalizedBlocks;
      const hasAssistantPayload =
        (resolvedContent && resolvedContent.trim().length > 0) ||
        finalizedBlocks.length > 0 ||
        (lastReasoningRef.current && lastReasoningRef.current.length > 0);
      if (hasAssistantPayload) {
        const assistantMsg: ChatMessage = {
          id: newStreamingId,
          role: "assistant",
          content: resolvedContent,
          createdAt: new Date(),
          runId: latestRunId || currentRunId || undefined,
          responseBlocks: finalizedBlocks.length > 0 ? finalizedBlocks : undefined,
          reasoningSteps: lastReasoningRef.current && lastReasoningRef.current.length > 0 ? lastReasoningRef.current : undefined,
          thinkingDurationMs: thinkingDurationRef.current || undefined,
        };
        setMessages(prev => {
          const next = [...prev, assistantMsg];
          persistHistory(next);
          return next;
        });
      } else if (isApprovalResume) {
        const approved =
          approvalDecision === "approve" ||
          approvalDecision === "approved" ||
          approvalDecision === "true" ||
          approvalDecision === "yes" ||
          approvalDecision === "1";
        const rejected =
          approvalDecision === "reject" ||
          approvalDecision === "rejected" ||
          approvalDecision === "false" ||
          approvalDecision === "no" ||
          approvalDecision === "0";
        const fallbackMessage = approved
          ? "Approved."
          : rejected
          ? "Rejected."
          : "Approval received.";
        const assistantMsg: ChatMessage = {
          id: newStreamingId,
          role: "assistant",
          content: fallbackMessage,
          createdAt: new Date(),
          runId: latestRunId || currentRunId || undefined,
        };
        setMessages(prev => {
          const next = [...prev, assistantMsg];
          persistHistory(next);
          return next;
        });
      }
      setStreamingContent("");
      setCurrentReasoning([]);
      setCurrentResponseBlocks([]);
      setActiveStreamingId(null);
      setIsLoading(false);
      reasoningRef.current = [];
      lastReasoningRef.current = [];
      responseBlocksRef.current = [];
      thinkingDurationRef.current = null;
    } catch (e) {
      console.error("Agent execution failed:", e);
    } finally {
      setIsLoading(false);
      thinkingStartRef.current = null;
      void refreshHistory();
    }
  };

  const handleCopy = useCallback((content: string, messageId: string) => {
    navigator.clipboard.writeText(content);
    setCopiedMessageId(messageId);
    setTimeout(() => setCopiedMessageId(null), 2000);
  }, []);

  const handleLike = async (msg: ChatMessage) => {
    setLiked(prev => ({ ...prev, [msg.id]: !prev[msg.id] }));
    if (disliked[msg.id]) setDisliked(prev => ({ ...prev, [msg.id]: false }));
  };

  const handleDislike = async (msg: ChatMessage) => {
    setDisliked(prev => ({ ...prev, [msg.id]: !prev[msg.id] }));
    if (liked[msg.id]) setLiked(prev => ({ ...prev, [msg.id]: false }));
  };

  const handleRetry = async (msg: ChatMessage) => {
    const idx = messages.findIndex(m => m.id === msg.id);
    if (idx > 0 && messages[idx-1].role === "user") {
      const userMessage = messages[idx - 1];
      const userText = userMessage.content;
      setMessages(prev => prev.slice(0, idx-1));
      handleSubmit({
        text: userText,
        files: (userMessage.attachments || []).filter(
          (attachment): attachment is FileUIPart => Boolean(attachment?.url),
        ),
      });
    }
  };

  const handleLoadTrace = useCallback(async (msg: ChatMessage) => {
    if (!msg.runId) return;
    setTraceLoadingByMessageId((prev) => ({ ...prev, [msg.id]: true }));
    try {
      const steps = await buildExecutionStepsFromRunTrace(msg.runId);
      if (!steps || steps.length === 0) return;
      setInspectedTraceSteps(steps);
    } catch (error) {
      console.error("Failed to load run trace", { runId: msg.runId, error });
    } finally {
      setTraceLoadingByMessageId((prev) => ({ ...prev, [msg.id]: false }));
    }
  }, []);

  const handleSourceClick = useCallback((citations: Citation[] | undefined) => {
    console.log("Source click:", citations);
  }, []);

  const upsertLiveVoiceMessage = useCallback(() => {}, []);
  const refresh = useCallback(async () => {}, []);
  const executionSteps = inspectedTraceSteps ?? liveExecutionSteps;
  const effectiveCurrentThreadId =
    lastAgentIdRef.current === agentId ? currentThreadId : null;

  return {
    messages,
    isLoading,
    isLoadingHistory: false,
    streamingContent,
    currentReasoning,
    currentResponseBlocks,
    executionSteps,
    executionEvents,
    liked,
    disliked,
    copiedMessageId,
    lastThinkingDurationMs,
    activeStreamingId,
    currentRunId,
    currentRunStatus,
    currentThreadId: effectiveCurrentThreadId,
    isPaused,
    pendingApproval,
    historyLoading,
    history,
    startNewChat,
    loadHistoryChat,
    loadHistoryChatById,
    handleSubmit,
    handleStop,
    handleCopy,
    handleLike,
    handleDislike,
    handleRetry,
    handleLoadTrace,
    handleSourceClick,
    traceLoadingByMessageId,
    upsertLiveVoiceMessage,
    refresh,
    textareaRef,
  };
}
