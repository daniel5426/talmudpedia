"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { flushSync } from "react-dom";
import { nanoid } from "nanoid";
import { agentService } from "@/services";
import type { AgentExecutionEvent, AgentRunStatus } from "@/services";
import { ChatController, ChatMessage, Citation } from "@/components/layout/useChatController";
import type { ChatRenderBlock } from "@/services/chat-presentation";
import {
  adaptRunStreamEvent,
  applyRunStreamEventToBlocks,
  extractStructuredAssistantText,
  finalizeAssistantRenderBlocks,
  sortChatRenderBlocks,
} from "@/services/chat-presentation";
import { useAuthStore } from "@/lib/store/useAuthStore";
import { AgentChatHistoryItem, useAgentThreadHistory } from "./useAgentThreadHistory";

export interface ExecutionStep {
  id: string;
  name: string;
  type: string;
  status: "pending" | "running" | "completed" | "error";
  input?: any;
  output?: any;
  timestamp: Date;
}

const resolveArchitectResponse = (content: string) => {
  return extractStructuredAssistantText(content) || content;
};

export function useAgentRunController(agentId: string | undefined): ChatController & {
  executionSteps: ExecutionStep[];
  executionEvents: AgentExecutionEvent[];
  currentResponseBlocks: ChatRenderBlock[];
  currentRunId: string | null;
  currentRunStatus: AgentRunStatus["status"] | null;
  isPaused: boolean;
  pendingApproval: boolean;
  historyLoading: boolean;
  history: AgentChatHistoryItem[];
  startNewChat: () => void;
  loadHistoryChat: (item: AgentChatHistoryItem) => Promise<AgentChatHistoryItem | null>;
} {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [currentReasoning, setCurrentReasoning] = useState<ChatMessage["reasoningSteps"]>([]);
  const [currentResponseBlocks, setCurrentResponseBlocks] = useState<ChatRenderBlock[]>([]);
  const [executionSteps, setExecutionSteps] = useState<ExecutionStep[]>([]);
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
  const currentThreadIdRef = useRef<string | null>(null);
  const authUserId = useAuthStore((state) => state.user?.id);
  const {
    history,
    historyLoading,
    refreshHistory,
    loadThreadMessages,
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
    currentThreadIdRef.current = currentThreadId;
  }, [currentThreadId]);

  // Reset state when agentId changes
  useEffect(() => {
    setMessages([]);
    setIsLoading(false);
    setStreamingContent("");
    setCurrentReasoning([]);
    setCurrentResponseBlocks([]);
    setExecutionSteps([]);
    setLastThinkingDurationMs(null);
    setActiveStreamingId(null);
    setCurrentRunId(null);
    setCurrentRunStatus(null);
    setCurrentThreadId(null);
    setIsPaused(false);
    setPendingApproval(false);
    setExecutionEvents([]);
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
        if (reason !== "stop") {
          persistHistory(next);
        }
        return next;
      });
    },
    [persistHistory]
  );

  const handleStop = useCallback(() => {
    commitStreamingMessage("stop");
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setActiveStreamingId(null);
    setStreamingContent("");
    setCurrentReasoning([]);
    setCurrentResponseBlocks([]);
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
    setExecutionSteps([]);
    setExecutionEvents([]);
    setLastThinkingDurationMs(null);
    setActiveStreamingId(null);
    setCurrentRunId(null);
    setCurrentRunStatus(null);
    setCurrentThreadId(null);
    setIsPaused(false);
    setPendingApproval(false);
    reasoningRef.current = [];
    lastReasoningRef.current = [];
    responseBlocksRef.current = [];
    thinkingDurationRef.current = null;
    currentThreadIdRef.current = null;
  }, []);

  const startNewChat = useCallback(() => {
    resetExecutionState();
    setMessages([]);
  }, [resetExecutionState]);

  const loadHistoryChat = useCallback(async (item: AgentChatHistoryItem): Promise<AgentChatHistoryItem | null> => {
    if (!item) return null;
    const resolved = await loadThreadMessages(item);
    if (!resolved) return null;
    resetExecutionState();
    setCurrentThreadId(resolved.threadId || item.threadId || null);
    setMessages(resolved.messages || []);
    return resolved;
  }, [loadThreadMessages, resetExecutionState]);

  const serializeConversationMessages = useCallback((source: ChatMessage[]) => {
    return source
      .filter((msg) => (msg.role === "user" || msg.role === "assistant") && typeof msg.content === "string")
      .map((msg) => ({
        role: msg.role,
        content: msg.content,
      }));
  }, []);

  const handleSubmit = async (message: { text: string; files: any[] }) => {
    if (!message.text.trim() || !agentId) return;

    const isApprovalResume = isPaused && pendingApproval;
    const approvalDecision = isApprovalResume ? message.text.trim().toLowerCase() : null;

    commitStreamingMessage("new");
    handleStop();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const userMsg: ChatMessage = {
      id: nanoid(),
      role: "user",
      content: message.text,
      createdAt: new Date(),
    };

    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);
    setStreamingContent("");
    setCurrentReasoning([]);
    setCurrentResponseBlocks([]);
    setExecutionSteps([]);
    setExecutionEvents([]);
    setCurrentRunStatus("running");
    setLastThinkingDurationMs(null);
    const newStreamingId = nanoid();
    setActiveStreamingId(newStreamingId);
    thinkingStartRef.current = Date.now();
    responseBlocksRef.current = [];

    try {
      // New runs must include full prior conversation history; the backend will append request.input as the latest user turn.
      const priorMessages = !isPaused ? serializeConversationMessages(messagesRef.current) : undefined;
      const response = await agentService.streamAgent(
        agentId,
        {
          text: message.text,
          messages: priorMessages,
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
            const eventName = String(rawEvent.event || "");
            const payload =
              rawEvent.payload && typeof rawEvent.payload === "object"
                ? (rawEvent.payload as Record<string, unknown>)
                : {};
            if (typeof rawEvent.run_id === "string" && rawEvent.run_id.trim().length > 0) {
              setCurrentRunId(rawEvent.run_id);
            }

            if (eventName.startsWith("orchestration.") || eventName === "node_end") {
              setExecutionEvents((prev) => [...prev, { ...(rawEvent as AgentExecutionEvent), received_at: Date.now() }]);
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
              setExecutionSteps(prev => [...prev, {
                id: stepId,
                name: String(payload.display_name || payload.summary || payload.tool || "Tool"),
                type: "tool",
                status: "running",
                input: payload.input,
                timestamp: new Date(),
              }]);
            } else if (eventName === "tool.completed") {
              const stepId = String(payload.span_id || rawEvent.run_id || "");
              setExecutionSteps(prev => prev.map(s => s.id === stepId ? {
                ...s,
                status: "completed",
                output: payload.output,
              } : s));
            } else if (eventName === "node_start" || eventName === "on_chain_start") {
              const data = rawEvent.data && typeof rawEvent.data === "object" ? rawEvent.data as Record<string, unknown> : {};
              const stepId = String(rawEvent.span_id || rawEvent.run_id || nanoid());
              setExecutionSteps(prev => [...prev, {
                id: stepId,
                name: String(rawEvent.name || "Node"),
                type: "node",
                status: "running",
                input: data.input,
                timestamp: new Date(),
              }]);
            } else if (eventName === "node_end" || eventName === "on_chain_end") {
              const data = rawEvent.data && typeof rawEvent.data === "object" ? rawEvent.data as Record<string, unknown> : {};
              const stepId = String(rawEvent.span_id || rawEvent.run_id || "");
              setExecutionSteps(prev => prev.map(s => s.id === stepId ? {
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
          runId: currentRunId || newStreamingId,
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
      const userText = messages[idx-1].content;
      setMessages(prev => prev.slice(0, idx-1));
      handleSubmit({ text: userText, files: [] });
    }
  };

  const handleSourceClick = useCallback((citations: Citation[] | undefined) => {
    console.log("Source click:", citations);
  }, []);

  const upsertLiveVoiceMessage = useCallback(() => {}, []);
  const refresh = useCallback(async () => {}, []);

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
    isPaused,
    pendingApproval,
    historyLoading,
    history,
    startNewChat,
    loadHistoryChat,
    handleSubmit,
    handleStop,
    handleCopy,
    handleLike,
    handleDislike,
    handleRetry,
    handleSourceClick,
    upsertLiveVoiceMessage,
    refresh,
    textareaRef,
  };
}
