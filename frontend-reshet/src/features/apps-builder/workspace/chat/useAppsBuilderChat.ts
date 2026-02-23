import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  modelsService,
  publishedAppsService,
} from "@/services";
import type {
  CodingAgentChatSession,
  CodingAgentPromptSubmissionResponse,
  CodingAgentPromptQueueItem,
  LogicalModel,
  PublishedAppRevision,
} from "@/services";

import { TimelineItem } from "./chat-model";
import {
  parseEngineUnavailableDetail,
  parseModelUnavailableDetail,
  parseRunActiveDetail,
  parseTerminalRunStatus,
  type TerminalRunStatus,
} from "./stream-parsers";
import { consumeRunStream as consumeRunStreamImpl } from "./useAppsBuilderChat.stream";
import { readStoredChatSessionId, writeStoredChatSessionId } from "./chat-session-storage";
import { QueuedPrompt, useAppsBuilderChatTimelineState } from "./useAppsBuilderChat.timeline";

export type { QueuedPrompt };

export type UseAppsBuilderChatOptions = {
  appId: string;
  activeTab: "preview" | "config";
  ensureDraftDevSession: () => Promise<void>;
  refreshStateSilently: () => Promise<void>;
  onApplyRestoredRevision: (revision: PublishedAppRevision) => void;
  onSetCurrentRevisionId: (revisionId: string | null) => void;
  onError: (message: string | null) => void;
  initialActiveRunId?: string | null;
};

export type UseAppsBuilderChatResult = {
  isAgentPanelOpen: boolean;
  setIsAgentPanelOpen: (next: boolean) => void;
  isSending: boolean;
  isStopping: boolean;
  isUndoing: boolean;
  timeline: TimelineItem[];
  activeThinkingSummary: string;
  chatSessions: CodingAgentChatSession[];
  activeChatSessionId: string | null;
  chatModels: LogicalModel[];
  selectedRunModelId: string | null;
  setSelectedRunModelId: (next: string | null) => void;
  isModelSelectorOpen: boolean;
  setIsModelSelectorOpen: (next: boolean) => void;
  selectedRunModelLabel: string;
  queuedPrompts: QueuedPrompt[];
  removeQueuedPrompt: (promptId: string) => void;
  sendBuilderChat: (rawInput: string) => Promise<void>;
  stopCurrentRun: () => void;
  startNewChat: () => void;
  revertToCheckpoint: (userItemId: string, checkpointId: string) => Promise<void>;
  loadChatSession: (sessionId: string) => Promise<void>;
};

type ConsumeRunOptions = {
  runId: string;
};

type RestoreSessionOptions = {
  attachActiveRun?: boolean;
  preferredRunId?: string | null;
};

