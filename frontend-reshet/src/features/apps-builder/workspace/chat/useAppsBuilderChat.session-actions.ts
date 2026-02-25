import { useCallback } from "react";

import { publishedAppsService } from "@/services";
import type { PublishedAppRevision } from "@/services";

import {
  DRAFT_SESSION_KEY,
  appendUserTimeline,
  createQueuedPrompt,
  normalizeSessionKey,
  type SessionContainer,
} from "./useAppsBuilderChat.session-state";
import {
  parseEngineUnavailableDetail,
  parseModelUnavailableDetail,
  parseRunActiveDetail,
  parseTerminalRunStatus,
} from "./stream-parsers";

type PromptRequest = {
  input: string;
  clientMessageId: string;
  userTimelineId: string;
  modelId?: string | null;
};

type SessionActionsDeps = {
  appId: string;
  activeTab: "preview" | "config";
  selectedRunModelId: string | null;
  activeChatSessionIdRef: { current: string | null };
  isMountedRef: { current: boolean };
  onError: (message: string | null) => void;
  onApplyRestoredRevision: (revision: PublishedAppRevision) => void;
  ensureDraftDevSession: () => Promise<void>;
  mutateSession: (sessionKey: string, updater: (session: SessionContainer) => void) => void;
  getSession: (sessionKey: string) => SessionContainer;
  markSessionRunActive: (sessionId: string, runId: string, status?: string) => void;
  clearSessionRunActivity: (sessionId: string, runId?: string | null) => void;
  probeSessionRunActivity: (sessionId: string) => Promise<void>;
  consumeRunStreamForSession: (sessionKey: string, runId: string, runSessionId: string | null) => Promise<void>;
  requestCancelForRun: (runId: string, session: SessionContainer) => Promise<void>;
  ensureSessionKeyByServerSessionId: (sessionKey: string, serverSessionId: string | null | undefined) => string;
  setActiveChatSessionId: (sessionId: string | null) => void;
  setSessionStopping: (sessionKey: string, next: boolean) => void;
  forceClearSessionSendingState: (sessionKey: string) => void;
  createClientMessageId: () => string;
};

