"use client";

import { startTransition, useState, useRef, useCallback, useEffect } from "react";
import { nanoid } from "nanoid";
import { agentService } from "@/services";
import type { AgentExecutionEvent, AgentRunStatus } from "@/services";
import type { AgentGraphDefinition } from "@/services/agent";
import { ChatController, ChatMessage, Citation } from "@/components/layout/useChatController";
import type { ChatRenderBlock } from "@/services/chat-presentation";
import type { FileUIPart } from "ai";
import {
  extractAssistantTextFromBlocks,
  sortChatRenderBlocks,
} from "@/services/chat-presentation";
import {
  loadRunTraceInspection,
  type ExecutionStep,
} from "@/services/run-trace-steps";
import { useAuthStore } from "@/lib/store/useAuthStore";
import { AgentChatHistoryItem, useAgentThreadHistory } from "./useAgentThreadHistory";

export type { ExecutionStep } from "@/services/run-trace-steps";

const resolveAssistantContentFromBlocks = (
  blocks: ChatRenderBlock[],
  fallbackContent: string,
) => {
  const assistantText = extractAssistantTextFromBlocks(blocks);

  if (assistantText) {
    return assistantText;
  }

  return fallbackContent.trim();
};

const readResponseBlocksFromPayload = (payload: Record<string, unknown>): ChatRenderBlock[] | null => {
  const blocks = payload.response_blocks;
  if (!Array.isArray(blocks)) {
    return null;
  }
  return sortChatRenderBlocks(blocks as ChatRenderBlock[]);
};

const finalizeLiveSteps = (
  steps: ExecutionStep[],
  status: "completed" | "error",
  output?: unknown,
): ExecutionStep[] =>
  steps.map((step) =>
    step.status === "running"
      ? {
          ...step,
          status,
          output: step.output !== undefined ? step.output : output,
        }
      : step,
  );

const finalizeVisibleResponseBlocks = (blocks: ChatRenderBlock[]): ChatRenderBlock[] =>
  sortChatRenderBlocks(
    blocks.map((block) => {
      if (block.kind === "assistant_text" && (block.status === "running" || block.status === "streaming")) {
        return { ...block, status: "complete" as const };
      }
      if (block.kind === "tool_call" && block.status === "running") {
        return { ...block, status: "complete" as const };
      }
      if (block.kind === "reasoning_note" && block.status === "running") {
        return { ...block, status: "complete" as const };
      }
      return block;
    }),
  );

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

  const nestedPayloadData =
    payload?.data && typeof payload.data === "object"
      ? (payload.data as Record<string, unknown>)
      : null;
  const nestedPayloadEventData =
    nestedPayloadData?.data && typeof nestedPayloadData.data === "object"
      ? (nestedPayloadData.data as Record<string, unknown>)
      : null;
  const nestedPayloadMetadata =
    nestedPayloadData?.metadata && typeof nestedPayloadData.metadata === "object"
      ? (nestedPayloadData.metadata as Record<string, unknown>)
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
          : typeof nestedPayloadData?.span_id === "string"
            ? nestedPayloadData.span_id
          : undefined,
    name:
      typeof rawEvent.name === "string"
        ? rawEvent.name
        : typeof payload?.name === "string"
          ? payload.name
          : typeof nestedPayloadData?.name === "string"
            ? nestedPayloadData.name
          : undefined,
    data:
      topLevelData ||
      nestedPayloadEventData ||
      (payload?.data && typeof payload.data === "object"
        ? (payload.data as Record<string, unknown>)
        : undefined),
    metadata:
      topLevelMetadata ||
      nestedPayloadMetadata ||
      (payload?.metadata && typeof payload.metadata === "object"
        ? (payload.metadata as Record<string, unknown>)
        : undefined),
  };
};

