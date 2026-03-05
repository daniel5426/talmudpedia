"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { flushSync } from "react-dom";
import { nanoid } from "nanoid";
import { SearchIcon, DotIcon } from "lucide-react";
import { agentService } from "@/services";
import type { AgentExecutionEvent, AgentRunStatus } from "@/services";
import { ChatController, ChatMessage, Citation, mergeReasoningSteps } from "@/components/layout/useChatController";
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

const extractJsonFromContent = (content: string) => {
  const trimmed = content.trim();
  if (!trimmed) return null;

  if (trimmed.startsWith("```")) {
    const match = trimmed.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
    if (match && match[1]) {
      return match[1].trim();
    }
  }

  return trimmed;
};

const resolveArchitectResponse = (content: string) => {
  const candidate = extractJsonFromContent(content);
  if (!candidate) return content;

  try {
    const parsed = JSON.parse(candidate);
    if (
      parsed &&
      typeof parsed === "object" &&
      parsed.action === "respond" &&
      typeof parsed.message === "string" &&
      parsed.message.trim().length > 0
    ) {
      return parsed.message.trim();
    }
  } catch {
    // ignore JSON parse failures
  }

  return content;
};

const adaptStreamEvent = (event: any): any => {
  if (!event || event.version !== "run-stream.v2") return event;

  const payload = (event.payload && typeof event.payload === "object") ? event.payload : {};
  const eventName = String(event.event || "");

  if (eventName === "assistant.delta") {
    return { event: "token", run_id: event.run_id, data: { content: payload.content } };
  }
  if (eventName === "run.accepted") {
    return {
      event: "run_status",
      run_id: event.run_id,
      data: { status: payload.status || "running", thread_id: payload.thread_id },
    };
  }
  if (eventName === "run.completed") {
    return { event: "run_status", run_id: event.run_id, data: { status: "completed" } };
  }
  if (eventName === "run.paused") {
    return {
      event: "run_status",
      run_id: event.run_id,
      data: { status: "paused", next: payload.next, next_nodes: payload.next_nodes },
    };
  }
  if (eventName === "run.cancelled") {
    return { event: "run_status", run_id: event.run_id, data: { status: "cancelled" } };
  }
  if (eventName === "run.failed") {
    return {
      event: "error",
      run_id: event.run_id,
      data: { error: payload.error || event.diagnostics?.[0]?.message || "Agent error" },
    };
  }
  if (eventName === "tool.started") {
    return {
      event: "on_tool_start",
      run_id: event.run_id,
      span_id: payload.span_id,
      name: payload.tool,
      data: { input: payload.input, message: payload.message },
    };
  }
  if (eventName === "tool.completed") {
    return {
      event: "on_tool_end",
      run_id: event.run_id,
      span_id: payload.span_id,
      name: payload.tool,
      data: { output: payload.output },
    };
  }
  if (eventName === "tool.failed") {
    return {
      event: "error",
      run_id: event.run_id,
      span_id: payload.span_id,
      data: { error: payload.error || "Tool failed" },
    };
  }
  if (eventName === "reasoning.update") {
    return { type: "reasoning", run_id: event.run_id, data: payload };
  }
  if (eventName.startsWith("orchestration.")) {
    return {
      event: eventName,
      run_id: event.run_id,
      span_id: payload.span_id,
      name: payload.name,
      data: payload.data || payload,
      metadata: payload.metadata,
    };
  }

  return {
    event: eventName || "event",
    run_id: event.run_id,
    span_id: payload.span_id,
    name: payload.name,
    data: payload.data || payload,
    metadata: payload.metadata,
  };
};

