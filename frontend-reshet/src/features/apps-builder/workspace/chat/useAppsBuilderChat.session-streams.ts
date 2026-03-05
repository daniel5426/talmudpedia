import { consumeRunStream as consumeRunStreamImpl } from "./useAppsBuilderChat.stream";
import type { CodingAgentPendingQuestion } from "./stream-parsers";
import type { SessionContainer } from "./useAppsBuilderChat.session-state";

type ConsumeSessionRunStreamOptions = {
  appId: string;
  runId: string;
  runSessionId: string | null;
  activeTab: "preview" | "config";
  session: SessionContainer;
  activeChatSessionIdRef: { current: string | null };
  isMountedRef: { current: boolean };
  onError: (message: string | null) => void;
  onSetCurrentRevisionId: (revisionId: string | null) => void;
  onPostRunHydrationStateChange?: (inProgress: boolean) => void;
  refreshStateSilently: () => Promise<void>;
  ensureDraftDevSession: () => Promise<void>;
  loadChatSessions: () => Promise<unknown[]>;
  requestCancelForRun: (runId: string, session: SessionContainer) => Promise<void>;
  setSessionSending: (sessionKey: string, next: boolean) => void;
  setSessionStopping: (sessionKey: string, next: boolean) => void;
  setSessionThinking: (sessionKey: string, next: string) => void;
  pushSessionTimeline: (sessionKey: string, item: { kind?: "assistant" | "user" | "tool"; title: string; description?: string; tone?: "default" | "success" | "error" }) => void;
  upsertSessionAssistantTimeline: (sessionKey: string, assistantStreamId: string, description: string) => void;
  upsertSessionToolTimeline: (
    sessionKey: string,
    toolCallId: string,
    title: string,
    status: "running" | "completed" | "failed",
    toolName: string,
    toolPath?: string | null,
    toolDetail?: string | null,
  ) => void;
  finalizeSessionRunningTools: (sessionKey: string, status: "completed" | "failed") => void;
  attachCheckpointToSessionLastUser: (sessionKey: string, checkpointId: string) => void;
  setSessionPendingQuestion: (sessionKey: string, question: CodingAgentPendingQuestion | null) => void;
  clearSessionRunActivity: (sessionId: string, runId?: string | null) => void;
  probeSessionRunActivity: (sessionId: string) => Promise<void>;
};

export async function consumeSessionRunStream({
  appId,
  runId,
  runSessionId,
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
}: ConsumeSessionRunStreamOptions): Promise<void> {
  const normalizedRunId = String(runId || "").trim();
  if (!normalizedRunId) {
    return;
  }
  const nextStreamAttachmentId = ++session.streamAttachmentIdRef.current;
  const staleReader = session.abortReaderRef.current;
  if (staleReader && typeof staleReader.cancel === "function") {
    session.abortReaderRef.current = null;
    void staleReader.cancel().catch(() => undefined);
  }
  await consumeRunStreamImpl({
    appId,
    runId: normalizedRunId,
    runSessionId: runSessionId || null,
    streamAttachmentId: nextStreamAttachmentId,
    getCurrentStreamAttachmentId: () => session.streamAttachmentIdRef.current,
    activeTab,
    activeChatSessionIdRef,
    setIsSending: (next) => setSessionSending(session.key, next),
    setIsStopping: (next) => setSessionStopping(session.key, next),
    setActiveThinkingSummary: (next) => setSessionThinking(session.key, next),
    isSendingRef: session.isSendingRef,
    pendingCancelRef: session.pendingCancelRef,
    intentionalAbortRef: session.intentionalAbortRef,
    activeRunIdRef: session.activeRunIdRef,
    lastKnownRunIdRef: session.lastKnownRunIdRef,
    abortReaderRef: session.abortReaderRef,
    isMountedRef,
    seenRunEventKeysRef: session.seenRunEventKeysRef,
    onError,
    onSetCurrentRevisionId,
    onPostRunHydrationStateChange,
    pushTimeline: (item) => pushSessionTimeline(session.key, item),
    upsertAssistantTimeline: (assistantStreamId, description) => upsertSessionAssistantTimeline(session.key, assistantStreamId, description),
    upsertToolTimeline: (toolCallId, title, status, toolName, toolPath, toolDetail) =>
      upsertSessionToolTimeline(session.key, toolCallId, title, status, toolName, toolPath, toolDetail),
    finalizeRunningTools: (status) => finalizeSessionRunningTools(session.key, status),
    attachCheckpointToLastUser: (checkpointId) => attachCheckpointToSessionLastUser(session.key, checkpointId),
    refreshStateSilently,
    ensureDraftDevSession,
    loadChatSessions,
    requestCancelForRun: async (targetRunId) => requestCancelForRun(targetRunId, session),
    onQuestionAsked: (question) => {
      setSessionPendingQuestion(session.key, question);
    },
    onQuestionResolved: (requestId) => {
      if (!requestId) {
        setSessionPendingQuestion(session.key, null);
        return;
      }
      const current = session.pendingQuestion;
      if (!current || current.requestId === requestId) {
        setSessionPendingQuestion(session.key, null);
      }
    },
    onRunTerminalized: async ({ sessionId: terminalSessionId, runId: terminalRunId, terminalStatus }) => {
      if (terminalStatus) {
        clearSessionRunActivity(terminalSessionId, terminalRunId);
      } else {
        await probeSessionRunActivity(terminalSessionId);
      }
      if (session.attachedRunIdRef.current === terminalRunId) {
        session.attachedRunIdRef.current = null;
        session.attachedRunSessionIdRef.current = null;
      }
    },
  });
}