export function useAppsBuilderChatSessionActions({
  appId,
  activeTab,
  selectedRunModelId,
  activeChatSessionIdRef,
  isMountedRef,
  onError,
  onApplyRestoredRevision,
  ensureDraftDevSession,
  mutateSession,
  getSession,
  markSessionRunActive,
  clearSessionRunActivity,
  probeSessionRunActivity,
  consumeRunStreamForSession,
  requestCancelForRun,
  ensureSessionKeyByServerSessionId,
  setActiveChatSessionId,
  setSessionStopping,
  forceClearSessionSendingState,
  createClientMessageId,
}: SessionActionsDeps) {
  const runPrompt = useCallback(async (sessionKey: string, { input, clientMessageId, userTimelineId, modelId }: PromptRequest) => {
    const resolvedSessionKey = normalizeSessionKey(sessionKey);
    const promptText = input.trim();
    if (!promptText) return;
    const resolvedModelId = modelId || null;
    const session = getSession(resolvedSessionKey);

    onError(null);
    mutateSession(resolvedSessionKey, (target) => {
      target.isSending = true;
      target.isSendingRef.current = true;
      target.activeThinkingSummary = "Thinking...";
      target.pendingQuestion = null;
    });

    let streamStarted = false;
    const currentSessionId = resolvedSessionKey === DRAFT_SESSION_KEY ? null : resolvedSessionKey;
    const submitPrompt = () =>
      publishedAppsService.submitCodingAgentPrompt(appId, {
        input: promptText,
        model_id: resolvedModelId || undefined,
        chat_session_id: currentSessionId || undefined,
        client_message_id: clientMessageId,
      });

    try {
      let submission;
      try {
        submission = await submitPrompt();
      } catch (err: any) {
        const runActive = parseRunActiveDetail(err?.message);
        if (runActive) {
          mutateSession(resolvedSessionKey, (target) => {
            target.timeline = target.timeline.filter((item) => item.id !== userTimelineId);
            target.queuedPrompts = [createQueuedPrompt(promptText, resolvedModelId), ...target.queuedPrompts];
          });
          const runActiveSessionId = String(runActive.chat_session_id || currentSessionId || "").trim();
          if (runActiveSessionId) {
            markSessionRunActive(runActiveSessionId, runActive.active_run_id, "running");
            setActiveChatSessionId(runActiveSessionId);
          }
          const targetSessionKey = runActiveSessionId || resolvedSessionKey;
          const targetSession = getSession(targetSessionKey);
          targetSession.seenRunEventKeysRef.current = new Set();
          streamStarted = true;
          await consumeRunStreamForSession(targetSessionKey, runActive.active_run_id, runActiveSessionId || null);
          return;
        }
        const engineUnavailable = parseEngineUnavailableDetail(err?.message);
        if (engineUnavailable) {
          mutateSession(resolvedSessionKey, (target) => {
            target.timeline = target.timeline.map((item) => item.id === userTimelineId ? { ...item, userDeliveryStatus: "failed" } : item);
          });
          onError(engineUnavailable.message);
          return;
        }
        const modelUnavailable = parseModelUnavailableDetail(err?.message);
        if (modelUnavailable) {
          mutateSession(resolvedSessionKey, (target) => {
            target.timeline = target.timeline.map((item) => item.id === userTimelineId ? { ...item, userDeliveryStatus: "failed" } : item);
          });
          onError(modelUnavailable.message);
          return;
        }
        throw err;
      }

      const run = submission.run;
      const runSessionId = String(run.chat_session_id || currentSessionId || "").trim();
      const targetSessionKey = ensureSessionKeyByServerSessionId(resolvedSessionKey, runSessionId || null);
      if (runSessionId) {
        markSessionRunActive(runSessionId, run.run_id, "running");
        setActiveChatSessionId(runSessionId);
      }
      mutateSession(targetSessionKey, (target) => {
        target.timeline = target.timeline.map((item) => item.id === userTimelineId ? { ...item, userDeliveryStatus: "sent" } : item);
      });

      if (session.pendingCancelRef.current) {
        await requestCancelForRun(run.run_id, session);
        return;
      }
      const targetSession = getSession(targetSessionKey);
      targetSession.seenRunEventKeysRef.current = new Set();
      streamStarted = true;
      await consumeRunStreamForSession(targetSessionKey, run.run_id, runSessionId || null);
    } catch (err) {
      mutateSession(resolvedSessionKey, (target) => {
        target.timeline = target.timeline.map((item) => item.id === userTimelineId ? { ...item, userDeliveryStatus: "failed" } : item);
      });
      onError(err instanceof Error ? err.message : "Failed to run coding agent");
    } finally {
      if (!streamStarted) {
        mutateSession(resolvedSessionKey, (target) => {
          target.pendingCancelRef.current = false;
          target.isStopping = false;
          target.activeThinkingSummary = "";
          target.isSending = false;
          target.isSendingRef.current = false;
        });
      }
    }
  }, [appId, consumeRunStreamForSession, ensureSessionKeyByServerSessionId, getSession, markSessionRunActive, mutateSession, onError, requestCancelForRun, setActiveChatSessionId]);

  const runPromptWithTimeline = useCallback(async (sessionKey: string, input: string, modelId?: string | null) => {
    const normalizedInput = input.trim();
    if (!normalizedInput) return;
    const clientMessageId = createClientMessageId();
    let userTimelineId = "";
    mutateSession(sessionKey, (session) => {
      const appended = appendUserTimeline(session.timeline, {
        input: normalizedInput,
        status: "pending",
        clientMessageId,
      });
      session.timeline = appended.timeline;
      userTimelineId = appended.timelineId;
    });
    await runPrompt(sessionKey, {
      input: normalizedInput,
      clientMessageId,
      userTimelineId,
      modelId: modelId || null,
    });
  }, [createClientMessageId, mutateSession, runPrompt]);

  const drainQueuedPrompts = useCallback(async (sessionKey: string) => {
    const session = getSession(sessionKey);
    if (session.isQueueDrainActiveRef.current || session.isSendingRef.current) {
      return;
    }
    session.isQueueDrainActiveRef.current = true;
    try {
      while (!session.isSendingRef.current) {
        const nextPrompt = session.queuedPrompts[0];
        if (!nextPrompt) {
          break;
        }
        mutateSession(sessionKey, (target) => {
          target.queuedPrompts = target.queuedPrompts.slice(1);
        });
        await runPromptWithTimeline(sessionKey, nextPrompt.text, nextPrompt.modelId || null);
      }
    } finally {
      session.isQueueDrainActiveRef.current = false;
    }
  }, [getSession, mutateSession, runPromptWithTimeline]);

  const sendBuilderChat = useCallback(async (rawInput: string) => {
    const input = rawInput.trim();
    if (!input) return;
    const key = normalizeSessionKey(activeChatSessionIdRef.current);
    const session = getSession(key);
    if (session.isSendingRef.current || session.pendingCancelRef.current) {
      mutateSession(key, (target) => {
        target.queuedPrompts = [...target.queuedPrompts, createQueuedPrompt(input, selectedRunModelId)];
      });
      return;
    }
    await runPromptWithTimeline(key, input, selectedRunModelId);
    await drainQueuedPrompts(key);
  }, [activeChatSessionIdRef, drainQueuedPrompts, getSession, mutateSession, runPromptWithTimeline, selectedRunModelId]);

  const answerPendingQuestion = useCallback(async (answers: string[][]) => {
    const key = normalizeSessionKey(activeChatSessionIdRef.current);
    const session = getSession(key);
    const requestId = String(session.pendingQuestion?.requestId || "").trim();
    if (!requestId) {
      return;
    }
    const runId = session.activeRunIdRef.current || session.lastKnownRunIdRef.current;
    if (!runId) {
      onError("Missing active run for question response");
      return;
    }
    mutateSession(key, (target) => {
      target.isAnsweringQuestion = true;
    });
    onError(null);
    try {
      await publishedAppsService.answerCodingAgentRunQuestion(appId, runId, {
        question_id: requestId,
        answers,
      });
      mutateSession(key, (target) => {
        target.pendingQuestion = null;
      });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to submit question response");
    } finally {
      mutateSession(key, (target) => {
        target.isAnsweringQuestion = false;
      });
    }
  }, [activeChatSessionIdRef, appId, getSession, mutateSession, onError]);

  const removeQueuedPrompt = useCallback((promptId: string) => {
    const key = normalizeSessionKey(activeChatSessionIdRef.current);
    mutateSession(key, (session) => {
      session.queuedPrompts = session.queuedPrompts.filter((item) => item.id !== promptId);
    });
  }, [activeChatSessionIdRef, mutateSession]);

  const stopCurrentRun = useCallback(() => {
    const key = normalizeSessionKey(activeChatSessionIdRef.current);
    const session = getSession(key);

    const isNoActiveRunError = (err: unknown): boolean => {
      const message = (err instanceof Error ? err.message : String(err || "")).toLowerCase();
      return message.includes("no active run") || message.includes("not found");
    };

    session.pendingCancelRef.current = true;
    setSessionStopping(key, true);

    const runIdToCancel = session.activeRunIdRef.current || session.lastKnownRunIdRef.current;
    const sessionIdToCancel = String(session.attachedRunSessionIdRef.current || activeChatSessionIdRef.current || "").trim();

    if (runIdToCancel) {
      session.intentionalAbortRef.current = true;
      const reader = session.abortReaderRef.current;
      session.abortReaderRef.current = null;
      if (reader && typeof reader.cancel === "function") {
        void reader.cancel().catch(() => undefined);
      }
      void requestCancelForRun(runIdToCancel, session)
        .catch((err) => {
          onError(err instanceof Error ? err.message : "Failed to cancel current run");
          session.pendingCancelRef.current = false;
        })
        .finally(() => {
          if (sessionIdToCancel) {
            void probeSessionRunActivity(sessionIdToCancel);
          }
          if (isMountedRef.current) {
            setSessionStopping(key, false);
          }
        });
      return;
    }

    const sessionId = String(activeChatSessionIdRef.current || "").trim();
    if (!sessionId) {
      return;
    }

    void (async () => {
      try {
        const active = await publishedAppsService.findCodingAgentChatSessionActiveRun(appId, sessionId);
        if (active && !parseTerminalRunStatus(active.status)) {
          await requestCancelForRun(active.run_id, session);
          void probeSessionRunActivity(sessionId);
        } else {
          forceClearSessionSendingState(key);
          clearSessionRunActivity(sessionId);
        }
      } catch (err) {
        if (isNoActiveRunError(err)) {
          return;
        }
        onError(err instanceof Error ? err.message : "Failed to cancel current run");
        session.pendingCancelRef.current = false;
      } finally {
        if (isMountedRef.current) {
          setSessionStopping(key, false);
        }
      }
    })();
  }, [activeChatSessionIdRef, appId, clearSessionRunActivity, forceClearSessionSendingState, getSession, isMountedRef, onError, probeSessionRunActivity, requestCancelForRun, setSessionStopping]);

  const startNewChat = useCallback(() => {
    mutateSession(DRAFT_SESSION_KEY, (draft) => {
      draft.timeline = [];
      draft.queuedPrompts = [];
      draft.pendingQuestion = null;
      draft.isAnsweringQuestion = false;
      draft.isSending = false;
      draft.isStopping = false;
      draft.activeThinkingSummary = "";
      draft.history.initialized = true;
      draft.history.hasMore = false;
      draft.history.nextBeforeMessageId = null;
      draft.history.isLoadingOlder = false;
    });
    setActiveChatSessionId(null);
  }, [mutateSession, setActiveChatSessionId]);

  const revertToCheckpoint = useCallback(async (userItemId: string, checkpointId: string) => {
    const key = normalizeSessionKey(activeChatSessionIdRef.current);
    const session = getSession(key);
    if (session.isSendingRef.current) {
      stopCurrentRun();
    }

    onError(null);
    try {
      const response = await publishedAppsService.restoreCodingAgentCheckpoint(appId, checkpointId, {});
      const revision = response.revision;
      onApplyRestoredRevision(revision);
      mutateSession(key, (target) => {
        const idx = target.timeline.findIndex((item) => item.id === userItemId);
        if (idx >= 0) {
          target.timeline = target.timeline.slice(0, idx);
        }
      });
      if (activeTab === "preview") {
        await ensureDraftDevSession();
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to revert to checkpoint");
      throw err;
    }
  }, [activeChatSessionIdRef, activeTab, appId, ensureDraftDevSession, getSession, mutateSession, onApplyRestoredRevision, onError, stopCurrentRun]);

  return {
    sendBuilderChat,
    removeQueuedPrompt,
    answerPendingQuestion,
    stopCurrentRun,
    startNewChat,
    revertToCheckpoint,
  };
}
