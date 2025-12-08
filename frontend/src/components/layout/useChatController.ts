"use client";

import { useState, useEffect, useRef, useCallback, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { flushSync } from "react-dom";
import type { FileUIPart } from "ai";
import type { LucideIcon } from "lucide-react";
import { SearchIcon, DotIcon } from "lucide-react";
import { nanoid } from "nanoid";
import { chatService } from "@/services";
import { useAuthStore } from "@/lib/store/useAuthStore";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { hasPendingChatMessage } from "@/lib/chatPrefill";
import {
  ChatErrorTypes,
  isIgnorableError,
  processFilesForUpload,
  AbortControllerManager,
} from "@/lib/chatUtils";

export interface Citation {
  title: string;
  url: string;
  description: string;
  sourceRef?: string;
  ref?: string;
}
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: Date;
  attachments?: FileUIPart[];
  citations?: Citation[];
  reasoningSteps?: Array<{
    label: string;
    status: "active" | "complete" | "pending";
    icon: LucideIcon;
    description?: string;
    citations?: Citation[];
    query?: string;
    sources?: Array<Record<string, unknown>>;
  }>;
  thinkingDurationMs?: number;
  liked?: boolean;
  disliked?: boolean;
  messageIndex?: number;
}

const normalizeReasoningStatus = (
  status?: string
): "active" | "complete" | "pending" => {
  if (status === "active" || status === "pending" || status === "complete") {
    return status;
  }
  return "complete";
};

const getReasoningLabelKey = (label: ReactNode) => {
  if (typeof label === "string") return label;
  if (typeof label === "number") return label.toString();
  if (typeof label === "boolean") return label ? "true" : "false";
  return JSON.stringify(label);
};

export const mergeReasoningSteps = (
  steps?: ChatMessage["reasoningSteps"],
  options?: { finalize?: boolean }
) => {
  const finalize = options?.finalize ?? false;
  if (!steps || steps.length === 0) {
    return [];
  }
  const merged: ChatMessage["reasoningSteps"] = [];
  const indexMap = new Map<string, number>();
  steps.forEach((step) => {
    const key = getReasoningLabelKey(step.label);
    if (indexMap.has(key)) {
      const idx = indexMap.get(key)!;
      const incomingStatus = normalizeReasoningStatus(step.status);
      merged[idx] = {
        ...merged[idx],
        ...step,
        description: step.description ?? merged[idx].description,
        citations:
          step.citations && step.citations.length > 0
            ? step.citations
            : merged[idx].citations,
        icon: step.icon ?? merged[idx].icon,
        status: finalize
          ? "complete"
          : incomingStatus || merged[idx].status || "complete",
      };
    } else {
      const normalizedStatus = finalize
        ? "complete"
        : normalizeReasoningStatus(step.status);
      const nextStep = { ...step, status: normalizedStatus };
      indexMap.set(key, merged.push(nextStep) - 1);
    }
  });
  return merged;
};

export interface ChatController {
  messages: ChatMessage[];
  streamingContent: string;
  currentReasoning: ChatMessage["reasoningSteps"];
  isLoading: boolean;
  isLoadingHistory: boolean;
  liked: Record<string, boolean>;
  disliked: Record<string, boolean>;
  copiedMessageId: string | null;
  lastThinkingDurationMs: number | null;
  handleSubmit: (message: { text: string; files: FileUIPart[] }) => Promise<void>;
  handleStop: () => void;
  handleCopy: (content: string, messageId: string) => void;
  handleLike: (msg: ChatMessage) => Promise<void>;
  handleDislike: (msg: ChatMessage) => Promise<void>;
  handleRetry: (msg: ChatMessage) => Promise<void>;
  handleSourceClick: (citations: ChatMessage["citations"]) => void;
  refresh: () => Promise<void>;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
}

