import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  listOpenCodeCodingModels,
  OPENCODE_CODING_MODEL_AUTO_ID,
  publishedAppsService,
} from "@/services";
import type {
  CodingAgentChatSession,
  OpenCodeCodingModelOption,
} from "@/services";
import type { ContextWindow } from "@/services/context-window";

import type { TimelineItem } from "./chat-model";
import { readStoredChatSessionId, writeStoredChatSessionId } from "./chat-session-storage";
import {
  DRAFT_SESSION_KEY,
  appendUserTimeline,
  createQueuedPrompt,
  createSessionContainer,
  finalizeRunningTools,
  isLocalSessionKey,
  normalizeSessionKey,
  normalizeThreadTitle,
  prependTimelineWithoutDuplicates,
  upsertAssistantTimeline,
  upsertToolTimeline,
  updateUserTimelineDelivery,
  type QueuedPrompt,
  type SessionContainer,
} from "./useAppsBuilderChat.session-state";
import { extractHistoryPaging, extractHistoryTimeline } from "./useAppsBuilderChat.session-history";
import { consumeSessionStream } from "./useAppsBuilderChat.stream";
import type { CodingAgentPendingQuestion } from "./stream-parsers";
import { createOpenCodeMessageId, createOpenCodePartId } from "./opencode-identifiers";

export type { QueuedPrompt };

export type UseAppsBuilderChatOptions = {
  appId: string;
  activeTab: "preview" | "config";
  ensureDraftDevSession: () => Promise<void>;
  refreshStateSilently: () => Promise<void>;
  onPostRunHydrationStateChange?: (inProgress: boolean) => void;
  onSetCurrentRevisionId: (revisionId: string | null) => void;
  onError: (message: string | null) => void;
  initialActiveRunId?: string | null;
};

export type UseAppsBuilderChatResult = {
  isAgentPanelOpen: boolean;
  setIsAgentPanelOpen: (next: boolean) => void;
  isSending: boolean;
  isStopping: boolean;
  timeline: TimelineItem[];
  activeThinkingSummary: string;
  activeContextStatus: ContextWindow | null;
  chatSessions: CodingAgentChatSession[];
  activeChatSessionId: string | null;
  activateDraftChat: () => void;
  chatModels: OpenCodeCodingModelOption[];
  selectedRunModelId: string | null;
  setSelectedRunModelId: (next: string | null) => void;
  isModelSelectorOpen: boolean;
  setIsModelSelectorOpen: (next: boolean) => void;
  selectedRunModelLabel: string;
  queuedPrompts: QueuedPrompt[];
  pendingQuestion: CodingAgentPendingQuestion | null;
  isAnsweringQuestion: boolean;
  runningSessionIds: string[];
  sendingSessionIds: string[];
  sessionTitleHintsBySessionId: Record<string, string>;
  hasOlderHistory: boolean;
  isLoadingOlderHistory: boolean;
  loadOlderHistory: () => Promise<void>;
  removeQueuedPrompt: (promptId: string) => void;
  answerPendingQuestion: (answers: string[][]) => Promise<void>;
  refreshChatSessionRunActivity: () => Promise<void>;
  sendBuilderChat: (rawInput: string) => Promise<void>;
  stopCurrentRun: () => void;
  startNewChat: () => void;
  loadChatSession: (sessionId: string) => Promise<void>;
};

function createClientMessageId(): string {
  return createOpenCodeMessageId();
}

function appendAssistantChunk(current: string | undefined, nextChunk: string): string {
  const previous = String(current || "");
  const incoming = String(nextChunk || "");
  if (!incoming) {
    return previous;
  }
  if (!previous) {
    return incoming;
  }
  if (incoming.startsWith(previous)) {
    return incoming;
  }
  if (previous.endsWith(incoming)) {
    return previous;
  }
  return `${previous}${incoming}`;
}

export function shouldApplyHydratedSessionState(
  session: SessionContainer,
  options: { forceReload?: boolean },
): boolean {
  if (!options.forceReload) {
    return true;
  }
  return !(
    session.isSendingRef.current
    || session.promptSubmissionInFlightRef.current
    || session.pendingCancelRef.current
  );
}