export function useAgentRunController(
  agentId: string | undefined,
  graphDefinition?: AgentGraphDefinition | null,
  agentSlug?: string | null,
): ChatController & {
  executionSteps: ExecutionStep[];
  executionEvents: AgentExecutionEvent[];
  currentResponseBlocks: ChatRenderBlock[];
  currentRunId: string | null;
  currentRunStatus: AgentRunStatus["status"] | null;
  currentThreadId: string | null;
  inspectedTraceCopyText: string | null;
  isPaused: boolean;
  pendingApproval: boolean;
  historyLoading: boolean;
  history: AgentChatHistoryItem[];
  hasOlderHistory: boolean;
  isLoadingOlderHistory: boolean;
  startNewChat: () => void;
  loadHistoryChat: (item: AgentChatHistoryItem) => Promise<AgentChatHistoryItem | null>;
  loadHistoryChatById: (threadId: string) => Promise<AgentChatHistoryItem | null>;
  loadOlderHistory: () => Promise<AgentChatHistoryItem | null>;
  workflowInputs: NonNullable<AgentGraphDefinition["workflow_contract"]>["inputs"];
  stateVariables: NonNullable<AgentGraphDefinition["state_contract"]>["variables"];
} {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [currentReasoning, setCurrentReasoning] = useState<ChatMessage["reasoningSteps"]>([]);
  const [currentResponseBlocks, setCurrentResponseBlocks] = useState<ChatRenderBlock[]>([]);
  const [liveExecutionSteps, setLiveExecutionSteps] = useState<ExecutionStep[]>([]);
  const [inspectedTraceSteps, setInspectedTraceSteps] = useState<ExecutionStep[] | null>(null);
  const [inspectedTraceCopyText, setInspectedTraceCopyText] = useState<string | null>(null);
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
  const workflowInputs = Array.isArray(graphDefinition?.workflow_contract?.inputs)
    ? graphDefinition.workflow_contract.inputs
    : [];
  const stateVariables = Array.isArray(graphDefinition?.state_contract?.variables)
    ? graphDefinition.state_contract.variables
    : [];

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
  const rootRunIdRef = useRef<string | null>(null);
  const currentThreadIdRef = useRef<string | null>(null);
  const lastAgentIdRef = useRef<string | undefined>(agentId);
  const authUserId = useAuthStore((state) => state.user?.id);
  const {
    history,
    historyLoading,
    refreshHistory,
    loadThreadMessages,
    loadThreadById,
    loadOlderThreadMessages,
    upsertHistoryItem,
  } = useAgentThreadHistory(authUserId, agentId);

  const runtimeContext = useCallback(
    (extra?: Record<string, unknown>) => {
      const context: Record<string, unknown> = {};
      if (agentSlug === "platform-architect") {
        context.architect_mode = "default";
      }
      if (extra && typeof extra === "object") {
        Object.assign(context, extra);
      }
      return Object.keys(context).length > 0 ? context : undefined;
    },
    [agentSlug],
  );

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
    setInspectedTraceCopyText(null);
    setLastThinkingDurationMs(null);
    setActiveStreamingId(null);
    setCurrentRunId(null);
    setCurrentRunStatus(null);
    rootRunIdRef.current = null;
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
      const responseBlocks =
        reason === "stop" || reason === "interrupt"
          ? finalizeVisibleResponseBlocks(responseBlocksRef.current)
          : sortChatRenderBlocks(responseBlocksRef.current);
      responseBlocksRef.current = responseBlocks;
      const resolvedContent = resolveAssistantContentFromBlocks(responseBlocks, trimmedContent);

      if (!resolvedContent && (!reasoning || reasoning.length === 0) && responseBlocks.length === 0) return;

      const assistantMsg: ChatMessage = {
        id: streamingId,
        role: "assistant",
        content: resolvedContent,
        createdAt: new Date(),
        runId: rootRunIdRef.current || currentRunIdRef.current || undefined,
        responseBlocks: responseBlocks.length > 0 ? responseBlocks : undefined,
        animateResponseBlocks: responseBlocks.length > 0,
        reasoningSteps: reasoning && reasoning.length > 0 ? reasoning : undefined,
        thinkingDurationMs: thinkingDurationRef.current || undefined,
      };

      setMessages((prev) => {
        if (prev.some((msg) => msg.id === assistantMsg.id)) return prev;
        const next = [...prev, assistantMsg];
        persistHistory(next);
        return next;
      });
    },
    [persistHistory]
  );

  const handleStop = useCallback(() => {
    const partialText = streamingContentRef.current.trim();
    const runId = rootRunIdRef.current || currentRunIdRef.current;
    commitStreamingMessage("stop");
    setLiveExecutionSteps((prev) =>
      finalizeLiveSteps(prev, "error", { error: "Run cancelled" }),
    );
    if (runId) {
      setExecutionEvents((prev) => [
        ...prev,
        {
          event: "run.cancelled",
          run_id: runId,
          data: { status: "cancelled" },
          received_at: Date.now(),
        } as AgentExecutionEvent,
      ]);
    }
    if (runId) {
      void agentService.cancelRun(runId, {
        assistantOutputText: partialText || undefined,
      }).catch((error) => {
        console.error("Failed to cancel run", { runId, error });
      });
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
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
    rootRunIdRef.current = null;
    setIsPaused(false);
    setPendingApproval(false);
    setInspectedTraceSteps(null);
    setInspectedTraceCopyText(null);
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

  const loadOlderHistory = useCallback(async (): Promise<AgentChatHistoryItem | null> => {
    const threadId = currentThreadIdRef.current;
    if (!threadId) return null;
    const resolved = await loadOlderThreadMessages(threadId);
    if (!resolved) return null;
    setMessages(resolved.messages || []);
    return resolved;
  }, [loadOlderThreadMessages]);

  const serializeConversationMessages = useCallback((source: ChatMessage[]) => {
    return source
      .filter((msg) => (msg.role === "user" || msg.role === "assistant") && typeof msg.content === "string")
      .map((msg) => ({
        role: msg.role,
        content: msg.content,
      }));
  }, []);

  const handleSubmit = async (message: { text: string; files: FileUIPart[]; state?: Record<string, unknown> }) => {
    const seededState = message.state && typeof message.state === "object" ? message.state : {};
    if ((!message.text.trim() && message.files.length === 0 && Object.keys(seededState).length === 0) || !agentId) return;

    const isApprovalResume = isPaused && pendingApproval;
    const approvalDecision = isApprovalResume ? message.text.trim().toLowerCase() : null;

    commitStreamingMessage("new");
    handleStop();
    setInspectedTraceSteps(null);
    setInspectedTraceCopyText(null);
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
    startTransition(() => {
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
    rootRunIdRef.current = null;
    currentRunIdRef.current = null;
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
          state: Object.keys(seededState).length > 0 ? seededState : undefined,
          runId: isPaused ? currentRunId || undefined : undefined,
          threadId: currentThreadIdRef.current || undefined,
          context: runtimeContext(isPaused && pendingApproval ? { approval: message.text } : undefined),
        },
        'debug'
      );
      const responseThreadId = response.headers.get("X-Thread-ID");
      if (responseThreadId) {
        setCurrentThreadId(responseThreadId);
      }
      const responseRunId = response.headers.get("X-Run-ID");
      if (responseRunId && responseRunId.trim().length > 0) {
        rootRunIdRef.current = responseRunId;
        currentRunIdRef.current = responseRunId;
        setCurrentRunId(responseRunId);
      }
      setIsPaused(false); // Reset pause state when starting/resuming
      setPendingApproval(false);
      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";
      let terminalError: string | null = null;
      let latestRunId: string | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const dataStr = line.slice(6).trim();
          if (dataStr === "[DONE]") break;

          try {
            const rawEvent = JSON.parse(dataStr) as Record<string, unknown>;
            const normalizedEvent = normalizeExecutionEvent(rawEvent);
            const eventName = String(rawEvent.event || "");
            const payload =
              rawEvent.payload && typeof rawEvent.payload === "object"
                ? (rawEvent.payload as Record<string, unknown>)
                : {};
            const eventData =
              normalizedEvent.data && typeof normalizedEvent.data === "object"
                ? normalizedEvent.data
                : payload;
            const payloadResponseBlocks = readResponseBlocksFromPayload(payload);
            if (typeof rawEvent.run_id === "string" && rawEvent.run_id.trim().length > 0) {
              if (!rootRunIdRef.current) {
                rootRunIdRef.current = rawEvent.run_id;
              }
              latestRunId = rootRunIdRef.current;
              currentRunIdRef.current = rootRunIdRef.current;
              setCurrentRunId(rootRunIdRef.current);
            }

            if (
              eventName.startsWith("orchestration.") ||
              eventName === "tool.child_run_started" ||
              eventName === "tool.started" ||
              eventName === "tool.completed" ||
              eventName === "tool.failed" ||
              eventName === "run.failed" ||
              eventName === "run.cancelled" ||
              eventName === "run.completed" ||
              eventName === "node_start" ||
              eventName === "node_end" ||
              eventName === "on_chain_start" ||
              eventName === "on_chain_end"
            ) {
              setExecutionEvents((prev) => [...prev, { ...normalizedEvent, received_at: Date.now() }]);
            }

            if (payloadResponseBlocks) {
              const nextBlocks = sortChatRenderBlocks(payloadResponseBlocks);
              const nextAssistantText = extractAssistantTextFromBlocks(nextBlocks);
              responseBlocksRef.current = nextBlocks;
              setCurrentResponseBlocks(nextBlocks);
              setStreamingContent(nextAssistantText);
              streamingContentRef.current = nextAssistantText;
              if (thinkingStartRef.current && nextAssistantText) {
                const duration = Date.now() - thinkingStartRef.current;
                thinkingDurationRef.current = duration;
                setLastThinkingDurationMs(duration);
                thinkingStartRef.current = null;
              }
            } else if (eventName === "assistant.delta") {
              const content = String(payload.content || "");
              if (content) {
                const nextContent = `${streamingContentRef.current}${content}`;
                setStreamingContent(nextContent);
                streamingContentRef.current = nextContent;
                if (thinkingStartRef.current) {
                  const duration = Date.now() - thinkingStartRef.current;
                  thinkingDurationRef.current = duration;
                  setLastThinkingDurationMs(duration);
                  thinkingStartRef.current = null;
                }
              }
            }

            if (eventName === "run.failed") {
              terminalError = String(eventData.error || (Array.isArray(rawEvent.diagnostics) ? (rawEvent.diagnostics[0] as Record<string, unknown> | undefined)?.message : "") || "Agent error");
              setLiveExecutionSteps((prev) =>
                finalizeLiveSteps(prev, "error", { error: terminalError || "Agent error" }),
              );
              setCurrentRunStatus("failed");
              break;
            }

            if (
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
              if (status === "completed") {
                setLiveExecutionSteps((prev) => finalizeLiveSteps(prev, "completed"));
              } else if (status === "cancelled") {
                setLiveExecutionSteps((prev) =>
                  finalizeLiveSteps(prev, "error", { error: "Run cancelled" }),
                );
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
                nodeId: typeof eventData.source_node_id === "string" ? eventData.source_node_id : undefined,
                spanId: stepId,
                name: String(eventData.display_name || eventData.summary || eventData.tool || "Tool"),
                type: "tool",
                status: "running",
                input: eventData.input,
                timestamp: new Date(),
              }]);
            } else if (eventName === "tool.completed") {
              const stepId = String(payload.span_id || rawEvent.run_id || "");
              setLiveExecutionSteps(prev => prev.map(s => s.id === stepId ? {
                ...s,
                nodeId: s.nodeId || (typeof eventData.source_node_id === "string" ? eventData.source_node_id : undefined),
                status: "completed",
                output: s.output !== undefined ? s.output : payload.output,
              } : s));
            } else if (eventName === "tool.failed") {
              const stepId = String(payload.span_id || rawEvent.run_id || "");
              setLiveExecutionSteps(prev => prev.map(s => s.id === stepId ? {
                ...s,
                nodeId: s.nodeId || (typeof eventData.source_node_id === "string" ? eventData.source_node_id : undefined),
                status: "error",
                output: s.output !== undefined ? s.output : { error: payload.error || "Tool failed" },
              } : s));
            } else if (eventName === "node_start" || eventName === "on_chain_start") {
              const data = normalizedEvent.data || {};
              const stepId = String(normalizedEvent.span_id || normalizedEvent.run_id || nanoid());
              setLiveExecutionSteps(prev => [...prev, {
                id: stepId,
                nodeId: stepId,
                spanId: stepId,
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
                output: s.output !== undefined ? s.output : data.output,
              } : s));
            } else if (eventName === "workflow.node_output_published") {
              const stepId = String(rawEvent.span_id || eventData.node_id || "");
              const nodeName = String(eventData.node_name || "");
              setLiveExecutionSteps(prev => prev.map((step) => step.id === stepId ? {
                ...step,
                nodeId: step.nodeId || stepId || undefined,
                name: nodeName || step.name,
                output: eventData.published_output !== undefined ? eventData.published_output : step.output,
              } : step));
            } else if (eventName === "workflow.end_materialized") {
              const stepId = String(rawEvent.span_id || eventData.node_id || "");
              const nodeName = String(eventData.node_name || "");
              setLiveExecutionSteps(prev => prev.map((step) => step.id === stepId ? {
                ...step,
                nodeId: step.nodeId || stepId || undefined,
                name: nodeName || step.name,
                output: eventData.final_output !== undefined ? eventData.final_output : step.output,
              } : step));
            }
          } catch (e) {
            console.error("Error parsing event:", e);
          }
        }
        if (terminalError) break;
      }

      // Use the local newStreamingId to ensure it matches exactly what was used during the stream
      if (terminalError) {
        const errorContent = `Error: ${terminalError}`;
        setStreamingContent(errorContent);
        streamingContentRef.current = errorContent;
      }
      const resolvedContent = streamingContentRef.current.trim();
      const finalizedBlocks = sortChatRenderBlocks(responseBlocksRef.current);
      responseBlocksRef.current = finalizedBlocks;
      const displayContent = resolveAssistantContentFromBlocks(finalizedBlocks, resolvedContent);
      const hasAssistantPayload =
        (displayContent && displayContent.trim().length > 0) ||
        finalizedBlocks.length > 0 ||
        (lastReasoningRef.current && lastReasoningRef.current.length > 0);
      if (hasAssistantPayload) {
        const assistantMsg: ChatMessage = {
          id: newStreamingId,
          role: "assistant",
          content: displayContent,
          createdAt: new Date(),
          runId: latestRunId || currentRunId || undefined,
          responseBlocks: finalizedBlocks.length > 0 ? finalizedBlocks : undefined,
          animateResponseBlocks: finalizedBlocks.length > 0,
          reasoningSteps: lastReasoningRef.current && lastReasoningRef.current.length > 0 ? lastReasoningRef.current : undefined,
          thinkingDurationMs: thinkingDurationRef.current || undefined,
        };
        setMessages(prev => {
          if (prev.some((msg) => msg.id === assistantMsg.id)) return prev;
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
      const loaded = await loadRunTraceInspection(msg.runId);
      if (!loaded) return;
      setInspectedTraceSteps(loaded.steps);
      setInspectedTraceCopyText(loaded.serialized);
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
  const activeHistoryItem =
    history.find((item) => item.threadId === effectiveCurrentThreadId) || null;

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
    inspectedTraceCopyText,
    isPaused,
    pendingApproval,
    historyLoading,
    history,
    hasOlderHistory: Boolean(activeHistoryItem?.hasMoreHistory),
    isLoadingOlderHistory: Boolean(activeHistoryItem?.isLoadingOlderHistory),
    startNewChat,
    loadHistoryChat,
    loadHistoryChatById,
    loadOlderHistory,
    workflowInputs,
    stateVariables,
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
