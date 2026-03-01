import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  publishedAppsService,
  listOpenCodeCodingModels,
} from "@/services";
import type {
  CodingAgentChatSession,
  OpenCodeCodingModelOption,
} from "@/services";
import { timelineId, type TimelineItem } from "./chat-model";
import {
  type CodingAgentPendingQuestion,
  parseTerminalRunStatus,
  type TerminalRunStatus,
} from "./stream-parsers";
import { readStoredChatSessionId, writeStoredChatSessionId } from "./chat-session-storage";
import {
  DEFAULT_THREAD_TITLE,
  DRAFT_SESSION_KEY,
  isLocalSessionKey,
  attachCheckpointToLastUser,
  createSessionContainer,
  finalizeRunningTools,
  normalizeThreadTitle,
  normalizeSessionKey,
  prependTimelineWithoutDuplicates,
  type QueuedPrompt,
  type SessionContainer,
} from "./useAppsBuilderChat.session-state";
import { extractHistoryPaging, extractHistoryTimeline } from "./useAppsBuilderChat.session-history";
import { consumeSessionRunStream } from "./useAppsBuilderChat.session-streams";
import { useAppsBuilderChatRunActivity } from "./useAppsBuilderChat.run-activity";
import { useAppsBuilderChatSessionActions } from "./useAppsBuilderChat.session-actions";
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

type RestoreSessionOptions = {
  attachActiveRun?: boolean;
  preferredRunId?: string | null;
  forceReload?: boolean;
};

const TERMINAL_STATUSES = new Set<TerminalRunStatus>(["completed", "failed", "cancelled", "paused"]);