type PromptRequest = {
  input: string;
  clientMessageId: string;
  userTimelineId: string;
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
  onApplyRestoredRevision,
  onSetCurrentRevisionId,
  onError,
  initialActiveRunId,
}: UseAppsBuilderChatOptions): UseAppsBuilderChatResult {
  const [isAgentPanelOpen, setIsAgentPanelOpenState] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [isUndoing, setIsUndoing] = useState(false);
  const [activeThinkingSummary, setActiveThinkingSummary] = useState("");
  const [chatSessions, setChatSessions] = useState<CodingAgentChatSession[]>([]);
  const [activeChatSessionId, setActiveChatSessionId] = useState<string | null>(null);
  const [chatModels, setChatModels] = useState<LogicalModel[]>([]);
  const [selectedRunModelId, setSelectedRunModelId] = useState<string | null>(null);
  const [isModelSelectorOpen, setIsModelSelectorOpen] = useState(false);

  const {
    timeline,
    setTimeline,
    queuedPrompts,
    setQueuedPrompts,
    queuePromptByIdRef,
    timelineByClientMessageIdRef,
    queuedTimelineByClientMessageIdRef,
    resetTimelineState,
    pushTimeline,
    appendUserTimeline,
    updateUserTimelineDelivery,
    upsertAssistantTimeline,
    upsertToolTimeline,
    finalizeRunningTools,
    attachCheckpointToLastUser,
    mapQueueItems,
  } = useAppsBuilderChatTimelineState();

  const abortReaderRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
  const activeRunIdRef = useRef<string | null>(null);
  const lastKnownRunIdRef = useRef<string | null>(null);
  const activeChatSessionIdRef = useRef<string | null>(null);
  const cancelInFlightRunIdRef = useRef<string | null>(null);
  const pendingCancelRef = useRef(false);
  const intentionalAbortRef = useRef(false);
  const isSendingRef = useRef(false);
  const isMountedRef = useRef(true);
  const seenRunEventKeysRef = useRef<Set<string>>(new Set());
  const bootstrapDidRunRef = useRef(false);
  const lastResumeAttemptRunIdRef = useRef<string | null>(null);
  const restoredLastSessionRef = useRef(false);

  useEffect(() => {
    isSendingRef.current = isSending;
  }, [isSending]);

  useEffect(() => {
    activeChatSessionIdRef.current = activeChatSessionId;
    writeStoredChatSessionId(appId, activeChatSessionId);
  }, [activeChatSessionId, appId]);

  useEffect(() => {
    restoredLastSessionRef.current = false;
  }, [appId]);

  const detachActiveStream = useCallback(() => {
    intentionalAbortRef.current = true;
    const reader = abortReaderRef.current;
    abortReaderRef.current = null;
    if (reader && typeof reader.cancel === "function") {
      void reader.cancel().catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      detachActiveStream();
    };
  }, [detachActiveStream]);

  const selectedRunModelLabel = useMemo(() => {
    if (!selectedRunModelId) return "Auto";
    const match = chatModels.find((model) => model.id === selectedRunModelId);
    return match?.name || "Auto";
  }, [chatModels, selectedRunModelId]);

  const setIsAgentPanelOpen = useCallback((next: boolean) => {
    setIsAgentPanelOpenState(next);
  }, []);

  const loadChatModels = useCallback(async () => {
    try {
      const response = await modelsService.listModels("chat", "active", 0, 200);
      const models = (response.models || []).filter((item) => item.is_active !== false);
      setChatModels(models);
      setSelectedRunModelId((prev) => {
        if (!prev) return prev;
        return models.some((item) => item.id === prev) ? prev : null;
      });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load chat models");
    }
  }, [onError]);

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

  const refreshQueue = useCallback(
    async (sessionId: string | null | undefined) => {
      const normalizedSessionId = String(sessionId || "").trim();
      if (!normalizedSessionId) {
        setQueuedPrompts([]);
        queuePromptByIdRef.current = new Map();
        return;
      }
      try {
        const items = await publishedAppsService.listCodingAgentChatSessionQueue(appId, normalizedSessionId);
        mapQueueItems(items);
      } catch {
        setQueuedPrompts([]);
        queuePromptByIdRef.current = new Map();
      }
    },
    [appId, mapQueueItems, queuePromptByIdRef, setQueuedPrompts],
  );

  const requestCancelForRun = useCallback(
    async (runId: string) => {
      if (!runId) return;
      if (cancelInFlightRunIdRef.current === runId) return;
      cancelInFlightRunIdRef.current = runId;
      try {
        await publishedAppsService.cancelCodingAgentRun(appId, runId);
      } finally {
        if (cancelInFlightRunIdRef.current === runId) {
          cancelInFlightRunIdRef.current = null;
        }
      }
    },
    [appId],
  );

  const consumeRunStream = useCallback(async ({ runId }: ConsumeRunOptions) => {
    await consumeRunStreamImpl({
      appId,
      runId,
      activeTab,
      activeChatSessionIdRef,
      setIsSending,
      setIsStopping,
      setActiveThinkingSummary,
      isSendingRef,
      pendingCancelRef,
      intentionalAbortRef,
      activeRunIdRef,
      lastKnownRunIdRef,
      abortReaderRef,
      isMountedRef,
      seenRunEventKeysRef,
      onError,
      onSetCurrentRevisionId,
      pushTimeline,
      upsertAssistantTimeline,
      upsertToolTimeline,
      finalizeRunningTools,
      attachCheckpointToLastUser,
      refreshStateSilently,
      ensureDraftDevSession,
      loadChatSessions,
      refreshQueue,
    });
  }, [
    activeTab,
    appId,
    attachCheckpointToLastUser,
    ensureDraftDevSession,
    finalizeRunningTools,
    loadChatSessions,
    onError,
    onSetCurrentRevisionId,
    pushTimeline,
    refreshQueue,
    refreshStateSilently,
    upsertAssistantTimeline,
    upsertToolTimeline,
  ]);

  const enqueuePrompt = useCallback(async ({ input, clientMessageId, userTimelineId }: PromptRequest) => {
    const promptText = input.trim();
    if (!promptText) return;

    const sessionIdHint = activeChatSessionIdRef.current || undefined;
    queuedTimelineByClientMessageIdRef.current.set(clientMessageId, userTimelineId);
    updateUserTimelineDelivery({ timelineId: userTimelineId, status: "queued" });

    const enqueuePayload = {
      input: promptText,
      model_id: selectedRunModelId,
      chat_session_id: sessionIdHint,
      client_message_id: clientMessageId,
    };

    try {
      const submission = await publishedAppsService.submitCodingAgentPrompt(appId, enqueuePayload);
      if (submission.submission_status === "queued") {
        await refreshQueue(sessionIdHint || null);
        if (!isSendingRef.current) {
          seenRunEventKeysRef.current = new Set();
          await consumeRunStream({ runId: submission.active_run_id });
        }
        return;
      }

      const run = submission.run;
      if (run.chat_session_id) {
        setActiveChatSessionId(run.chat_session_id);
      }
      await refreshQueue(run.chat_session_id || sessionIdHint || null);
      const terminal = parseTerminalRunStatus(run.status);
      if (!terminal && !isSendingRef.current) {
        seenRunEventKeysRef.current = new Set();
        await consumeRunStream({ runId: run.run_id });
      }
    } catch (err: any) {
      queuedTimelineByClientMessageIdRef.current.delete(clientMessageId);
      updateUserTimelineDelivery({ timelineId: userTimelineId, status: "failed" });
      onError(err instanceof Error ? err.message : "Failed to enqueue prompt");
    }
  }, [
    appId,
    consumeRunStream,
    onError,
    refreshQueue,
    selectedRunModelId,
    queuedTimelineByClientMessageIdRef,
    updateUserTimelineDelivery,
  ]);

  const restoreSession = useCallback(async (
    sessionId: string,
    options: RestoreSessionOptions = {},
  ) => {
    const normalizedSessionId = String(sessionId || "").trim();
    if (!normalizedSessionId) return;

    if (isSendingRef.current) {
      void requestCancelForRun(activeRunIdRef.current || lastKnownRunIdRef.current || "");
      detachActiveStream();
      setIsSending(false);
      isSendingRef.current = false;
      pendingCancelRef.current = false;
      setIsStopping(false);
    }

    onError(null);
    try {
      const [detail, queueItems] = await Promise.all([
        publishedAppsService.getCodingAgentChatSession(appId, normalizedSessionId, 300),
        publishedAppsService
          .listCodingAgentChatSessionQueue(appId, normalizedSessionId)
          .catch(() => [] as CodingAgentPromptQueueItem[]),
      ]);
      const restoredTimeline: TimelineItem[] = detail.messages
        .filter((item) => (item.role === "user" || item.role === "assistant") && String(item.content || "").trim().length > 0)
        .map((item) => ({
          id: `history-${item.id}`,
          kind: item.role,
          title: item.role === "user" ? "User request" : "Assistant",
          description: item.content,
          tone: "default",
          userDeliveryStatus: item.role === "user" ? "sent" : undefined,
        }));

      setTimeline(restoredTimeline);
      timelineByClientMessageIdRef.current = new Map();
      queuedTimelineByClientMessageIdRef.current = new Map();
      setActiveChatSessionId(detail.session.id);
      mapQueueItems(queueItems);
      setActiveThinkingSummary("");

      if (!options.attachActiveRun) {
        return;
      }

      let runIdToAttach = String(options.preferredRunId || "").trim() || null;
      try {
        const active = await publishedAppsService.getCodingAgentChatSessionActiveRun(appId, detail.session.id);
        const activeStatus = parseTerminalRunStatus(active.status);
        if (!activeStatus && (!runIdToAttach || runIdToAttach === active.run_id)) {
          runIdToAttach = active.run_id;
        }
      } catch {
        // No active run for session.
      }

      if (!runIdToAttach) {
        return;
      }

      seenRunEventKeysRef.current = new Set();
      await consumeRunStream({ runId: runIdToAttach });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load coding-agent chat session");
    }
  }, [
    appId,
    consumeRunStream,
    detachActiveStream,
    mapQueueItems,
    onError,
    requestCancelForRun,
    setTimeline,
    timelineByClientMessageIdRef,
    queuedTimelineByClientMessageIdRef,
  ]);

  const loadChatSession = useCallback(async (sessionId: string) => {
    await restoreSession(sessionId, { attachActiveRun: true });
  }, [restoreSession]);

  const runPrompt = useCallback(async ({ input, clientMessageId, userTimelineId }: PromptRequest) => {
    const promptText = input.trim();
    if (!promptText) return;

    onError(null);
    setIsSending(true);
    isSendingRef.current = true;
    setActiveThinkingSummary("Thinking...");
    let streamStarted = false;

    const submitPrompt = () =>
      publishedAppsService.submitCodingAgentPrompt(appId, {
        input: promptText,
        model_id: selectedRunModelId,
        chat_session_id: activeChatSessionIdRef.current || undefined,
        client_message_id: clientMessageId,
      });

    try {
      let submission: CodingAgentPromptSubmissionResponse;
      try {
        submission = await submitPrompt();
      } catch (err: any) {
        const engineUnavailable = parseEngineUnavailableDetail(err?.message);
        if (engineUnavailable) {
          updateUserTimelineDelivery({ timelineId: userTimelineId, status: "failed" });
          onError(engineUnavailable.message);
          return;
        }
        const modelUnavailable = parseModelUnavailableDetail(err?.message);
        if (modelUnavailable) {
          updateUserTimelineDelivery({ timelineId: userTimelineId, status: "failed" });
          onError(modelUnavailable.message);
          return;
        }
        throw err;
      }

      if (submission.submission_status === "queued") {
        updateUserTimelineDelivery({ timelineId: userTimelineId, status: "queued" });
        await refreshQueue(activeChatSessionIdRef.current);
        if (!isSendingRef.current) {
          seenRunEventKeysRef.current = new Set();
          streamStarted = true;
          await consumeRunStream({ runId: submission.active_run_id });
        }
        return;
      }

      const run = submission.run;

      if (run.chat_session_id) {
        setActiveChatSessionId(run.chat_session_id);
        await refreshQueue(run.chat_session_id);
      }

      queuedTimelineByClientMessageIdRef.current.delete(clientMessageId);
      updateUserTimelineDelivery({ timelineId: userTimelineId, status: "sent" });

      if (pendingCancelRef.current) {
        await requestCancelForRun(run.run_id);
        return;
      }

      seenRunEventKeysRef.current = new Set();
      streamStarted = true;
      await consumeRunStream({ runId: run.run_id });
    } catch (err) {
      updateUserTimelineDelivery({ timelineId: userTimelineId, status: "failed" });
      onError(err instanceof Error ? err.message : "Failed to run coding agent");
    } finally {
      if (!streamStarted) {
        pendingCancelRef.current = false;
        setIsStopping(false);
        setActiveThinkingSummary("");
        setIsSending(false);
        isSendingRef.current = false;
      }
    }
  }, [
    appId,
    consumeRunStream,
    onError,
    refreshQueue,
    requestCancelForRun,
    selectedRunModelId,
    queuedTimelineByClientMessageIdRef,
    updateUserTimelineDelivery,
  ]);

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
    await restoreSession(storedSessionId, { attachActiveRun: true });
  }, [appId, initialActiveRunId, loadChatSessions, restoreSession]);

  useEffect(() => {
    if (bootstrapDidRunRef.current) {
      return;
    }
    bootstrapDidRunRef.current = true;

    void Promise.all([
      loadChatModels(),
      loadChatSessions(),
    ]).then(async ([, sessions]) => {
      await restoreLastSessionIfPossible(sessions as CodingAgentChatSession[]);
    });
  }, [loadChatModels, loadChatSessions, restoreLastSessionIfPossible]);

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
        await restoreSession(runSessionId, { attachActiveRun: true, preferredRunId: runId });
        return;
      }

      const sessions = await loadChatSessions();
      for (const session of sessions) {
        try {
          const active = await publishedAppsService.getCodingAgentChatSessionActiveRun(appId, session.id);
          if (active.run_id === runId && !parseTerminalRunStatus(active.status)) {
            await restoreSession(session.id, { attachActiveRun: true, preferredRunId: runId });
            return;
          }
        } catch {
          // keep scanning
        }
      }
    } catch {
      // keep quiet for resume bootstrapping
    }
  }, [appId, loadChatSessions, restoreSession]);

  useEffect(() => {
    const runId = String(initialActiveRunId || "").trim();
    if (runId) {
      if (!isSendingRef.current) {
        void resumeActiveRun(runId);
      }
      return;
    }
    if (!isSendingRef.current) {
      void restoreLastSessionIfPossible();
    }
  }, [initialActiveRunId, resumeActiveRun, restoreLastSessionIfPossible]);

  const stopCurrentRun = useCallback(() => {
    pendingCancelRef.current = true;
    setIsStopping(true);

    const runIdToCancel = activeRunIdRef.current || lastKnownRunIdRef.current;
    if (!runIdToCancel) {
      // Cancellation was requested before create-run resolved; runPrompt will
      // issue cancel as soon as it receives a concrete run_id.
      return;
    }

    void requestCancelForRun(runIdToCancel).catch((err) => {
      const message = err instanceof Error ? err.message : "Failed to cancel current run";
      onError(message);
      pendingCancelRef.current = false;
      setIsStopping(false);
    });
  }, [onError, requestCancelForRun]);

  const removeQueuedPrompt = useCallback((promptId: string) => {
    const sessionId = activeChatSessionIdRef.current;
    if (!sessionId) {
      return;
    }
    const queuedPrompt = queuePromptByIdRef.current.get(promptId);
    const clientMessageId = String(queuedPrompt?.clientMessageId || "").trim();
    void publishedAppsService
      .deleteCodingAgentChatSessionQueueItem(appId, sessionId, promptId)
      .then(async () => {
        if (clientMessageId) {
          queuedTimelineByClientMessageIdRef.current.delete(clientMessageId);
          updateUserTimelineDelivery({ clientMessageId, status: "failed" });
        }
        await refreshQueue(sessionId);
      })
      .catch((err) => {
        onError(err instanceof Error ? err.message : "Failed to remove queued prompt");
      });
  }, [
    appId,
    onError,
    refreshQueue,
    queuePromptByIdRef,
    queuedTimelineByClientMessageIdRef,
    updateUserTimelineDelivery,
  ]);

  const sendBuilderChat = useCallback(async (rawInput: string) => {
    const input = rawInput.trim();
    if (!input) return;

    const clientMessageId = createClientMessageId();
    const shouldQueueImmediately = isSendingRef.current || pendingCancelRef.current;
    const userTimelineId = appendUserTimeline({
      input,
      status: shouldQueueImmediately ? "queued" : "pending",
      clientMessageId,
    });

    if (shouldQueueImmediately) {
      await enqueuePrompt({ input, clientMessageId, userTimelineId });
      return;
    }

    await runPrompt({ input, clientMessageId, userTimelineId });
  }, [appendUserTimeline, enqueuePrompt, runPrompt]);

  const startNewChat = useCallback(() => {
    if (isSendingRef.current) {
      stopCurrentRun();
      detachActiveStream();
    }
    resetTimelineState();
    setActiveThinkingSummary("");
    setActiveChatSessionId(null);
    seenRunEventKeysRef.current = new Set();
  }, [detachActiveStream, resetTimelineState, stopCurrentRun]);

  const revertToCheckpoint = useCallback(async (userItemId: string, checkpointId: string) => {
    if (isSendingRef.current) {
      stopCurrentRun();
      detachActiveStream();
    }
    setIsUndoing(true);
    onError(null);
    try {
      const response = await publishedAppsService.restoreCodingAgentCheckpoint(appId, checkpointId, {});
      const revision = response.revision;
      onApplyRestoredRevision(revision);
      setTimeline((prev) => {
        const idx = prev.findIndex((item) => item.id === userItemId);
        if (idx < 0) return prev;
        return prev.slice(0, idx);
      });
      if (activeTab === "preview") {
        await ensureDraftDevSession();
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to revert to checkpoint");
    } finally {
      setIsUndoing(false);
    }
  }, [
    activeTab,
    appId,
    detachActiveStream,
    ensureDraftDevSession,
    onApplyRestoredRevision,
    onError,
    setTimeline,
    stopCurrentRun,
  ]);

  return {
    isAgentPanelOpen,
    setIsAgentPanelOpen,
    isSending,
    isStopping,
    isUndoing,
    timeline,
    activeThinkingSummary,
    chatSessions,
    activeChatSessionId,
    chatModels,
    selectedRunModelId,
    setSelectedRunModelId,
    isModelSelectorOpen,
    setIsModelSelectorOpen,
    selectedRunModelLabel,
    queuedPrompts,
    removeQueuedPrompt,
    sendBuilderChat,
    stopCurrentRun,
    startNewChat,
    revertToCheckpoint,
    loadChatSession,
  };
}
