"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { flushSync } from "react-dom";
import { nanoid } from "nanoid";
import { SearchIcon, DotIcon, Terminal } from "lucide-react";
import { agentService } from "@/services";
import { ChatController, ChatMessage, Citation, mergeReasoningSteps } from "@/components/layout/useChatController";

export interface AgentChatHistoryItem {
  id: string;
  title: string;
  timestamp: number;
  messages: ChatMessage[];
}

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

export function useAgentRunController(agentId: string | undefined): ChatController & {
  executionSteps: ExecutionStep[];
  currentRunId: string | null;
  isPaused: boolean;
  history: AgentChatHistoryItem[];
  startNewChat: () => void;
  loadHistoryChat: (item: AgentChatHistoryItem) => void;
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
  const [isPaused, setIsPaused] = useState(false);
  const [history, setHistory] = useState<AgentChatHistoryItem[]>([]);

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

  const historyKey = agentId ? `agent-exec-history:${agentId}` : null;
  const historyLimit = 5;

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
    if (!historyKey || typeof window === "undefined") {
      setHistory([]);
      return;
    }
    try {
      const raw = window.localStorage.getItem(historyKey);
      if (!raw) {
        setHistory([]);
        return;
      }
      const parsed = JSON.parse(raw) as AgentChatHistoryItem[];
      setHistory(Array.isArray(parsed) ? parsed : []);
    } catch (error) {
      console.warn("Failed to load agent chat history", error);
      setHistory([]);
    }
  }, [historyKey]);

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
    setIsPaused(false);
    setHistory([]);
    reasoningRef.current = [];
    thinkingDurationRef.current = null;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, [agentId]);

  const persistHistory = useCallback((nextMessages: ChatMessage[]) => {
    if (!historyKey || typeof window === "undefined") return;
    if (nextMessages.length === 0) return;
    const lastMessage = nextMessages[nextMessages.length - 1];
    if (lastMessage.role !== "assistant") return;
    const firstUser = nextMessages.find((msg) => msg.role === "user");
    if (!firstUser) return;

    const title = firstUser.content.trim().slice(0, 80) || "New chat";
    const item: AgentChatHistoryItem = {
      id: nanoid(),
      title,
      timestamp: Date.now(),
      messages: nextMessages,
    };

    setHistory((prev) => {
      const last = prev[0];
      if (last && last.title === item.title && last.messages.length === item.messages.length && last.messages[last.messages.length - 1]?.content === lastMessage.content) {
        return prev;
      }
      const updated = [item, ...prev].slice(0, historyLimit);
      try {
        window.localStorage.setItem(historyKey, JSON.stringify(updated));
      } catch (error) {
        console.warn("Failed to save agent chat history", error);
      }
      return updated;
    });
  }, [historyKey]);

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

  const startNewChat = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    setStreamingContent("");
    setCurrentReasoning([]);
    setExecutionSteps([]);
    setLastThinkingDurationMs(null);
    setActiveStreamingId(null);
    setCurrentRunId(null);
    setIsPaused(false);
    reasoningRef.current = [];
    lastReasoningRef.current = [];
    thinkingDurationRef.current = null;
    setMessages([]);
  }, []);

  const loadHistoryChat = useCallback((item: AgentChatHistoryItem) => {
    if (!item) return;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    setStreamingContent("");
    setCurrentReasoning([]);
    setExecutionSteps([]);
    setLastThinkingDurationMs(null);
    setActiveStreamingId(null);
    setCurrentRunId(null);
    setIsPaused(false);
    reasoningRef.current = [];
    lastReasoningRef.current = [];
    thinkingDurationRef.current = null;
    setMessages(item.messages || []);
  }, []);

  const handleSubmit = async (message: { text: string; files: any[] }) => {
    if (!message.text.trim() || !agentId) return;

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
    setLastThinkingDurationMs(null);
    const newStreamingId = nanoid();
    setActiveStreamingId(newStreamingId);
    thinkingStartRef.current = Date.now();

    try {
      const response = await agentService.streamAgent(agentId, { 
        text: message.text,
        runId: isPaused ? currentRunId || undefined : undefined
      }, 'debug');
      setIsPaused(false); // Reset pause state when starting/resuming
      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";
      let fullAiContent = "";

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
            const event = JSON.parse(dataStr);
            
            if (event.type === "done") break;

            // Handle unified reasoning events (Phase 3)
            if (event.type === "reasoning") {
              const stepData = event.data;
              const step = {
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
              if (event.data?.status === "paused") {
                setIsPaused(true);
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
      }

      // Use the local newStreamingId to ensure it matches exactly what was used during the stream
      const resolvedContent = resolveArchitectResponse(fullAiContent);
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
    liked,
    disliked,
    copiedMessageId,
    lastThinkingDurationMs,
    activeStreamingId,
    currentRunId,
    isPaused,
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
