import {
  startTransition,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
} from "react";

import { EMPTY_SUGGESTIONS, HISTORY_PAGE_SIZE } from "./demo-data";
import {
  fetchAgentThread,
  fetchAgentThreads,
  streamAgent,
  type AgentThreadDetailDto,
} from "./standalone-runtime";
import {
  applyRuntimeEvent,
  createId,
  mapThreadDetail,
  mapThreadSummary,
  previewFromMessage,
  titleFromPrompt,
} from "./thread-mappers";
import type { TemplateMessage, TemplateThread } from "./types";

export function useClassicChatState() {
  const [threads, setThreads] = useState<TemplateThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string>("");
  const [visibleHistoryCount, setVisibleHistoryCount] = useState(HISTORY_PAGE_SIZE);
  const [inputValue, setInputValue] = useState("");
  const [isResponding, setIsResponding] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [likedMessageIds, setLikedMessageIds] = useState<Record<string, boolean>>({});
  const [dislikedMessageIds, setDislikedMessageIds] = useState<Record<string, boolean>>({});
  const activeThreadIdRef = useRef(activeThreadId);
  const hydratedThreadIdsRef = useRef<Set<string>>(new Set());

  const hydrateThread = useEffectEvent(async (threadId: string, isCancelled: () => boolean) => {
    try {
      const detail = await fetchAgentThread(threadId);
      if (isCancelled()) return;
      upsertHydratedThread(detail);
      hydratedThreadIdsRef.current.add(threadId);
    } catch (error) {
      if (!isCancelled()) {
        console.error(`Failed to hydrate thread ${threadId}`, error);
      }
    }
  });

  useEffect(() => {
    activeThreadIdRef.current = activeThreadId;
  }, [activeThreadId]);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const history = await fetchAgentThreads();
        if (cancelled) return;
        const mappedThreads = history.items.map(mapThreadSummary);
        setThreads(mappedThreads);
        setActiveThreadId((current) => current || mappedThreads[0]?.id || "");
      } catch (error) {
        if (!cancelled) {
          console.error("Failed to load thread history", error);
        }
      } finally {
        if (!cancelled) {
          setIsLoadingHistory(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!activeThreadId || hydratedThreadIdsRef.current.has(activeThreadId)) {
      return;
    }

    const thread = threads.find((item) => item.id === activeThreadId);
    if (!thread || thread.isLoaded) {
      hydratedThreadIdsRef.current.add(activeThreadId);
      return;
    }

    let cancelled = false;
    void hydrateThread(activeThreadId, () => cancelled);

    return () => {
      cancelled = true;
    };
  }, [activeThreadId, threads]);

  const activeThread =
    threads.find((thread) => thread.id === activeThreadId) || threads[0] || null;

  const visibleThreads = threads.slice(0, visibleHistoryCount);
  const hasMoreHistory = visibleHistoryCount < threads.length;

  const newChat = () => {
    const threadId = `local-${createId()}`;
    const nextThread: TemplateThread = {
      id: threadId,
      title: "New chat",
      preview: "Start a new conversation.",
      updatedAt: "Just now",
      messages: [],
      isLoaded: true,
    };

    startTransition(() => {
      setThreads((current) => [nextThread, ...current]);
      setActiveThreadId(threadId);
      setInputValue("");
      setVisibleHistoryCount((current) => Math.max(current, HISTORY_PAGE_SIZE));
    });
  };

  const loadMoreHistory = () => {
    setVisibleHistoryCount((current) =>
      Math.min(current + HISTORY_PAGE_SIZE, threads.length)
    );
  };

  const submitMessage = async (text: string) => {
    const normalized = text.trim();
    if (!normalized || isResponding) return;

    const threadId = activeThread?.id || `local-${createId()}`;
    const userMessage: TemplateMessage = {
      id: createId(),
      role: "user",
      createdAt: new Date().toISOString(),
      text: normalized,
    };

    const assistantMessageId = createId();
    const assistantMessage: TemplateMessage = {
      id: assistantMessageId,
      role: "assistant",
      createdAt: new Date().toISOString(),
      blocks: [],
    };

    setInputValue("");
    setIsResponding(true);

    // Initial message append
    setThreads((current) => {
      const existingThread = current.find((t) => t.id === threadId);
      const threadMessages = existingThread?.messages || [];
      const updatedThread: TemplateThread = {
        id: threadId,
        title:
          existingThread && existingThread.messages.length > 0
            ? existingThread.title
            : titleFromPrompt(normalized),
        preview: previewFromMessage(userMessage),
        updatedAt: "Just now",
        messages: [...threadMessages, userMessage, assistantMessage],
      };

      const remaining = current.filter((t) => t.id !== threadId);
      return [updatedThread, ...remaining];
    });

    setActiveThreadId(threadId);

    try {
      const { threadId: platformThreadId } = await streamAgent(
        {
          input: normalized,
          threadId: threadId.startsWith("local-") ? undefined : threadId,
        },
        (event) => {
          setThreads((prevThreads) => {
            const currentThread = prevThreads.find((t) => t.id === threadId);
            if (!currentThread) return prevThreads;

            const msgIndex = currentThread.messages.findIndex((m) => m.id === assistantMessageId);
            if (msgIndex === -1) return prevThreads;

            const updatedMessages = [...currentThread.messages];
            const message = { ...updatedMessages[msgIndex] };
            message.blocks = applyRuntimeEvent([...(message.blocks || [])], event);
            message.text = message.blocks
              ?.filter((block) => block.kind === "text")
              .map((block) => block.content)
              .join("\n");
            updatedMessages[msgIndex] = message;

            const updatedThread = {
              ...currentThread,
              messages: updatedMessages,
              preview: previewFromMessage(message),
              updatedAt: "Just now",
              isLoaded: true,
            };
            const remaining = prevThreads.filter((t) => t.id !== threadId);
            return [updatedThread, ...remaining];
          });
        },
      );

      if (platformThreadId && platformThreadId !== threadId) {
        hydratedThreadIdsRef.current.add(platformThreadId);
        setThreads((current) =>
          current.map((thread) =>
            thread.id === threadId
              ? {
                  ...thread,
                  id: platformThreadId,
                  isLoaded: true,
                }
              : thread,
          ),
        );
        if (activeThreadIdRef.current === threadId) {
          setActiveThreadId(platformThreadId);
        }
      }

    } catch (error) {
      console.error("Streaming failed:", error);
      setThreads((prevThreads) => {
        const currentThread = prevThreads.find((t) => t.id === threadId);
        if (!currentThread) return prevThreads;
        const msgIndex = currentThread.messages.findIndex((m) => m.id === assistantMessageId);
        if (msgIndex === -1) return prevThreads;

        const updatedMessages = [...currentThread.messages];
        const message = { ...updatedMessages[msgIndex] };
        message.blocks = [
          ...(message.blocks || []),
          {
            id: createId(),
            kind: "text",
            content:
              error instanceof Error
                ? `Sorry, the standalone server failed: ${error.message}`
                : "Sorry, I encountered an error while processing your request.",
          },
        ];
        updatedMessages[msgIndex] = message;

        return prevThreads.map((thread) =>
          thread.id === threadId
            ? {
                ...thread,
                messages: updatedMessages,
                preview: previewFromMessage(message),
              }
            : thread,
        );
      });
    } finally {
      setIsResponding(false);
    }
  };

  const retryAssistantMessage = (messageId: string) => {
    if (!activeThread) return;
    const messageIndex = activeThread.messages.findIndex((message) => message.id === messageId);
    if (messageIndex < 1) return;

    const previousMessage = activeThread.messages[messageIndex - 1];
    if (previousMessage.role !== "user" || !previousMessage.text) return;

    setThreads((current) =>
      current.map((thread) =>
        thread.id === activeThread.id
          ? {
              ...thread,
              messages: thread.messages.slice(0, messageIndex),
              preview: previewFromMessage(previousMessage),
              updatedAt: "Just now",
            }
          : thread
      )
    );

    submitMessage(previousMessage.text);
  };

  const toggleLike = (messageId: string) => {
    setLikedMessageIds((current) => ({ ...current, [messageId]: !current[messageId] }));
    setDislikedMessageIds((current) => ({ ...current, [messageId]: false }));
  };

  const toggleDislike = (messageId: string) => {
    setDislikedMessageIds((current) => ({ ...current, [messageId]: !current[messageId] }));
    setLikedMessageIds((current) => ({ ...current, [messageId]: false }));
  };

  const copyMessage = async (messageId: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageId(messageId);
      window.setTimeout(() => {
        setCopiedMessageId((current) => (current === messageId ? null : current));
      }, 1200);
    } catch (error) {
      console.error("Failed to copy message", error);
    }
  };

  return {
    activeThread,
    activeThreadId,
    copiedMessageId,
    dislikedMessageIds,
    emptySuggestions: EMPTY_SUGGESTIONS,
    hasMoreHistory: !isLoadingHistory && hasMoreHistory,
    inputValue,
    isResponding,
    likedMessageIds,
    loadMoreHistory,
    newChat,
    retryAssistantMessage,
    setActiveThreadId,
    setInputValue,
    submitMessage,
    threads: visibleThreads,
    toggleDislike,
    toggleLike,
    copyMessage,
  };

  function upsertHydratedThread(detail: AgentThreadDetailDto) {
    const hydrated = mapThreadDetail(detail);
    setThreads((current) => {
      const existing = current.find((thread) => thread.id === detail.id);
      const merged = existing
        ? {
            ...hydrated,
            preview: hydrated.preview || existing.preview,
          }
        : hydrated;
      const remaining = current.filter((thread) => thread.id !== detail.id);
      return [merged, ...remaining];
    });
  }
}