export function useAppsBuilderChat({
  appId,
  onError,
}: UseAppsBuilderChatOptions): UseAppsBuilderChatResult {
  const [isAgentPanelOpen, setIsAgentPanelOpen] = useState(true);
  const [chatSessions, setChatSessions] = useState<CodingAgentChatSession[]>([]);
  const [activeChatSessionId, setActiveChatSessionId] = useState<string | null>(null);
  const [chatModels, setChatModels] = useState<OpenCodeCodingModelOption[]>([]);
  const [selectedRunModelId, setSelectedRunModelId] = useState<string | null>(null);
  const [isModelSelectorOpen, setIsModelSelectorOpen] = useState(false);
  const [sessionTitleHintsBySessionId, setSessionTitleHintsBySessionId] = useState<Record<string, string>>({});
  const [, setRenderTick] = useState(0);

  const sessionStoreRef = useRef<Record<string, SessionContainer>>({
    [DRAFT_SESSION_KEY]: createSessionContainer(DRAFT_SESSION_KEY),
  });
  const isMountedRef = useRef(true);
  const activeChatSessionIdRef = useRef<string | null>(null);
  const bootstrapDidRunRef = useRef(false);

  const bumpRender = useCallback(() => {
    setRenderTick((prev) => prev + 1);
  }, []);

  const getSession = useCallback((sessionKey: string): SessionContainer => {
    const normalizedKey = normalizeSessionKey(sessionKey);
    const existing = sessionStoreRef.current[normalizedKey];
    if (existing) {
      return existing;
    }
    const created = createSessionContainer(normalizedKey);
    sessionStoreRef.current[normalizedKey] = created;
    return created;
  }, []);

  const mutateSession = useCallback((sessionKey: string, updater: (session: SessionContainer) => void) => {
    const session = getSession(sessionKey);
    updater(session);
    bumpRender();
  }, [bumpRender, getSession]);

  const setSessionTitleHint = useCallback((sessionKey: string, rawTitle: string) => {
    const normalizedKey = String(sessionKey || "").trim();
    if (!normalizedKey) {
      return;
    }
    const nextTitle = normalizeThreadTitle(rawTitle);
    setSessionTitleHintsBySessionId((prev) => {
      if (prev[normalizedKey] === nextTitle) {
        return prev;
      }
      return { ...prev, [normalizedKey]: nextTitle };
    });
  }, []);

  const loadChatModels = useCallback(async () => {
    const models = listOpenCodeCodingModels();
    setChatModels(models);
    setSelectedRunModelId((prev) => (
      prev && !models.some((item) => item.id === prev)
        ? null
        : prev
    ));
  }, []);

  const loadChatSessions = useCallback(async (): Promise<CodingAgentChatSession[]> => {
    try {
      const sessions = await publishedAppsService.listCodingAgentChatSessions(appId, 50);
      setChatSessions(sessions);
      setSessionTitleHintsBySessionId((prev) => {
        const next = { ...prev };
        let changed = false;
        for (const session of sessions) {
          const title = normalizeThreadTitle(session.title);
          if (next[session.id] === title) {
            continue;
          }
          next[session.id] = title;
          changed = true;
        }
        return changed ? next : prev;
      });
      return sessions;
    } catch (error) {
      onError(error instanceof Error ? error.message : "Failed to load coding-agent chat sessions");
      return [];
    }
  }, [appId, onError]);

  const resetDraftSession = useCallback(() => {
    sessionStoreRef.current[DRAFT_SESSION_KEY] = createSessionContainer(DRAFT_SESSION_KEY);
    bumpRender();
  }, [bumpRender]);

  const ensureSessionKeyByServerSessionId = useCallback((sessionKey: string, serverSessionId: string): string => {
    const normalizedServerSessionId = String(serverSessionId || "").trim();
    const normalizedSourceKey = normalizeSessionKey(sessionKey);
    if (!normalizedServerSessionId || normalizedSourceKey === normalizedServerSessionId) {
      return normalizedSourceKey;
    }
    const source = getSession(normalizedSourceKey);
    const target = getSession(normalizedServerSessionId);
    target.timeline = source.timeline;
    target.queuedPrompts = source.queuedPrompts;
    target.pendingQuestion = source.pendingQuestion;
    target.isAnsweringQuestion = source.isAnsweringQuestion;
    target.isSending = source.isSending;
    target.isStopping = source.isStopping;
    target.activeThinkingSummary = source.activeThinkingSummary;
    target.contextStatus = source.contextStatus;
    target.history = source.history;
    target.pendingCancelRef.current = source.pendingCancelRef.current;
    target.intentionalAbortRef.current = source.intentionalAbortRef.current;
    target.isSendingRef.current = source.isSendingRef.current;
    target.streamAttachmentIdRef.current = source.streamAttachmentIdRef.current;
    target.promptSubmissionInFlightRef.current = source.promptSubmissionInFlightRef.current;
    target.abortReaderRef.current = source.abortReaderRef.current;
    target.attachedRunSessionIdRef.current = normalizedServerSessionId;
    if (normalizedSourceKey === DRAFT_SESSION_KEY) {
      sessionStoreRef.current[DRAFT_SESSION_KEY] = createSessionContainer(DRAFT_SESSION_KEY);
    } else if (isLocalSessionKey(normalizedSourceKey)) {
      delete sessionStoreRef.current[normalizedSourceKey];
    }
    bumpRender();
    return normalizedServerSessionId;
  }, [bumpRender, getSession]);

  const hydrateSessionHistory = useCallback(async (
    sessionId: string,
    options: { forceReload?: boolean } = {},
  ) => {
    const normalizedSessionId = String(sessionId || "").trim();
    if (!normalizedSessionId) {
      return;
    }
    const session = getSession(normalizedSessionId);
    if (session.history.initialized && !options.forceReload) {
      return;
    }
    const detail = await publishedAppsService.getCodingAgentChatSession(appId, normalizedSessionId, { limit: 200 });
    const timeline = extractHistoryTimeline(detail);
    const paging = extractHistoryPaging(detail);
    const latestSession = getSession(normalizedSessionId);
    if (!shouldApplyHydratedSessionState(latestSession, options)) {
      return;
    }
    mutateSession(normalizedSessionId, (target) => {
      target.timeline = timeline;
      target.history.initialized = true;
      target.history.hasMore = paging.hasMore;
      target.history.nextBeforeMessageId = paging.nextBeforeMessageId;
      target.history.isLoadingOlder = false;
      target.pendingQuestion = null;
      target.activeThinkingSummary = "";
      target.isSending = false;
      target.isStopping = false;
      target.isSendingRef.current = false;
      target.pendingCancelRef.current = false;
      target.promptSubmissionInFlightRef.current = false;
      target.streamConnectedRef.current = false;
      target.streamReadyPromiseRef.current = null;
      target.resolveStreamReadyRef.current = null;
      target.attachedRunSessionIdRef.current = normalizedSessionId;
    });
  }, [appId, getSession, mutateSession]);

  const drainQueuedPromptsRef = useRef<(sessionKey: string) => Promise<void>>(async () => undefined);

  const ensureSessionStreamAttached = useCallback(async (sessionId: string) => {
    const normalizedSessionId = String(sessionId || "").trim();
    if (!normalizedSessionId) {
      return;
    }
    const session = getSession(normalizedSessionId);
    if (session.abortReaderRef.current) {
      if (session.streamConnectedRef.current) {
        return;
      }
      if (session.streamReadyPromiseRef.current) {
        await session.streamReadyPromiseRef.current;
        return;
      }
    }
    session.intentionalAbortRef.current = false;
    session.streamConnectedRef.current = false;
    session.attachedRunSessionIdRef.current = normalizedSessionId;
    session.streamReadyPromiseRef.current = new Promise<void>((resolve) => {
      session.resolveStreamReadyRef.current = resolve;
    });
    const nextAttachmentId = ++session.streamAttachmentIdRef.current;
    const staleReader = session.abortReaderRef.current;
    session.abortReaderRef.current = null;
    if (staleReader && typeof staleReader.cancel === "function") {
      void staleReader.cancel().catch(() => undefined);
    }
    void consumeSessionStream({
      appId,
      sessionId: normalizedSessionId,
      streamAttachmentId: nextAttachmentId,
      getCurrentStreamAttachmentId: () => session.streamAttachmentIdRef.current,
      abortReaderRef: session.abortReaderRef,
      intentionalAbortRef: session.intentionalAbortRef,
      isMountedRef,
      onError,
      onSetSending: (next) => {
        mutateSession(normalizedSessionId, (target) => {
          target.isSending = next;
          target.isSendingRef.current = next;
          if (!next) {
            target.promptSubmissionInFlightRef.current = false;
          }
        });
      },
      onSetStopping: (next) => {
        mutateSession(normalizedSessionId, (target) => {
          target.isStopping = next;
        });
      },
      onSetThinkingSummary: (next) => {
        mutateSession(normalizedSessionId, (target) => {
          target.activeThinkingSummary = next;
        });
      },
      onConnected: () => {
        session.streamConnectedRef.current = true;
        const resolve = session.resolveStreamReadyRef.current;
        session.resolveStreamReadyRef.current = null;
        session.streamReadyPromiseRef.current = null;
        resolve?.();
      },
      onUpsertAssistant: (assistantMessageId, descriptionChunk) => {
        mutateSession(normalizedSessionId, (target) => {
          const existing = target.timeline.find(
            (item) => item.kind === "assistant" && item.assistantStreamId === assistantMessageId,
          );
          target.timeline = upsertAssistantTimeline(
            target.timeline,
            assistantMessageId,
            appendAssistantChunk(existing?.description, descriptionChunk),
          );
        });
      },
      onUpsertTool: (toolCallId, title, status, toolName, toolPath, toolDetail) => {
        mutateSession(normalizedSessionId, (target) => {
          target.timeline = upsertToolTimeline(
            target.timeline,
            toolCallId,
            title,
            status,
            toolName,
            toolPath,
            toolDetail,
          );
        });
      },
      onFinalizeRunningTools: (status) => {
        mutateSession(normalizedSessionId, (target) => {
          target.timeline = finalizeRunningTools(target.timeline, status);
        });
      },
      onPermissionUpdated: (question) => {
        mutateSession(normalizedSessionId, (target) => {
          target.pendingQuestion = question;
        });
      },
      onPermissionResolved: (requestId) => {
        mutateSession(normalizedSessionId, (target) => {
          if (!requestId || target.pendingQuestion?.requestId === requestId) {
            target.pendingQuestion = null;
          }
        });
      },
      onSessionIdle: async () => {
        await loadChatSessions();
        await drainQueuedPromptsRef.current(normalizedSessionId);
      },
    });
    if (session.streamReadyPromiseRef.current) {
      await session.streamReadyPromiseRef.current;
    }
  }, [appId, getSession, hydrateSessionHistory, loadChatSessions, mutateSession, onError]);

  const createServerSession = useCallback(async (sourceSessionKey: string, title: string): Promise<string> => {
    const created = await publishedAppsService.createCodingAgentChatSession(appId, { title });
    setChatSessions((prev) => {
      const next = [created, ...prev.filter((item) => item.id !== created.id)];
      return next;
    });
    setSessionTitleHint(created.id, created.title || title);
    const serverSessionKey = ensureSessionKeyByServerSessionId(sourceSessionKey, created.id);
    activeChatSessionIdRef.current = created.id;
    setActiveChatSessionId(created.id);
    return serverSessionKey;
  }, [appId, ensureSessionKeyByServerSessionId, setSessionTitleHint]);

  const submitPromptToSession = useCallback(async (
    sessionKey: string,
    input: string,
    options: {
      timelineId: string;
      clientMessageId: string;
      modelId?: string | null;
    },
  ) => {
    const normalizedInput = String(input || "").trim();
    if (!normalizedInput) {
      return;
    }

    let targetSessionKey = normalizeSessionKey(sessionKey);
    const currentSession = getSession(targetSessionKey);
    if (targetSessionKey === DRAFT_SESSION_KEY || isLocalSessionKey(targetSessionKey)) {
      targetSessionKey = await createServerSession(targetSessionKey, normalizedInput);
    }
    const serverSessionId = targetSessionKey;
    const session = getSession(serverSessionId);

    mutateSession(serverSessionId, (target) => {
      target.isSending = true;
      target.isSendingRef.current = true;
      target.isStopping = false;
      target.activeThinkingSummary = "Thinking...";
      target.pendingQuestion = null;
      target.promptSubmissionInFlightRef.current = true;
      target.attachedRunSessionIdRef.current = serverSessionId;
      target.timeline = updateUserTimelineDelivery(target.timeline, {
        timelineId: options.timelineId,
        status: "pending",
      });
    });

    try {
      await ensureSessionStreamAttached(serverSessionId);
      await publishedAppsService.submitCodingAgentMessage(appId, serverSessionId, {
        message_id: options.clientMessageId,
        model_id: String(options.modelId || "").trim() || OPENCODE_CODING_MODEL_AUTO_ID,
        parts: [{ id: createOpenCodePartId(), type: "text", text: normalizedInput }],
      });
      mutateSession(serverSessionId, (target) => {
        target.timeline = updateUserTimelineDelivery(target.timeline, {
          timelineId: options.timelineId,
          status: "sent",
        });
        target.promptSubmissionInFlightRef.current = false;
      });
      await loadChatSessions();
    } catch (error) {
      mutateSession(serverSessionId, (target) => {
        target.timeline = updateUserTimelineDelivery(target.timeline, {
          timelineId: options.timelineId,
          status: "failed",
        });
        target.isSending = false;
        target.isSendingRef.current = false;
        target.isStopping = false;
        target.activeThinkingSummary = "";
        target.promptSubmissionInFlightRef.current = false;
      });
      onError(error instanceof Error ? error.message : "Failed to send coding-agent message");
      return;
    }

    if (session.pendingCancelRef.current) {
      try {
        await publishedAppsService.abortCodingAgentChatSession(appId, serverSessionId);
      } finally {
        mutateSession(serverSessionId, (target) => {
          target.pendingCancelRef.current = false;
          target.isStopping = false;
        });
      }
    }
  }, [appId, createServerSession, ensureSessionStreamAttached, getSession, loadChatSessions, mutateSession, onError]);

  const drainQueuedPrompts = useCallback(async (sessionKey: string) => {
    const normalizedSessionKey = normalizeSessionKey(sessionKey);
    const session = getSession(normalizedSessionKey);
    if (session.isQueueDrainActiveRef.current || session.isSendingRef.current || session.promptSubmissionInFlightRef.current) {
      return;
    }
    session.isQueueDrainActiveRef.current = true;
    try {
      while (!session.isSendingRef.current && !session.promptSubmissionInFlightRef.current) {
        const nextPrompt = session.queuedPrompts[0];
        if (!nextPrompt) {
          break;
        }
        mutateSession(normalizedSessionKey, (target) => {
          target.queuedPrompts = target.queuedPrompts.slice(1);
        });
        let optimisticTimelineId = "";
        const clientMessageId = nextPrompt.clientMessageId || createClientMessageId();
        mutateSession(normalizedSessionKey, (target) => {
          const appended = appendUserTimeline(target.timeline, {
            input: nextPrompt.text,
            status: "pending",
            clientMessageId,
          });
          target.timeline = appended.timeline;
          optimisticTimelineId = appended.timelineId;
        });
        await submitPromptToSession(normalizedSessionKey, nextPrompt.text, {
          timelineId: optimisticTimelineId,
          clientMessageId,
          modelId: nextPrompt.modelId || null,
        });
      }
    } finally {
      session.isQueueDrainActiveRef.current = false;
    }
  }, [getSession, mutateSession, submitPromptToSession]);

  drainQueuedPromptsRef.current = drainQueuedPrompts;

  const sendBuilderChat = useCallback(async (rawInput: string) => {
    const input = String(rawInput || "").trim();
    if (!input) {
      return;
    }
    const activeKey = normalizeSessionKey(activeChatSessionIdRef.current);
    const session = getSession(activeKey);
    if (activeKey === DRAFT_SESSION_KEY) {
      setSessionTitleHint(DRAFT_SESSION_KEY, input);
    }
    if (session.isSendingRef.current || session.promptSubmissionInFlightRef.current || session.pendingCancelRef.current) {
      mutateSession(activeKey, (target) => {
        target.queuedPrompts = [...target.queuedPrompts, createQueuedPrompt(input, selectedRunModelId)];
      });
      return;
    }

    const clientMessageId = createClientMessageId();
    let optimisticTimelineId = "";
    mutateSession(activeKey, (target) => {
      const appended = appendUserTimeline(target.timeline, {
        input,
        status: "pending",
        clientMessageId,
      });
      target.timeline = appended.timeline;
      optimisticTimelineId = appended.timelineId;
    });

    await submitPromptToSession(activeKey, input, {
      timelineId: optimisticTimelineId,
      clientMessageId,
      modelId: selectedRunModelId,
    });
  }, [getSession, mutateSession, selectedRunModelId, setSessionTitleHint, submitPromptToSession]);

  const answerPendingQuestion = useCallback(async (answers: string[][]) => {
    const sessionId = String(activeChatSessionIdRef.current || "").trim();
    if (!sessionId) {
      return;
    }
    const session = getSession(sessionId);
    const requestId = String(session.pendingQuestion?.requestId || "").trim();
    if (!requestId) {
      return;
    }
    mutateSession(sessionId, (target) => {
      target.isAnsweringQuestion = true;
    });
    try {
      await publishedAppsService.answerCodingAgentPermission(appId, sessionId, requestId, { answers });
      mutateSession(sessionId, (target) => {
        target.pendingQuestion = null;
      });
    } catch (error) {
      onError(error instanceof Error ? error.message : "Failed to answer permission request");
    } finally {
      mutateSession(sessionId, (target) => {
        target.isAnsweringQuestion = false;
      });
    }
  }, [appId, getSession, mutateSession, onError]);

  const stopCurrentRun = useCallback(() => {
    const sessionId = String(activeChatSessionIdRef.current || "").trim();
    if (!sessionId) {
      return;
    }
    mutateSession(sessionId, (target) => {
      target.pendingCancelRef.current = true;
      target.isStopping = true;
    });
    void publishedAppsService.abortCodingAgentChatSession(appId, sessionId)
      .then(async () => {
        await hydrateSessionHistory(sessionId, { forceReload: true });
      })
      .catch((error) => {
        onError(error instanceof Error ? error.message : "Failed to stop coding-agent session");
      })
      .finally(() => {
        mutateSession(sessionId, (target) => {
          target.pendingCancelRef.current = false;
          target.isStopping = false;
          target.isSending = false;
          target.isSendingRef.current = false;
          target.promptSubmissionInFlightRef.current = false;
          target.activeThinkingSummary = "";
        });
      });
  }, [appId, hydrateSessionHistory, mutateSession, onError]);

  const removeQueuedPrompt = useCallback((promptId: string) => {
    const sessionKey = normalizeSessionKey(activeChatSessionIdRef.current);
    mutateSession(sessionKey, (target) => {
      target.queuedPrompts = target.queuedPrompts.filter((item) => item.id !== promptId);
    });
  }, [mutateSession]);

  const startNewChat = useCallback(() => {
    resetDraftSession();
    activeChatSessionIdRef.current = null;
    setActiveChatSessionId(null);
  }, [resetDraftSession]);

  const activateDraftChat = useCallback(() => {
    activeChatSessionIdRef.current = null;
    setActiveChatSessionId(null);
  }, []);

  const loadChatSession = useCallback(async (sessionId: string) => {
    const normalizedSessionId = String(sessionId || "").trim();
    if (!normalizedSessionId) {
      activateDraftChat();
      return;
    }
    activeChatSessionIdRef.current = normalizedSessionId;
    setActiveChatSessionId(normalizedSessionId);
    await hydrateSessionHistory(normalizedSessionId, { forceReload: true });
    await ensureSessionStreamAttached(normalizedSessionId);
  }, [activateDraftChat, ensureSessionStreamAttached, hydrateSessionHistory]);

  const loadOlderHistory = useCallback(async () => {
    const sessionId = String(activeChatSessionIdRef.current || "").trim();
    if (!sessionId) {
      return;
    }
    const session = getSession(sessionId);
    if (!session.history.hasMore || !session.history.nextBeforeMessageId || session.history.isLoadingOlder) {
      return;
    }
    mutateSession(sessionId, (target) => {
      target.history.isLoadingOlder = true;
    });
    try {
      const detail = await publishedAppsService.getCodingAgentChatSession(appId, sessionId, {
        limit: 200,
        before_message_id: session.history.nextBeforeMessageId,
      });
      const timeline = extractHistoryTimeline(detail);
      const paging = extractHistoryPaging(detail);
      mutateSession(sessionId, (target) => {
        target.timeline = prependTimelineWithoutDuplicates(target.timeline, timeline);
        target.history.hasMore = paging.hasMore;
        target.history.nextBeforeMessageId = paging.nextBeforeMessageId;
        target.history.isLoadingOlder = false;
      });
    } catch (error) {
      mutateSession(sessionId, (target) => {
        target.history.isLoadingOlder = false;
      });
      onError(error instanceof Error ? error.message : "Failed to load older chat history");
    }
  }, [appId, getSession, mutateSession, onError]);

  const refreshChatSessionRunActivity = useCallback(async () => {
    await loadChatSessions();
  }, [loadChatSessions]);

  useEffect(() => {
    activeChatSessionIdRef.current = activeChatSessionId;
    writeStoredChatSessionId(appId, activeChatSessionId);
  }, [activeChatSessionId, appId]);

  useEffect(() => {
    sessionStoreRef.current = { [DRAFT_SESSION_KEY]: createSessionContainer(DRAFT_SESSION_KEY) };
    activeChatSessionIdRef.current = null;
    setActiveChatSessionId(null);
    setSessionTitleHintsBySessionId({});
    bumpRender();
  }, [appId, bumpRender]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      for (const session of Object.values(sessionStoreRef.current)) {
        session.intentionalAbortRef.current = true;
        session.streamConnectedRef.current = false;
        session.streamReadyPromiseRef.current = null;
        session.resolveStreamReadyRef.current = null;
        const reader = session.abortReaderRef.current;
        session.abortReaderRef.current = null;
        if (reader && typeof reader.cancel === "function") {
          void reader.cancel().catch(() => undefined);
        }
      }
    };
  }, []);

  useEffect(() => {
    if (bootstrapDidRunRef.current) {
      return;
    }
    bootstrapDidRunRef.current = true;
    void Promise.all([loadChatModels(), loadChatSessions()]).then(async ([, sessions]) => {
      const storedSessionId = readStoredChatSessionId(appId);
      if (storedSessionId && sessions.some((item) => item.id === storedSessionId)) {
        await loadChatSession(storedSessionId);
      }
    });
  }, [appId, loadChatModels, loadChatSession, loadChatSessions]);

  const activeSession = getSession(normalizeSessionKey(activeChatSessionId));
  const isSending = activeSession.isSending;
  const isStopping = activeSession.isStopping;
  const timeline = activeSession.timeline;
  const activeThinkingSummary = activeSession.activeThinkingSummary;
  const activeContextStatus = activeSession.contextStatus;
  const queuedPrompts = activeSession.queuedPrompts;
  const pendingQuestion = activeSession.pendingQuestion;
  const isAnsweringQuestion = activeSession.isAnsweringQuestion;
  const hasOlderHistory = activeSession.history.hasMore;
  const isLoadingOlderHistory = activeSession.history.isLoadingOlder;

  const sendingSessionIds = Object.values(sessionStoreRef.current)
    .filter((session) => session.key !== DRAFT_SESSION_KEY && (session.isSendingRef.current || session.promptSubmissionInFlightRef.current))
    .map((session) => session.key);
  const runningSessionIds = sendingSessionIds;

  const selectedRunModelLabel = useMemo(() => {
    if (!selectedRunModelId) {
      return "Auto";
    }
    const match = chatModels.find((model) => model.id === selectedRunModelId);
    return match?.name || "Auto";
  }, [chatModels, selectedRunModelId]);

  return {
    isAgentPanelOpen,
    setIsAgentPanelOpen,
    isSending,
    isStopping,
    timeline,
    activeThinkingSummary,
    activeContextStatus,
    chatSessions,
    activeChatSessionId,
    activateDraftChat,
    chatModels,
    selectedRunModelId,
    setSelectedRunModelId,
    isModelSelectorOpen,
    setIsModelSelectorOpen,
    selectedRunModelLabel,
    queuedPrompts,
    pendingQuestion,
    isAnsweringQuestion,
    runningSessionIds,
    sendingSessionIds,
    sessionTitleHintsBySessionId,
    hasOlderHistory,
    isLoadingOlderHistory,
    loadOlderHistory,
    removeQueuedPrompt,
    answerPendingQuestion,
    refreshChatSessionRunActivity,
    sendBuilderChat,
    stopCurrentRun,
    startNewChat,
    loadChatSession,
  };
}
