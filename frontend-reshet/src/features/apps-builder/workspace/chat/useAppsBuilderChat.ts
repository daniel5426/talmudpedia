import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  modelsService,
  publishedAppsService,
} from "@/services";
import type {
  CodingAgentChatSession,
  CodingAgentPromptSubmissionResponse,
  LogicalModel,
  PublishedAppRevision,
} from "@/services";
import { TimelineItem } from "./chat-model";
import {
  type CodingAgentPendingQuestion,
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
  pendingQuestion: CodingAgentPendingQuestion | null;
  isAnsweringQuestion: boolean;
  removeQueuedPrompt: (promptId: string) => void;
  answerPendingQuestion: (answers: string[][]) => Promise<void>;
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
  modelId?: string | null;
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
  const [pendingQuestion, setPendingQuestion] = useState<CodingAgentPendingQuestion | null>(null);
  const [isAnsweringQuestion, setIsAnsweringQuestion] = useState(false);
  const {
    timeline,
    setTimeline,
    queuedPrompts,
    setQueuedPrompts,
    resetTimelineState,
    pushTimeline,
    appendUserTimeline,
    updateUserTimelineDelivery,
    upsertAssistantTimeline,
    upsertToolTimeline,
    finalizeRunningTools,
    attachCheckpointToLastUser,
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
  const queuedPromptsRef = useRef<QueuedPrompt[]>([]);
  const isQueueDrainActiveRef = useRef(false);
  const drainQueuedPromptsRef = useRef<() => Promise<void>>(async () => undefined);
  useEffect(() => {
    isSendingRef.current = isSending;
  }, [isSending]);
  useEffect(() => {
    queuedPromptsRef.current = queuedPrompts;
  }, [queuedPrompts]);
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
  const forceClearSendingState = useCallback(() => {
    detachActiveStream();
    activeRunIdRef.current = null;
    lastKnownRunIdRef.current = null;
    pendingCancelRef.current = false;
    cancelInFlightRunIdRef.current = null;
    setIsStopping(false);
    setActiveThinkingSummary("");
    setIsSending(false);
    isSendingRef.current = false;
    setPendingQuestion(null);
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
  const replaceLocalQueue = useCallback((nextQueue: QueuedPrompt[]) => {
    queuedPromptsRef.current = nextQueue;
    setQueuedPrompts(nextQueue);
  }, [setQueuedPrompts]);
  const enqueueLocalPrompt = useCallback((input: string, modelId?: string | null): QueuedPrompt => {
    const nextPrompt: QueuedPrompt = {
      id: `queue-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
      text: input,
      createdAt: Date.now(),
      clientMessageId: null,
      modelId: modelId || null,
    };
    const nextQueue = [...queuedPromptsRef.current, nextPrompt];
    replaceLocalQueue(nextQueue);
    return nextPrompt;
  }, [replaceLocalQueue]);
  const prependLocalPrompt = useCallback((input: string, modelId?: string | null): QueuedPrompt => {
    const nextPrompt: QueuedPrompt = {
      id: `queue-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
      text: input,
      createdAt: Date.now(),
      clientMessageId: null,
      modelId: modelId || null,
    };
    const nextQueue = [nextPrompt, ...queuedPromptsRef.current];
    replaceLocalQueue(nextQueue);
    return nextPrompt;
  }, [replaceLocalQueue]);
  const popNextQueuedPrompt = useCallback((): QueuedPrompt | null => {
    const [nextPrompt, ...rest] = queuedPromptsRef.current;
    if (!nextPrompt) {
      return null;
    }
    replaceLocalQueue(rest);
    return nextPrompt;
  }, [replaceLocalQueue]);
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
      requestCancelForRun,
      onQuestionAsked: (question) => {
        setPendingQuestion(question);
      },
      onQuestionResolved: (requestId) => {
        setPendingQuestion((prev) => {
          if (!prev) return prev;
          if (!requestId || prev.requestId === requestId) {
            return null;
          }
          return prev;
        });
      },
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
    refreshStateSilently,
    requestCancelForRun,
    upsertAssistantTimeline,
    upsertToolTimeline,
  ]);
  const answerPendingQuestion = useCallback(async (answers: string[][]) => {
    const requestId = String(pendingQuestion?.requestId || "").trim();
    if (!requestId) {
      return;
    }
    const runId = activeRunIdRef.current || lastKnownRunIdRef.current;
    if (!runId) {
      onError("Missing active run for question response");
      return;
    }
    setIsAnsweringQuestion(true);
    onError(null);
    try {
      await publishedAppsService.answerCodingAgentRunQuestion(appId, runId, {
        question_id: requestId,
        answers,
      });
      setPendingQuestion(null);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to submit question response");
    } finally {
      setIsAnsweringQuestion(false);
    }
  }, [appId, onError, pendingQuestion?.requestId]);
  const restoreSession = useCallback(async (
    sessionId: string,
    options: RestoreSessionOptions = {},
  ) => {
    const normalizedSessionId = String(sessionId || "").trim();
    if (!normalizedSessionId) return;
    if (isSendingRef.current) {
      void requestCancelForRun(activeRunIdRef.current || lastKnownRunIdRef.current || "");
      forceClearSendingState();
    }
    onError(null);
    try {
      const detail = await publishedAppsService.getCodingAgentChatSession(appId, normalizedSessionId, 300);
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
      replaceLocalQueue([]);
      setActiveChatSessionId(detail.session.id);
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
      await drainQueuedPromptsRef.current();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load coding-agent chat session");
    }
  }, [
    appId,
    consumeRunStream,
    onError,
    requestCancelForRun,
    forceClearSendingState,
    replaceLocalQueue,
    setTimeline,
  ]);
  const loadChatSession = useCallback(async (sessionId: string) => {
    await restoreSession(sessionId, { attachActiveRun: true });
  }, [restoreSession]);
  const runPrompt = useCallback(async ({ input, clientMessageId, userTimelineId, modelId }: PromptRequest) => {
    const promptText = input.trim();
    if (!promptText) return;
    const resolvedModelId = modelId || null;
    onError(null);
    setIsSending(true);
    isSendingRef.current = true;
    setActiveThinkingSummary("Thinking...");
    setPendingQuestion(null);
    let streamStarted = false;
    const submitPrompt = () =>
      publishedAppsService.submitCodingAgentPrompt(appId, {
        input: promptText,
        model_id: resolvedModelId || undefined,
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
        // Keep queue frontend-only: remove temporary chat row and re-queue locally.
        setTimeline((prev) => prev.filter((item) => item.id !== userTimelineId));
        prependLocalPrompt(promptText, resolvedModelId);
        seenRunEventKeysRef.current = new Set();
        streamStarted = true;
        await consumeRunStream({ runId: submission.active_run_id });
        return;
      }
      const run = submission.run;
      if (run.chat_session_id) {
        setActiveChatSessionId(run.chat_session_id);
      }
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
    prependLocalPrompt,
    requestCancelForRun,
    setTimeline,
    updateUserTimelineDelivery,
  ]);
  const runPromptWithTimeline = useCallback(async (input: string, modelId?: string | null) => {
    const promptText = input.trim();
    if (!promptText) {
      return;
    }
    const clientMessageId = createClientMessageId();
    const userTimelineId = appendUserTimeline({
      input: promptText,
      status: "pending",
      clientMessageId,
    });
    await runPrompt({
      input: promptText,
      clientMessageId,
      userTimelineId,
      modelId: modelId || null,
    });
  }, [appendUserTimeline, runPrompt]);
  const drainQueuedPrompts = useCallback(async () => {
    if (isQueueDrainActiveRef.current || isSendingRef.current) {
      return;
    }
    isQueueDrainActiveRef.current = true;
    try {
      while (!isSendingRef.current) {
        const nextPrompt = popNextQueuedPrompt();
        if (!nextPrompt) {
          break;
        }
        await runPromptWithTimeline(nextPrompt.text, nextPrompt.modelId || null);
      }
    } finally {
      isQueueDrainActiveRef.current = false;
    }
  }, [popNextQueuedPrompt, runPromptWithTimeline]);
  useEffect(() => {
    drainQueuedPromptsRef.current = drainQueuedPrompts;
  }, [drainQueuedPrompts]);
  useEffect(() => {
    if (!isSending && queuedPromptsRef.current.length > 0) {
      void drainQueuedPrompts();
    }
  }, [drainQueuedPrompts, isSending]);
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
  useEffect(() => {
    if (!isSending) {
      return;
    }
    let disposed = false;
    const intervalMs = 2000;
    const isNotFoundError = (err: unknown): boolean => {
      const message = err instanceof Error ? err.message : String(err || "");
      return message.toLowerCase().includes("not found");
    };
    const reconcileSendingState = async () => {
      if (disposed || !isSendingRef.current) {
        return;
      }
      const runId = activeRunIdRef.current || lastKnownRunIdRef.current;
      if (runId) {
        try {
          const run = await publishedAppsService.getCodingAgentRun(appId, runId);
          if (parseTerminalRunStatus(run.status)) {
            forceClearSendingState();
          }
          return;
        } catch (err) {
          if (isNotFoundError(err)) {
            forceClearSendingState();
            return;
          }
        }
      }
      const sessionId = activeChatSessionIdRef.current;
      if (!sessionId) {
        return;
      }
      try {
        const active = await publishedAppsService.getCodingAgentChatSessionActiveRun(appId, sessionId);
        if (parseTerminalRunStatus(active.status)) {
          forceClearSendingState();
        }
      } catch (err) {
        if (isNotFoundError(err)) {
          forceClearSendingState();
        }
      }
    };
    void reconcileSendingState();
    const timer = setInterval(() => {
      void reconcileSendingState();
    }, intervalMs);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [appId, forceClearSendingState, isSending]);
  const stopCurrentRun = useCallback(() => {
    pendingCancelRef.current = true;
    setIsStopping(true);
    const runIdToCancel = activeRunIdRef.current || lastKnownRunIdRef.current;
    if (runIdToCancel) {
      detachActiveStream();
      void requestCancelForRun(runIdToCancel)
        .catch((err) => {
          const message = err instanceof Error ? err.message : "Failed to cancel current run";
          onError(message);
          pendingCancelRef.current = false;
        })
        .finally(() => {
          if (isMountedRef.current) {
            setIsStopping(false);
          }
        });
      return;
    }
    const sessionId = activeChatSessionIdRef.current;
    if (!sessionId) {
      forceClearSendingState();
      return;
    }
    detachActiveStream();
    void (async () => {
      try {
        const active = await publishedAppsService.getCodingAgentChatSessionActiveRun(appId, sessionId);
        if (!parseTerminalRunStatus(active.status)) {
          await requestCancelForRun(active.run_id);
        } else {
          forceClearSendingState();
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to cancel current run";
        onError(message);
        pendingCancelRef.current = false;
      } finally {
        if (isMountedRef.current) {
          setIsStopping(false);
        }
      }
    })();
  }, [appId, detachActiveStream, forceClearSendingState, onError, requestCancelForRun]);
  const removeQueuedPrompt = useCallback((promptId: string) => {
    const nextQueue = queuedPromptsRef.current.filter((item) => item.id !== promptId);
    replaceLocalQueue(nextQueue);
  }, [
    replaceLocalQueue,
  ]);
  const sendBuilderChat = useCallback(async (rawInput: string) => {
    const input = rawInput.trim();
    if (!input) return;
    const shouldQueueImmediately = isSendingRef.current || pendingCancelRef.current;
    if (shouldQueueImmediately) {
      enqueueLocalPrompt(input, selectedRunModelId);
      return;
    }
    await runPromptWithTimeline(input, selectedRunModelId);
    await drainQueuedPrompts();
  }, [drainQueuedPrompts, enqueueLocalPrompt, runPromptWithTimeline, selectedRunModelId]);
  const startNewChat = useCallback(() => {
    if (isSendingRef.current) {
      stopCurrentRun();
      detachActiveStream();
    }
    resetTimelineState();
    setActiveThinkingSummary("");
    setActiveChatSessionId(null);
    setPendingQuestion(null);
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
    pendingQuestion,
    isAnsweringQuestion,
    removeQueuedPrompt,
    answerPendingQuestion,
    sendBuilderChat,
    stopCurrentRun,
    startNewChat,
    revertToCheckpoint,
    loadChatSession,
  };
}