function createClientMessageId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function useAppsBuilderChat({
  appId,
  activeTab,
  ensureDraftDevSession,
  refreshStateSilently,
  onPostRunHydrationStateChange,
  onSetCurrentRevisionId,
  onError,
  initialActiveRunId,
}: UseAppsBuilderChatOptions): UseAppsBuilderChatResult {
  const [isAgentPanelOpen, setIsAgentPanelOpenState] = useState(true);
  const [chatSessions, setChatSessions] = useState<CodingAgentChatSession[]>([]);
  const [activeChatSessionId, setActiveChatSessionId] = useState<string | null>(null);
  const [chatModels, setChatModels] = useState<OpenCodeCodingModelOption[]>([]);
  const [selectedRunModelId, setSelectedRunModelId] = useState<string | null>(null);
  const [isModelSelectorOpen, setIsModelSelectorOpen] = useState(false);
  const [sessionTitleHintsBySessionId, setSessionTitleHintsBySessionId] = useState<Record<string, string>>({});
  const [, setRenderTick] = useState(0);

  const activeChatSessionIdRef = useRef<string | null>(null);
  const sessionStoreRef = useRef<Record<string, SessionContainer>>({
    [DRAFT_SESSION_KEY]: createSessionContainer(DRAFT_SESSION_KEY),
  });
  const isMountedRef = useRef(true);
  const bootstrapDidRunRef = useRef(false);
  const restoredLastSessionRef = useRef(false);
  const lastResumeAttemptRunIdRef = useRef<string | null>(null);

  const {
    runningSessionIds,
    markSessionRunActive,
    clearSessionRunActivity,
    probeSessionRunActivity,
    probeSessionRunActivityBatch,
  } = useAppsBuilderChatRunActivity({ appId });

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

  const forceClearSessionSendingState = useCallback((sessionKey: string) => {
    mutateSession(sessionKey, (session) => {
      session.streamAttachmentIdRef.current += 1;
      session.intentionalAbortRef.current = true;
      const reader = session.abortReaderRef.current;
      session.abortReaderRef.current = null;
      if (reader && typeof reader.cancel === "function") {
        void reader.cancel().catch(() => undefined);
      }
      session.activeRunIdRef.current = null;
      session.lastKnownRunIdRef.current = null;
      session.attachedRunIdRef.current = null;
      session.attachedRunSessionIdRef.current = null;
      session.pendingCancelRef.current = false;
      session.cancelInFlightRunIdRef.current = null;
      session.isStopping = false;
      session.activeThinkingSummary = "";
      session.isSending = false;
      session.isSendingRef.current = false;
      session.pendingQuestion = null;
    });
  }, [mutateSession]);

  const setSessionSending = useCallback((sessionKey: string, next: boolean) => {
    mutateSession(sessionKey, (session) => {
      session.isSending = next;
      session.isSendingRef.current = next;
    });
  }, [mutateSession]);

  const setSessionStopping = useCallback((sessionKey: string, next: boolean) => {
    mutateSession(sessionKey, (session) => {
      session.isStopping = next;
    });
  }, [mutateSession]);

  const setSessionThinking = useCallback((sessionKey: string, next: string) => {
    mutateSession(sessionKey, (session) => {
      session.activeThinkingSummary = next;
    });
  }, [mutateSession]);

  const setSessionPendingQuestion = useCallback((sessionKey: string, question: CodingAgentPendingQuestion | null) => {
    mutateSession(sessionKey, (session) => {
      session.pendingQuestion = question;
    });
  }, [mutateSession]);

  const pushSessionTimeline = useCallback((
    sessionKey: string,
    item: {
      kind?: "assistant" | "user" | "tool";
      title: string;
      description?: string;
      tone?: "default" | "success" | "error";
    },
  ) => {
    mutateSession(sessionKey, (session) => {
      session.timeline = [...session.timeline, { ...item, kind: item.kind || "assistant", id: timelineId("timeline") }];
    });
  }, [mutateSession]);

  const upsertSessionAssistantTimeline = useCallback((sessionKey: string, assistantStreamId: string, description: string) => {
    mutateSession(sessionKey, (session) => {
      const existingIndex = session.timeline.findIndex(
        (item) => item.kind === "assistant" && item.assistantStreamId === assistantStreamId,
      );
      if (existingIndex >= 0) {
        const next = [...session.timeline];
        next[existingIndex] = {
          ...next[existingIndex],
          description,
          tone: "default",
        };
        session.timeline = next;
        return;
      }
      session.timeline = [
        ...session.timeline,
        {
          id: timelineId("assistant"),
          kind: "assistant",
          title: "Assistant",
          description,
          tone: "default",
          assistantStreamId,
        },
      ];
    });
  }, [mutateSession]);

  const upsertSessionToolTimeline = useCallback((
    sessionKey: string,
    toolCallId: string,
    title: string,
    status: "running" | "completed" | "failed",
    toolName: string,
    toolPath?: string | null,
    toolDetail?: string | null,
  ) => {
    mutateSession(sessionKey, (session) => {
      const existingIndex = session.timeline.findIndex((item) => item.kind === "tool" && item.toolCallId === toolCallId);
      const nextTone = status === "failed" ? "error" : status === "completed" ? "success" : undefined;
      if (existingIndex >= 0) {
        const next = [...session.timeline];
        next[existingIndex] = {
          ...next[existingIndex],
          title,
          toolStatus: status,
          tone: nextTone,
          toolName,
          toolPath: toolPath || next[existingIndex].toolPath,
          toolDetail: toolDetail || next[existingIndex].toolDetail,
        };
        session.timeline = next;
        return;
      }
      session.timeline = [
        ...session.timeline,
        {
          id: timelineId("tool"),
          kind: "tool",
          toolCallId,
          toolStatus: status,
          title,
          tone: nextTone,
          toolName,
          toolPath: toolPath || undefined,
          toolDetail: toolDetail || undefined,
        },
      ];
    });
  }, [mutateSession]);

  const finalizeSessionRunningTools = useCallback((sessionKey: string, status: "completed" | "failed") => {
    mutateSession(sessionKey, (session) => {
      session.timeline = finalizeRunningTools(session.timeline, status);
    });
  }, [mutateSession]);

  const attachCheckpointToSessionLastUser = useCallback((sessionKey: string, checkpointId: string) => {
    mutateSession(sessionKey, (session) => {
      session.timeline = attachCheckpointToLastUser(session.timeline, checkpointId);
    });
  }, [mutateSession]);

  const activeSessionKey = normalizeSessionKey(activeChatSessionId);
  const activeSession = getSession(activeSessionKey);

  useEffect(() => {
    activeChatSessionIdRef.current = activeChatSessionId;
    const persistedSessionId = isLocalSessionKey(activeChatSessionId) ? null : activeChatSessionId;
    writeStoredChatSessionId(appId, persistedSessionId);
  }, [activeChatSessionId, appId]);

  useEffect(() => {
    sessionStoreRef.current = { [DRAFT_SESSION_KEY]: createSessionContainer(DRAFT_SESSION_KEY) };
    restoredLastSessionRef.current = false;
    setActiveChatSessionId(null);
    setSessionTitleHintsBySessionId({});
    bumpRender();
  }, [appId, bumpRender]);

  const setSessionTitleHint = useCallback((sessionKey: string, rawTitle: string) => {
    const normalizedKey = String(sessionKey || "").trim();
    if (!normalizedKey) {
      return;
    }
    const nextTitle = normalizeThreadTitle(rawTitle);
    setSessionTitleHintsBySessionId((prev) => {
      const currentTitle = String(prev[normalizedKey] || "").trim();
      if (currentTitle && currentTitle !== DEFAULT_THREAD_TITLE) {
        return prev;
      }
      if (
        currentTitle
        && currentTitle !== DEFAULT_THREAD_TITLE
        && nextTitle === DEFAULT_THREAD_TITLE
      ) {
        return prev;
      }
      if (currentTitle === nextTitle) {
        return prev;
      }
      return { ...prev, [normalizedKey]: nextTitle };
    });
  }, []);

  const moveSessionTitleHint = useCallback((sourceSessionKey: string, targetSessionKey: string) => {
    const sourceKey = String(sourceSessionKey || "").trim();
    const targetKey = String(targetSessionKey || "").trim();
    if (!sourceKey || !targetKey || sourceKey === targetKey) {
      return;
    }
    setSessionTitleHintsBySessionId((prev) => {
      const sourceTitle = normalizeThreadTitle(prev[sourceKey]);
      const targetTitle = normalizeThreadTitle(prev[targetKey]);
      if (
        sourceTitle === DEFAULT_THREAD_TITLE
        || (targetTitle && targetTitle !== DEFAULT_THREAD_TITLE)
        || targetTitle === sourceTitle
      ) {
        return prev;
      }
      const next = { ...prev, [targetKey]: sourceTitle };
      if (sourceKey !== targetKey) {
        delete next[sourceKey];
      }
      return next;
    });
  }, []);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      for (const session of Object.values(sessionStoreRef.current)) {
        session.intentionalAbortRef.current = true;
        const reader = session.abortReaderRef.current;
        session.abortReaderRef.current = null;
        if (reader && typeof reader.cancel === "function") {
          void reader.cancel().catch(() => undefined);
        }
      }
    };
  }, []);

  const selectedRunModelLabel = useMemo(() => {
    if (!selectedRunModelId) return "Auto";
    const match = chatModels.find((model) => model.id === selectedRunModelId);
    return match?.name || "Auto";
  }, [chatModels, selectedRunModelId]);

  const setIsAgentPanelOpen = useCallback((next: boolean) => {
    setIsAgentPanelOpenState(next);
  }, []);

  const loadChatModels = useCallback(async () => {
    const models = listOpenCodeCodingModels();
    setChatModels(models);
    setSelectedRunModelId((prev) => {
      if (!prev) return prev;
      return models.some((item) => item.id === prev) ? prev : null;
    });
  }, []);

  const loadChatSessions = useCallback(async (): Promise<CodingAgentChatSession[]> => {
    try {
      const sessions = await publishedAppsService.listCodingAgentChatSessions(appId, 50);
      setChatSessions(sessions);
      return sessions;
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load coding-agent chat sessions");
      return [];
    }
  }, [appId, onError]);

  const requestCancelForRun = useCallback(async (runId: string, session: SessionContainer) => {
    if (!runId) return;
    if (session.cancelInFlightRunIdRef.current === runId) return;
    session.cancelInFlightRunIdRef.current = runId;
    try {
      await publishedAppsService.cancelCodingAgentRun(appId, runId);
    } finally {
      if (session.cancelInFlightRunIdRef.current === runId) {
        session.cancelInFlightRunIdRef.current = null;
      }
    }
  }, [appId]);

  const copySessionRuntimeState = useCallback((
    source: SessionContainer,
    target: SessionContainer,
    attachedRunSessionId?: string | null,
  ) => {
    target.timeline = source.timeline;
    target.queuedPrompts = source.queuedPrompts;
    target.pendingQuestion = source.pendingQuestion;
    target.isAnsweringQuestion = source.isAnsweringQuestion;
    target.isSending = source.isSending;
    target.isStopping = source.isStopping;
    target.activeThinkingSummary = source.activeThinkingSummary;
    target.history = source.history;
    target.activeRunIdRef.current = source.activeRunIdRef.current;
    target.lastKnownRunIdRef.current = source.lastKnownRunIdRef.current;
    target.attachedRunIdRef.current = source.attachedRunIdRef.current;
    target.attachedRunSessionIdRef.current = attachedRunSessionId ?? source.attachedRunSessionIdRef.current;
    target.abortReaderRef.current = source.abortReaderRef.current;
    target.pendingCancelRef.current = source.pendingCancelRef.current;
    target.intentionalAbortRef.current = source.intentionalAbortRef.current;
    target.isSendingRef.current = source.isSendingRef.current;
    target.seenRunEventKeysRef.current = source.seenRunEventKeysRef.current;
    target.streamAttachmentIdRef.current = source.streamAttachmentIdRef.current;
    target.cancelInFlightRunIdRef.current = source.cancelInFlightRunIdRef.current;
    target.isQueueDrainActiveRef.current = source.isQueueDrainActiveRef.current;
  }, []);

  const promoteDraftSessionToLocalSession = useCallback((localSessionKey: string): string => {
    const normalizedLocalKey = String(localSessionKey || "").trim();
    if (!isLocalSessionKey(normalizedLocalKey)) {
      return DRAFT_SESSION_KEY;
    }
    const source = getSession(DRAFT_SESSION_KEY);
    const target = getSession(normalizedLocalKey);
    copySessionRuntimeState(source, target);
    sessionStoreRef.current[DRAFT_SESSION_KEY] = createSessionContainer(DRAFT_SESSION_KEY);
    activeChatSessionIdRef.current = normalizedLocalKey;
    setActiveChatSessionId(normalizedLocalKey);
    return normalizedLocalKey;
  }, [copySessionRuntimeState, getSession]);

  const ensureSessionKeyByServerSessionId = useCallback((
    sessionKey: string,
    serverSessionId: string | null | undefined,
  ): string => {
    const normalizedServerId = String(serverSessionId || "").trim();
    if (!normalizedServerId) {
      return normalizeSessionKey(sessionKey);
    }
    const sourceKey = normalizeSessionKey(sessionKey);
    if (sourceKey === normalizedServerId) {
      return normalizedServerId;
    }
    const source = getSession(sourceKey);
    const target = getSession(normalizedServerId);
    if (sourceKey === DRAFT_SESSION_KEY || isLocalSessionKey(sourceKey)) {
      copySessionRuntimeState(source, target, normalizedServerId);
      if (sourceKey === DRAFT_SESSION_KEY) {
        sessionStoreRef.current[DRAFT_SESSION_KEY] = createSessionContainer(DRAFT_SESSION_KEY);
      } else {
        delete sessionStoreRef.current[sourceKey];
      }
      bumpRender();
      const currentActiveKey = normalizeSessionKey(activeChatSessionIdRef.current);
      if (currentActiveKey === sourceKey) {
        activeChatSessionIdRef.current = normalizedServerId;
        setActiveChatSessionId(normalizedServerId);
      }
    }
    return normalizedServerId;
  }, [bumpRender, copySessionRuntimeState, getSession]);

  const consumeRunStreamForSession = useCallback(async (
    sessionKey: string,
    runId: string,
    runSessionId: string | null,
  ) => {
    const resolvedSessionKey = ensureSessionKeyByServerSessionId(sessionKey, runSessionId);
    const session = getSession(resolvedSessionKey);
    const normalizedRunId = String(runId || "").trim();
    const normalizedRunSessionId = String(runSessionId || resolvedSessionKey || "").trim() || null;
    if (!normalizedRunId) {
      return;
    }
    session.attachedRunIdRef.current = normalizedRunId;
    session.attachedRunSessionIdRef.current = normalizedRunSessionId;
    if (normalizedRunSessionId) {
      markSessionRunActive(normalizedRunSessionId, normalizedRunId, "running");
    }

    await consumeSessionRunStream({
      appId,
      runId: normalizedRunId,
      runSessionId: normalizedRunSessionId,
      activeTab,
      session,
      activeChatSessionIdRef,
      isMountedRef,
      onError,
      onSetCurrentRevisionId,
      onPostRunHydrationStateChange,
      refreshStateSilently,
      ensureDraftDevSession,
      loadChatSessions,
      requestCancelForRun,
      setSessionSending,
      setSessionStopping,
      setSessionThinking,
      pushSessionTimeline,
      upsertSessionAssistantTimeline,
      upsertSessionToolTimeline,
      finalizeSessionRunningTools,
      attachCheckpointToSessionLastUser,
      setSessionPendingQuestion,
      clearSessionRunActivity,
      probeSessionRunActivity,
    });
  }, [activeTab, appId, attachCheckpointToSessionLastUser, clearSessionRunActivity, ensureDraftDevSession, ensureSessionKeyByServerSessionId, finalizeSessionRunningTools, getSession, loadChatSessions, markSessionRunActive, onError, onPostRunHydrationStateChange, onSetCurrentRevisionId, probeSessionRunActivity, pushSessionTimeline, refreshStateSilently, requestCancelForRun, setSessionPendingQuestion, setSessionSending, setSessionStopping, setSessionThinking, upsertSessionAssistantTimeline, upsertSessionToolTimeline]);

  const hydrateSessionHistory = useCallback(async (
    sessionId: string,
    options: RestoreSessionOptions = {},
  ) => {
    const normalizedSessionId = String(sessionId || "").trim();
    if (!normalizedSessionId) return;
    const session = getSession(normalizedSessionId);
    if (session.history.initialized && !options.forceReload) {
      setActiveChatSessionId(normalizedSessionId);
      if (options.attachActiveRun && !session.isSendingRef.current) {
        try {
          const active = await publishedAppsService.findCodingAgentChatSessionActiveRun(appId, normalizedSessionId);
          if (active && !parseTerminalRunStatus(active.status)) {
            session.seenRunEventKeysRef.current = new Set<string>();
            void consumeRunStreamForSession(normalizedSessionId, active.run_id, normalizedSessionId);
          }
        } catch {
          // best effort
        }
      }
      return;
    }

    onError(null);
    try {
      const detail = await publishedAppsService.getCodingAgentChatSession(appId, normalizedSessionId, { limit: 10 });
      const restoredTimeline = extractHistoryTimeline(detail);
      const paging = extractHistoryPaging(detail);
      mutateSession(normalizedSessionId, (target) => {
        target.timeline = restoredTimeline;
        target.queuedPrompts = [];
        target.pendingQuestion = null;
        target.activeThinkingSummary = "";
        target.history.initialized = true;
        target.history.hasMore = paging.hasMore;
        target.history.nextBeforeMessageId = paging.nextBeforeMessageId;
        target.history.isLoadingOlder = false;
      });
      setActiveChatSessionId(detail.session.id);
      await probeSessionRunActivity(detail.session.id);

      if (!options.attachActiveRun) {
        return;
      }

      let runIdToAttach = String(options.preferredRunId || "").trim() || null;
      const active = await publishedAppsService.findCodingAgentChatSessionActiveRun(appId, detail.session.id);
      if (active) {
        const activeStatus = parseTerminalRunStatus(active.status);
        if (!activeStatus && (!runIdToAttach || runIdToAttach === active.run_id)) {
          runIdToAttach = active.run_id;
        }
      }
      if (!runIdToAttach) {
        return;
      }
      const target = getSession(detail.session.id);
      target.seenRunEventKeysRef.current = new Set();
      void consumeRunStreamForSession(detail.session.id, runIdToAttach, detail.session.id);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load coding-agent chat session");
    }
  }, [appId, consumeRunStreamForSession, getSession, mutateSession, onError, probeSessionRunActivity]);

  const loadOlderHistory = useCallback(async () => {
    const sessionId = String(activeChatSessionIdRef.current || "").trim();
    if (!sessionId || isLocalSessionKey(sessionId)) return;
    const session = getSession(sessionId);
    if (session.history.isLoadingOlder || !session.history.hasMore || !session.history.nextBeforeMessageId) {
      return;
    }

    mutateSession(sessionId, (target) => {
      target.history.isLoadingOlder = true;
    });
    try {
      const detail = await publishedAppsService.getCodingAgentChatSession(appId, sessionId, {
        limit: 10,
        before_message_id: session.history.nextBeforeMessageId,
      });
      const olderTimeline = extractHistoryTimeline(detail);
      const paging = extractHistoryPaging(detail);
      mutateSession(sessionId, (target) => {
        target.timeline = prependTimelineWithoutDuplicates(target.timeline, olderTimeline);
        target.history.hasMore = paging.hasMore;
        target.history.nextBeforeMessageId = paging.nextBeforeMessageId;
        target.history.isLoadingOlder = false;
      });
    } catch (err) {
      mutateSession(sessionId, (target) => {
        target.history.isLoadingOlder = false;
      });
      onError(err instanceof Error ? err.message : "Failed to load older chat history");
    }
  }, [appId, getSession, mutateSession, onError]);

  const loadChatSession = useCallback(async (sessionId: string) => {
    const normalizedSessionId = String(sessionId || "").trim();
    if (!normalizedSessionId) return;
    if (isLocalSessionKey(normalizedSessionId)) {
      activeChatSessionIdRef.current = normalizedSessionId;
      setActiveChatSessionId(normalizedSessionId);
      return;
    }
    activeChatSessionIdRef.current = normalizedSessionId;
    setActiveChatSessionId(normalizedSessionId);
    await hydrateSessionHistory(normalizedSessionId, { attachActiveRun: true });
  }, [hydrateSessionHistory]);

  const activateDraftChat = useCallback(() => {
    activeChatSessionIdRef.current = null;
    setActiveChatSessionId(null);
  }, []);

  const refreshChatSessionRunActivity = useCallback(async () => {
    try {
      const sessions = await loadChatSessions();
      const candidates = new Set<string>();
      const activeId = String(activeChatSessionIdRef.current || "").trim();
      if (activeId && !isLocalSessionKey(activeId)) {
        candidates.add(activeId);
      }
      for (const sessionId of runningSessionIds) {
        const normalized = String(sessionId || "").trim();
        if (normalized) {
          candidates.add(normalized);
        }
      }
      for (const session of sessions.slice(0, 16)) {
        candidates.add(session.id);
      }
      await probeSessionRunActivityBatch(Array.from(candidates));
    } catch {
      // best effort
    }
  }, [loadChatSessions, probeSessionRunActivityBatch, runningSessionIds]);

  const {
    sendBuilderChat,
    removeQueuedPrompt,
    answerPendingQuestion,
    stopCurrentRun,
    startNewChat,
  } = useAppsBuilderChatSessionActions({
    appId,
    selectedRunModelId,
    activeChatSessionIdRef,
    isMountedRef,
    onError,
    mutateSession,
    getSession,
    markSessionRunActive,
    clearSessionRunActivity,
    probeSessionRunActivity,
    consumeRunStreamForSession,
    requestCancelForRun,
    ensureSessionKeyByServerSessionId,
    promoteDraftSessionToLocalSession,
    setSessionTitleHint,
    moveSessionTitleHint,
    setActiveChatSessionId,
    setSessionStopping,
    forceClearSessionSendingState,
    createClientMessageId,
  });

  const restoreLastSessionIfPossible = useCallback(async (sessionsHint?: CodingAgentChatSession[]) => {
    if (restoredLastSessionRef.current) {
      return;
    }
    const activeRunId = String(initialActiveRunId || "").trim();
    if (activeRunId) {
      return;
    }
    const storedSessionId = readStoredChatSessionId(appId);
    if (!storedSessionId) {
      restoredLastSessionRef.current = true;
      return;
    }
    const sessions = sessionsHint || await loadChatSessions();
    if (!sessions.some((item) => item.id === storedSessionId)) {
      restoredLastSessionRef.current = true;
      return;
    }
    restoredLastSessionRef.current = true;
    await hydrateSessionHistory(storedSessionId, { attachActiveRun: true });
  }, [appId, hydrateSessionHistory, initialActiveRunId, loadChatSessions]);

  const resumeActiveRun = useCallback(async (targetRunId: string) => {
    const runId = String(targetRunId || "").trim();
    if (!runId) return;
    if (lastResumeAttemptRunIdRef.current === runId) return;
    lastResumeAttemptRunIdRef.current = runId;
    try {
      const run = await publishedAppsService.getCodingAgentRun(appId, runId);
      const status = parseTerminalRunStatus(run.status);
      if (status && TERMINAL_STATUSES.has(status)) {
        return;
      }
      const runSessionId = String(run.chat_session_id || "").trim();
      if (runSessionId) {
        await hydrateSessionHistory(runSessionId, { attachActiveRun: true, preferredRunId: runId });
        return;
      }
      const sessions = await loadChatSessions();
      for (const session of sessions) {
        try {
          const active = await publishedAppsService.findCodingAgentChatSessionActiveRun(appId, session.id);
          if (active && active.run_id === runId && !parseTerminalRunStatus(active.status)) {
            await hydrateSessionHistory(session.id, { attachActiveRun: true, preferredRunId: runId });
            return;
          }
        } catch {
          // continue scan
        }
      }
    } catch {
      // bootstrap best-effort
    }
  }, [appId, hydrateSessionHistory, loadChatSessions]);

  useEffect(() => {
    if (bootstrapDidRunRef.current) {
      return;
    }
    bootstrapDidRunRef.current = true;
    void Promise.all([loadChatModels(), loadChatSessions()]).then(async ([, sessions]) => {
      await restoreLastSessionIfPossible(sessions as CodingAgentChatSession[]);
    });
  }, [loadChatModels, loadChatSessions, restoreLastSessionIfPossible]);

  useEffect(() => {
    const runId = String(initialActiveRunId || "").trim();
    if (runId) {
      void resumeActiveRun(runId);
      return;
    }
    void restoreLastSessionIfPossible();
  }, [initialActiveRunId, restoreLastSessionIfPossible, resumeActiveRun]);

  useEffect(() => {
    const timer = setInterval(() => {
      for (const [key, session] of Object.entries(sessionStoreRef.current)) {
        if (!session.isSendingRef.current) {
          continue;
        }
        const runId = session.activeRunIdRef.current || session.lastKnownRunIdRef.current;
        if (runId) {
          void (async () => {
            try {
              const run = await publishedAppsService.getCodingAgentRun(appId, runId);
              if (parseTerminalRunStatus(run.status)) {
                forceClearSessionSendingState(key);
              }
            } catch (err) {
              const message = err instanceof Error ? err.message : String(err || "");
              if (message.toLowerCase().includes("not found")) {
                forceClearSessionSendingState(key);
              }
            }
          })();
          continue;
        }

        const sessionId = key === DRAFT_SESSION_KEY ? null : key;
        if (!sessionId || isLocalSessionKey(sessionId)) {
          continue;
        }
        void (async () => {
          try {
            const active = await publishedAppsService.findCodingAgentChatSessionActiveRun(appId, sessionId);
            if (!active || parseTerminalRunStatus(active.status)) {
              forceClearSessionSendingState(key);
            }
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err || "");
            if (message.toLowerCase().includes("not found")) {
              forceClearSessionSendingState(key);
            }
          }
        })();
      }
    }, 2000);
    return () => {
      clearInterval(timer);
    };
  }, [appId, forceClearSessionSendingState]);

  const isSending = activeSession.isSending;
  const isStopping = activeSession.isStopping;
  const timeline = activeSession.timeline;
  const queuedPrompts = activeSession.queuedPrompts;
  const pendingQuestion = activeSession.pendingQuestion;
  const isAnsweringQuestion = activeSession.isAnsweringQuestion;
  const activeThinkingSummary = activeSession.activeThinkingSummary;
  const hasOlderHistory = activeSession.history.hasMore;
  const isLoadingOlderHistory = activeSession.history.isLoadingOlder;
  const sendingSessionIds = Object.values(sessionStoreRef.current)
    .filter((session) => session.key !== DRAFT_SESSION_KEY && session.isSendingRef.current)
    .map((session) => session.key);

  return {
    isAgentPanelOpen,
    setIsAgentPanelOpen,
    isSending,
    isStopping,
    timeline,
    activeThinkingSummary,
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
