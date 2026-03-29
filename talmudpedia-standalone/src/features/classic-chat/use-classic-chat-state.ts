import {
  startTransition,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
} from "react";
import { flushSync } from "react-dom";

import { HISTORY_PAGE_SIZE } from "./demo-data";
import {
  deleteAgentThread,
  fetchAgentThread,
  fetchAgentThreads,
  streamAgent,
  type AgentThreadDetailDto,
  uploadAgentAttachments,
} from "./standalone-runtime";
import {
  applyRuntimeEvent,
  createId,
  isWidgetToolEvent,
  mapThreadDetail,
  mapRuntimeAttachment,
  mapThreadSummary,
  previewFromMessage,
  titleFromPrompt,
} from "./thread-mappers";
import { useSession } from "./session-context";
import type { ComposerSubmitPayload, TemplateAttachment, TemplateMessage, TemplateThread } from "./types";

const THREAD_PAGE_SIZE = 20;

export function useClassicChatState() {
  const { session } = useSession();
  const [threads, setThreads] = useState<TemplateThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string>("");
  const [visibleHistoryCount, setVisibleHistoryCount] = useState(HISTORY_PAGE_SIZE);
  const [inputValue, setInputValue] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isResponding, setIsResponding] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [likedMessageIds, setLikedMessageIds] = useState<Record<string, boolean>>({});
  const [dislikedMessageIds, setDislikedMessageIds] = useState<Record<string, boolean>>({});
  const activeThreadIdRef = useRef(activeThreadId);
  const hydratedThreadIdsRef = useRef<Set<string>>(new Set());

  const hydrateThread = useEffectEvent(async (threadId: string, isCancelled: () => boolean) => {
    try {
      const detail = await fetchAgentThread(threadId, { limit: THREAD_PAGE_SIZE });
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
    if (session?.selectedClientId) {
      setSubmitError(null);
    }
  }, [session?.selectedClientId]);

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

  const visibleThreads = threads
    .filter((t) => !(t.isLoaded && t.messages.length === 0))
    .slice(0, visibleHistoryCount);
  const hasMoreHistory = visibleHistoryCount < threads.length;

  const newChat = () => {
    // If any initialized thread is empty, switch to the first (newest) empty one
    const emptyThread = threads.find((t) => t.isLoaded && t.messages.length === 0);
    if (emptyThread) {
      setActiveThreadId(emptyThread.id);
      setInputValue("");
      return;
    }

    const threadId = `local-${createId()}`;
    const nextThread: TemplateThread = {
      id: threadId,
      title: "New chat",
      preview: "Start a new conversation.",
      updatedAt: "Just now",
      messages: [],
      isLoaded: true,
      hasMoreHistory: false,
      nextBeforeTurnIndex: null,
      isLoadingOlderHistory: false,
    };

    startTransition(() => {
      setThreads((current) => [nextThread, ...current]);
      setActiveThreadId(threadId);
      setInputValue("");
      setSubmitError(null);
      setVisibleHistoryCount((current) => Math.max(current, HISTORY_PAGE_SIZE));
    });
  };

  const loadMoreHistory = () => {
    setVisibleHistoryCount((current) =>
      Math.min(current + HISTORY_PAGE_SIZE, threads.length)
    );
  };

  const loadOlderMessages = async () => {
    if (!activeThread?.id || activeThread.nextBeforeTurnIndex === null || activeThread.nextBeforeTurnIndex === undefined) {
      return;
    }
    if (activeThread.isLoadingOlderHistory) {
      return;
    }

    setThreads((current) =>
      current.map((thread) =>
        thread.id === activeThread.id
          ? { ...thread, isLoadingOlderHistory: true }
          : thread,
      ),
    );

    try {
      const detail = await fetchAgentThread(activeThread.id, {
        beforeTurnIndex: activeThread.nextBeforeTurnIndex,
        limit: THREAD_PAGE_SIZE,
      });
      const olderPage = mapThreadDetail(detail);
      setThreads((current) =>
        current.map((thread) =>
          thread.id === activeThread.id
            ? {
                ...thread,
                title: olderPage.title || thread.title,
                updatedAt: thread.updatedAt,
                messages: [...olderPage.messages, ...thread.messages],
                isLoaded: true,
                hasMoreHistory: olderPage.hasMoreHistory,
                nextBeforeTurnIndex: olderPage.nextBeforeTurnIndex,
                isLoadingOlderHistory: false,
              }
            : thread,
        ),
      );
    } catch (error) {
      console.error(`Failed to load older thread messages for ${activeThread.id}`, error);
      setThreads((current) =>
        current.map((thread) =>
          thread.id === activeThread.id
            ? { ...thread, isLoadingOlderHistory: false }
            : thread,
        ),
      );
    }
  };

  const removeThread = async (threadId: string) => {
    if (!threads.find((thread) => thread.id === threadId)) {
      return;
    }

    if (!threadId.startsWith("local-")) {
      await deleteAgentThread(threadId);
    }

    hydratedThreadIdsRef.current.delete(threadId);
    let nextActiveThreadId = "";
    setThreads((current) => {
      const remaining = current.filter((thread) => thread.id !== threadId);
      nextActiveThreadId =
        activeThreadIdRef.current === threadId ? remaining[0]?.id || "" : activeThreadIdRef.current;
      return remaining;
    });
    setActiveThreadId((current) => {
      if (current !== threadId) {
        return current;
      }
      return nextActiveThreadId;
    });
  };

  const submitPreparedMessage = async ({
    text,
    attachmentIds,
    attachments,
  }: {
    text: string;
    attachmentIds: string[];
    attachments: TemplateAttachment[];
  }) => {
    const normalized = text.trim();
    if (!normalized && attachments.length === 0) return;
    if (isResponding) return;
    const selectedClientId = String(session?.selectedClientId || "").trim();
    if (!selectedClientId) {
      setSubmitError("Select a demo client before sending a message.");
      return;
    }

    const threadId = activeThread?.id || `local-${createId()}`;
    const userMessage: TemplateMessage = {
      id: createId(),
      role: "user",
      createdAt: new Date().toISOString(),
      text: normalized || undefined,
      attachments,
    };

    const assistantMessageId = createId();
    const assistantMessage: TemplateMessage = {
      id: assistantMessageId,
      role: "assistant",
      createdAt: new Date().toISOString(),
      runStatus: "pending",
      blocks: [],
    };

    setSubmitError(null);
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
            : titleFromPrompt(normalized || attachments[0]?.filename || "New chat"),
        preview: previewFromMessage(userMessage),
        updatedAt: "Just now",
        messages: [...threadMessages, userMessage, assistantMessage],
      };

      const remaining = current.filter((t) => t.id !== threadId);
      return [updatedThread, ...remaining];
    });

    setActiveThreadId(threadId);

    try {
      const applyStreamEvent = (event: Parameters<typeof streamAgent>[1] extends (event: infer T) => void ? T : never) => {
        const updateThreads = () => {
          setThreads((prevThreads) => {
            const currentThread = prevThreads.find((t) => t.id === threadId);
            if (!currentThread) return prevThreads;

            const msgIndex = currentThread.messages.findIndex((m) => m.id === assistantMessageId);
            if (msgIndex === -1) return prevThreads;

            const updatedMessages = [...currentThread.messages];
            const message = { ...updatedMessages[msgIndex] };
            message.blocks = applyRuntimeEvent([...(message.blocks || [])], event);
            if (event.event === "run.completed") {
              message.runStatus = "completed";
            } else if (event.event === "run.failed") {
              message.runStatus = "error";
            } else {
              message.runStatus = "streaming";
            }
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
        };

        if (event.event === "tool.started" && isWidgetToolEvent(event)) {
          flushSync(updateThreads);
          return;
        }

        updateThreads();
      };

      const finalizeAssistantMessageAfterStream = () => {
        setThreads((prevThreads) => {
          const currentThread = prevThreads.find((t) => t.id === threadId);
          if (!currentThread) return prevThreads;

          const msgIndex = currentThread.messages.findIndex((m) => m.id === assistantMessageId);
          if (msgIndex === -1) return prevThreads;

          const updatedMessages = [...currentThread.messages];
          const message = { ...updatedMessages[msgIndex] };
          if (message.runStatus === "completed" || message.runStatus === "error") {
            return prevThreads;
          }

          message.runStatus = "completed";
          message.text = message.blocks
            ?.filter((block) => block.kind === "text")
            .map((block) => block.content)
            .join("\n");
          updatedMessages[msgIndex] = message;

          return prevThreads.map((thread) =>
            thread.id === threadId
              ? {
                  ...thread,
                  messages: updatedMessages,
                  preview: previewFromMessage(message),
                  updatedAt: "Just now",
                  isLoaded: true,
                }
              : thread,
          );
        });
      };

      const { threadId: platformThreadId } = await streamAgent(
        {
          clientId: selectedClientId,
          input: normalized || undefined,
          attachmentIds,
          threadId: threadId.startsWith("local-") ? undefined : threadId,
        },
        applyStreamEvent,
      );

      finalizeAssistantMessageAfterStream();

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
        message.runStatus = "error";
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

  const submitMessage = async (payload: ComposerSubmitPayload | string) => {
    const submission =
      typeof payload === "string"
        ? { text: payload, files: [] }
        : payload;
    const normalized = submission.text.trim();
    if (!normalized && submission.files.length === 0) {
      return;
    }

    const currentThreadId = activeThread?.id || `local-${createId()}`;
    const runtimeThreadId = currentThreadId.startsWith("local-") ? undefined : currentThreadId;

    let attachments: TemplateAttachment[] = [];
    let attachmentIds: string[] = [];
    if (submission.files.length > 0) {
      const uploaded = await uploadAgentAttachments({
        files: submission.files,
        threadId: runtimeThreadId,
      });
      attachments = uploaded.items.map((attachment, index) =>
        mapRuntimeAttachment(attachment, submission.files[index]?.url || null),
      );
      attachmentIds = uploaded.items.map((attachment) => attachment.id);
    }

    setInputValue("");
    await submitPreparedMessage({
      text: normalized,
      attachmentIds,
      attachments,
    });
  };

  const retryAssistantMessage = (messageId: string) => {
    if (!activeThread) return;
    const messageIndex = activeThread.messages.findIndex((message) => message.id === messageId);
    if (messageIndex < 1) return;

    const previousMessage = activeThread.messages[messageIndex - 1];
    if (previousMessage.role !== "user") return;

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

    void submitPreparedMessage({
      text: previousMessage.text || "",
      attachmentIds: (previousMessage.attachments || []).map((attachment) => attachment.id),
      attachments: previousMessage.attachments || [],
    });
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
    activeThreadHasOlderHistory: Boolean(activeThread?.hasMoreHistory),
    activeThreadIsLoadingOlderHistory: Boolean(activeThread?.isLoadingOlderHistory),
    copiedMessageId,
    dislikedMessageIds,
    hasMoreHistory: !isLoadingHistory && hasMoreHistory,
    inputValue,
    isResponding,
    submitError,
    likedMessageIds,
    loadMoreHistory,
    loadOlderMessages,
    removeThread,
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
      const existingIndex = current.findIndex((thread) => thread.id === detail.id);
      if (existingIndex > -1) {
        const merged = {
          ...hydrated,
          preview: hydrated.preview || current[existingIndex].preview,
          isLoadingOlderHistory: false,
        };
        const next = [...current];
        next[existingIndex] = merged;
        return next;
      }
      return [hydrated, ...current];
    });
  }
}