export function useChatController(): ChatController {
  const router = useRouter();
  const setSourceListOpen = useLayoutStore((state) => state.setSourceListOpen);
  const activeChatId = useLayoutStore((state) => state.activeChatId);
  const setActiveChatId = useLayoutStore((state) => state.setActiveChatId);
  const setSourceList = useLayoutStore((state) => state.setSourceList);
  const prevActiveChatIdRef = useRef<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [currentReasoning, setCurrentReasoning] = useState<
    ChatMessage["reasoningSteps"]
  >([]);
  const [liked, setLiked] = useState<Record<string, boolean>>({});
  const [disliked, setDisliked] = useState<Record<string, boolean>>({});
  const [lastThinkingDurationMs, setLastThinkingDurationMs] = useState<
    number | null
  >(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const citationsRef = useRef<ChatMessage["citations"]>([]);
  const reasoningRef = useRef<ChatMessage["reasoningSteps"]>([]);
  const thinkingStartRef = useRef<number | null>(null);
  const thinkingDurationRef = useRef<number | null>(null);
  const abortManager = useRef(new AbortControllerManager());
  const isInitializingChatRef = useRef(false);
  const isActivelyStreamingRef = useRef(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const clearStreamingState = useCallback(() => {
    setIsLoading(false);
    setStreamingContent("");
    setCurrentReasoning([]);
    citationsRef.current = [];
    reasoningRef.current = [];
    thinkingStartRef.current = null;
    thinkingDurationRef.current = null;
    isActivelyStreamingRef.current = false;
  }, []);

  useEffect(() => {
    const prevActiveChatId = prevActiveChatIdRef.current;
    prevActiveChatIdRef.current = activeChatId;

    if (!activeChatId) {
      // Don't clear streaming state if we're actively loading/streaming (e.g., from pending message)
      if (isActivelyStreamingRef.current) {
        return;
      }
      // Don't abort if there's a pending message to process
      if (hasPendingChatMessage()) {
        clearStreamingState();
        return;
      }
      // Don't abort if we're transitioning from null to null (initial load)
      if (prevActiveChatId === null) {
        clearStreamingState();
        return;
      }
      abortManager.current.abort();
      clearStreamingState();
      return;
    }

    if (isInitializingChatRef.current) {
      return;
    }

    // Don't abort if we're transitioning from null to a new chat ID (initialization)
    if (prevActiveChatId === null && activeChatId) {
      return;
    }

    abortManager.current.abort();
    clearStreamingState();
  }, [activeChatId, clearStreamingState]);

  useEffect(() => {
    let isCancelled = false;

    async function loadHistory() {
      if (isInitializingChatRef.current) {
        isInitializingChatRef.current = false;
        return;
      }

      if (!activeChatId) {
        if (!isCancelled && !hasPendingChatMessage()) {
          setMessages([]);
          setIsLoadingHistory(false);
        }
        return;
      }

      setIsLoadingHistory(true);
      abortManager.current.abort();

      try {
        const history = await chatService.getHistory(activeChatId);
        if (isCancelled) {
          return;
        }
        const formattedMessages: ChatMessage[] = history.messages.map(
          (msg, index) => {
            const reasoningStepsRaw = msg.reasoning_steps
              ? msg.reasoning_steps.map((step: any) => {
                  const baseCitations = Array.isArray(step.citations)
                    ? step.citations
                    : undefined;
                  const fallbackCitations =
                    step.step.toLowerCase().includes("retrieval") &&
                    (!baseCitations || baseCitations.length === 0)
                      ? msg.citations
                      : baseCitations;
                  return {
                    label: step.step,
                    status: normalizeReasoningStatus(step.status),
                    icon: step.step.toLowerCase().includes("retrieval")
                      ? SearchIcon
                      : DotIcon,
                    description: step.message,
                    citations: fallbackCitations,
                    query: step.query,
                    sources: step.sources,
                  };
                })
              : [];
            const reasoningSteps =
              reasoningStepsRaw.length > 0
                ? mergeReasoningSteps(reasoningStepsRaw, { finalize: true })
                : [];
            return {
              id: nanoid(),
              role: msg.role,
              content: msg.content,
              createdAt: new Date(),
              citations: msg.citations,
              attachments: msg.attachments
                ? msg.attachments.map((att: any) => ({
                    type: "file",
                    mediaType: att.type,
                    filename: att.name,
                    url: `data:${att.type};base64,${att.content}`,
                  }))
                : undefined,
              reasoningSteps:
                reasoningSteps.length > 0 ? reasoningSteps : undefined,
              thinkingDurationMs: (msg as any).thinking_duration_ms ?? undefined,
              liked: (msg as any).liked,
              disliked: (msg as any).disliked,
              messageIndex: index,
            };
          }
        );
        setMessages(formattedMessages);

        const likedState: Record<string, boolean> = {};
        const dislikedState: Record<string, boolean> = {};
        formattedMessages.forEach((msg) => {
          if (msg.liked) likedState[msg.id] = true;
          if (msg.disliked) dislikedState[msg.id] = true;
        });
        setLiked(likedState);
        setDisliked(dislikedState);
        setIsLoadingHistory(false);
      } catch (error) {
        if (!isCancelled) {
          console.error("Failed to load chat history", error);
          setIsLoadingHistory(false);
        }
      }
    }
    loadHistory();

    return () => {
      isCancelled = true;
    };
  }, [activeChatId, refreshTrigger]);

  const handleSourceClick = (citations: ChatMessage["citations"]) => {
    if (!citations) return;
    const sources = citations.map((c) => ({
      id: nanoid(),
      score: 1,
      metadata: {
        index_title: c.title,
        ref: c.ref || c.title,
        text: c.description,
        version_title: "Sefaria",
      },
    }));
    setSourceList(sources);
    setSourceListOpen(true);
  };

  const handleStop = () => {
    abortManager.current.abort(ChatErrorTypes.USER_STOPPED);

    if (
      streamingContent ||
      (currentReasoning && currentReasoning.length > 0) ||
      (citationsRef.current && citationsRef.current.length > 0)
    ) {
      const partialMessage: ChatMessage = {
        id: nanoid(),
        role: "assistant",
        content: streamingContent,
        createdAt: new Date(),
        citations: citationsRef.current,
        reasoningSteps: (() => {
          const merged = mergeReasoningSteps(reasoningRef.current, {
            finalize: true,
          });
          return merged.length > 0 ? merged : undefined;
        })(),
        thinkingDurationMs: thinkingDurationRef.current ?? undefined,
      };

      setMessages((prev) => [...prev, partialMessage]);
    }

    clearStreamingState();
  };

  const handleSubmit = async (message: {
    text: string;
    files: FileUIPart[];
  }) => {
    if (!message.text.trim() && message.files.length === 0) return;

    const userMessage: ChatMessage = {
      id: nanoid(),
      role: "user",
      content: message.text,
      createdAt: new Date(),
      attachments: message.files,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    isActivelyStreamingRef.current = true;
    setStreamingContent("");
    setCurrentReasoning([]);
    setLastThinkingDurationMs(null);

    citationsRef.current = [];
    reasoningRef.current = [];
    thinkingStartRef.current = Date.now();
    thinkingDurationRef.current = null;

    (async () => {
      try {
        const abortController = abortManager.current.create(ChatErrorTypes.NEW_REQUEST);

        const token = useAuthStore.getState().token;
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }
        const processedFiles = await processFilesForUpload(message.files);

        const response = await fetch("/api/py/chat", {
          method: "POST",
          headers,
          body: JSON.stringify({
            message: message.text,
            chatId: activeChatId,
            files: processedFiles,
          }),
          signal: abortController.signal,
        });

        if (!response.ok) throw new Error("Chat request failed");

        const newChatId = response.headers.get("X-Chat-ID");
        if (newChatId && newChatId !== activeChatId) {
          isInitializingChatRef.current = true;
          setActiveChatId(newChatId);
          router.push(`/chat?chatId=${newChatId}`);
        }

        const reader = response.body?.getReader();
        if (!reader) return;

        let aiContent = "";
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (abortController.signal.aborted) {
            reader.cancel();
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const event = JSON.parse(line);

              if (event.type === "token") {
                if (!thinkingDurationRef.current && thinkingStartRef.current) {
                  const duration = Date.now() - thinkingStartRef.current;
                  thinkingDurationRef.current = duration;
                  setLastThinkingDurationMs(duration);
                }
                aiContent += event.content;
                flushSync(() => setStreamingContent(aiContent));
              } else if (event.type === "citation") {
                const newCitation = event.data;
                citationsRef.current = [
                  ...(citationsRef.current || []),
                  newCitation,
                ];
              } else if (event.type === "reasoning") {
                const stepData = event.data;
                const step = {
                  label: stepData.step,
                  status: stepData.status,
                  icon: stepData.step.toLowerCase().includes("retrieval")
                    ? SearchIcon
                    : DotIcon,
                  description: stepData.message,
                  citations: stepData.citations,
                  query: stepData.query,
                  sources: stepData.sources,
                } as any;

                flushSync(() => {
                  setCurrentReasoning((prev) => {
                    const existing = prev || [];
                    const index = existing.findIndex(
                      (s) => s.label === step.label
                    );
                    let newSteps;
                    if (index !== -1) {
                      newSteps = [...existing];
                      newSteps[index] = { ...newSteps[index], ...step };
                    } else {
                      newSteps = [...existing, step];
                    }
                    const merged = mergeReasoningSteps(newSteps);
                    reasoningRef.current = merged;
                    return merged;
                  });
                });
              }
            } catch (e) {
              console.error("Error parsing JSON stream line:", line, e);
            }
          }
        }

        const aiMessage: ChatMessage = {
          id: nanoid(),
          role: "assistant",
          content: aiContent,
          createdAt: new Date(),
          citations: citationsRef.current,
          reasoningSteps: (() => {
            const merged = mergeReasoningSteps(reasoningRef.current, {
              finalize: true,
            });
            return merged.length > 0 ? merged : undefined;
          })(),
          thinkingDurationMs: thinkingDurationRef.current ?? undefined,
        };

        setMessages((prev) => [...prev, aiMessage]);
        setStreamingContent("");
        setCurrentReasoning([]);
      } catch (error: any) {
        if (isIgnorableError(error)) {
          return;
        }
        console.error("Chat error:", error);
      } finally {
        if (!abortManager.current.isAborted()) {
          clearStreamingState();
          abortManager.current.clear();
        }
      }
    })();
  };

  const handleCopy = (content: string, messageId: string) => {
    navigator.clipboard.writeText(content);
    setCopiedMessageId(messageId);
    setTimeout(() => setCopiedMessageId(null), 200);
  };

  const handleLike = async (msg: ChatMessage) => {
    if (!activeChatId || msg.messageIndex === undefined) return;

    const newLikedState = !liked[msg.id];
    setLiked((prev) => ({
      ...prev,
      [msg.id]: newLikedState,
    }));

    if (newLikedState) {
      setDisliked((prev) => ({
        ...prev,
        [msg.id]: false,
      }));
    }

    try {
      await chatService.updateMessageFeedback(activeChatId, msg.messageIndex, {
        liked: newLikedState,
        disliked: newLikedState ? false : undefined,
      });
    } catch (error) {
      console.error("Failed to update like status", error);
      setLiked((prev) => ({
        ...prev,
        [msg.id]: !newLikedState,
      }));
    }
  };

  const handleDislike = async (msg: ChatMessage) => {
    if (!activeChatId || msg.messageIndex === undefined) return;

    const newDislikedState = !disliked[msg.id];
    setDisliked((prev) => ({
      ...prev,
      [msg.id]: newDislikedState,
    }));

    if (newDislikedState) {
      setLiked((prev) => ({
        ...prev,
        [msg.id]: false,
      }));
    }

    try {
      await chatService.updateMessageFeedback(activeChatId, msg.messageIndex, {
        disliked: newDislikedState,
        liked: newDislikedState ? false : undefined,
      });
    } catch (error) {
      console.error("Failed to update dislike status", error);
      setDisliked((prev) => ({
        ...prev,
        [msg.id]: !newDislikedState,
      }));
    }
  };

  const handleRetry = async (msg: ChatMessage) => {
    if (!activeChatId || !msg.content) return;

    const msgIndex = messages.findIndex((m) => m.id === msg.id);
    if (msgIndex <= 0) return;

    const userMessage = messages[msgIndex - 1];
    if (userMessage.role !== "user") return;

    try {
      await chatService.deleteLastAssistantMessage(activeChatId);

      setMessages((prev) => prev.slice(0, msgIndex));

      await handleSubmit({
        text: userMessage.content,
        files: userMessage.attachments || [],
      });
    } catch (error) {
      console.error("Failed to retry message", error);
    }
  };

  const refresh = useCallback(async () => {
    setRefreshTrigger(prev => prev + 1);
  }, []);

  return {
    messages,
    streamingContent,
    currentReasoning,
    isLoading,
    isLoadingHistory,
    liked,
    disliked,
    copiedMessageId,
    lastThinkingDurationMs,
    handleSubmit,
    handleStop,
    handleCopy,
    handleLike,
    handleDislike,
    handleRetry,
    handleSourceClick,
    refresh,
    textareaRef,
  };
}