export function useAgentRunController(agentId: string | undefined): ChatController & {
  executionSteps: ExecutionStep[];
  executionEvents: AgentExecutionEvent[];
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

      if (!trimmedContent && (!reasoning || reasoning.length === 0)) return;

      const assistantMsg: ChatMessage = {
        id: streamingId,
        role: "assistant",
        content: trimmedContent,
        createdAt: new Date(),
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
    setExecutionSteps([]);
    setExecutionEvents([]);
    setCurrentRunStatus("running");
    setLastThinkingDurationMs(null);
    const newStreamingId = nanoid();
    setActiveStreamingId(newStreamingId);
    thinkingStartRef.current = Date.now();

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
            const event = adaptStreamEvent(JSON.parse(dataStr));
            const eventName =
              typeof event.event === "string"
                ? event.event
                : typeof event.type === "string"
                ? event.type
                : "";
            if (eventName.startsWith("orchestration.") || eventName === "node_end") {
              setExecutionEvents((prev) => [...prev, { ...(event as AgentExecutionEvent), received_at: Date.now() }]);
            }
            
            if (event.type === "done") break;
            if (event.type === "error" || event.event === "error") {
              terminalError = event.error || event.data?.error || "Agent error";
              setCurrentRunStatus("failed");
              break;
            }

            // Handle unified reasoning events (Phase 3)
            if (event.type === "reasoning") {
              const stepData = event.data;
              const step = {
                id: stepData.step_id || nanoid(),
                label: stepData.step,
                status: stepData.status,
                icon: stepData.step.toLowerCase().includes("retrieval") ? SearchIcon : DotIcon,
                description: stepData.message,
                citations: stepData.citations,
                query: stepData.query,
                sources: stepData.sources,
              };
              
              setCurrentReasoning(prev => {
                const merged = mergeReasoningSteps([...(prev || []), step]);
                reasoningRef.current = merged;
                lastReasoningRef.current = merged;
                return merged;
              });
              continue; 
            }

            // Handle LangGraph Events
            if (event.event === "on_chat_model_stream") {
              // Legacy path (callback-based tokens)
              const content = event.data?.chunk?.content;
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
            } else if (event.event === "token") {
              // New explicit token event
              const content = event.data?.content;
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
            }
 else if (event.event === "run_id") {
              setCurrentRunId(event.run_id);
            } else if (event.event === "run_status") {
              const status = event.data?.status;
              const threadIdFromStatus = event.data?.thread_id;
              if (typeof threadIdFromStatus === "string" && threadIdFromStatus.trim().length > 0) {
                setCurrentThreadId(threadIdFromStatus);
              }
              if (typeof status === "string") {
                setCurrentRunStatus(status as AgentRunStatus["status"]);
              }
              if (status === "paused") {
                setIsPaused(true);
                const nextNodes = Array.isArray(event.data?.next_nodes) ? event.data.next_nodes : [];
                const next = event.data?.next;
                const nextList = Array.isArray(next) ? next : [];
                const nextTypes = nextNodes.map((node: any) => node?.type).filter(Boolean);
                const hasApproval = nextTypes.includes("user_approval") || nextList.includes("user_approval");
                setPendingApproval(hasApproval);
              } else {
                setIsPaused(false);
                setPendingApproval(false);
              }
            } else if (event.event === "on_tool_start") {
              const stepId = event.span_id || event.run_id || nanoid();
              setExecutionSteps(prev => [...prev, {
                id: stepId,
                name: event.name || "Tool",
                type: "tool",
                status: "running",
                input: event.data?.input,
                timestamp: new Date(),
              }]);
              // Reasoning update handled by 'reasoning' event now
            } else if (event.event === "on_tool_end") {
              const stepId = event.span_id || event.run_id;
              setExecutionSteps(prev => prev.map(s => s.id === stepId ? {
                ...s,
                status: "completed",
                output: event.data?.output,
              } : s));
              // Reasoning update handled by 'reasoning' event now
            } else if (event.event === "on_chain_start" || event.event === "node_start") {
              // Node execution
              const stepId = event.span_id || event.run_id || nanoid();
              setExecutionSteps(prev => [...prev, {
                id: stepId,
                name: event.name || "Node",
                type: "node",
                status: "running",
                input: event.data?.input,
                timestamp: new Date(),
              }]);
            } else if (event.event === "on_chain_end" || event.event === "node_end") {
              const stepId = event.span_id || event.run_id;
              setExecutionSteps(prev => prev.map(s => s.id === stepId ? {
                ...s,
                status: "completed",
                output: event.data?.output,
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
      const hasAssistantPayload =
        (resolvedContent && resolvedContent.trim().length > 0) ||
        (lastReasoningRef.current && lastReasoningRef.current.length > 0);
      if (hasAssistantPayload) {
        const assistantMsg: ChatMessage = {
          id: newStreamingId,
          role: "assistant",
          content: resolvedContent,
          createdAt: new Date(),
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
      setActiveStreamingId(null);
      setIsLoading(false);
      reasoningRef.current = [];
      lastReasoningRef.current = [];
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
