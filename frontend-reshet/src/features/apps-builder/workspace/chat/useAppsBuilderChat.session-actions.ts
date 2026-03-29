import { useCallback } from "react";

import { mergeContextStatus, OPENCODE_CODING_MODEL_AUTO_ID, publishedAppsService } from "@/services";

import {
  DRAFT_SESSION_KEY,
  appendUserTimeline,
  createLocalSessionKey,
  createQueuedPrompt,
  isLocalSessionKey,
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
  selectedRunModelId: string | null;
  activeChatSessionIdRef: { current: string | null };
  isMountedRef: { current: boolean };
  onError: (message: string | null) => void;
  mutateSession: (sessionKey: string, updater: (session: SessionContainer) => void) => void;
  getSession: (sessionKey: string) => SessionContainer;
  markSessionRunActive: (sessionId: string, runId: string, status?: string) => void;
  clearSessionRunActivity: (sessionId: string, runId?: string | null) => void;
  probeSessionRunActivity: (sessionId: string) => Promise<void>;
  consumeRunStreamForSession: (sessionKey: string, runId: string, runSessionId: string | null) => Promise<void>;
  requestCancelForRun: (runId: string, session: SessionContainer) => Promise<void>;
  ensureSessionKeyByServerSessionId: (sessionKey: string, serverSessionId: string | null | undefined) => string;
  promoteDraftSessionToLocalSession: (localSessionKey: string) => string;
  setSessionTitleHint: (sessionKey: string, title: string) => void;
  moveSessionTitleHint: (sourceSessionKey: string, targetSessionKey: string) => void;
  setActiveChatSessionId: (sessionId: string | null) => void;
  setSessionStopping: (sessionKey: string, next: boolean) => void;
  forceClearSessionSendingState: (sessionKey: string) => void;
  createClientMessageId: () => string;
};

export function useAppsBuilderChatSessionActions({
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
}: SessionActionsDeps) {
  const logChatDebug = useCallback((event: string, fields: Record<string, unknown> = {}) => {
    if (typeof console === "undefined" || typeof console.info !== "function") {
      return;
    }
    console.info("[apps-builder][chat]", {
      event,
      appId,
      ...fields,
    });
  }, [appId]);

  const runPrompt = useCallback(async (sessionKey: string, { input, clientMessageId, userTimelineId, modelId }: PromptRequest) => {
    const resolvedSessionKey = normalizeSessionKey(sessionKey);
    const promptText = input.trim();
    if (!promptText) return;
    const resolvedModelId = String(modelId || "").trim() || OPENCODE_CODING_MODEL_AUTO_ID;
    const session = getSession(resolvedSessionKey);
    session.promptSubmissionInFlightRef.current = true;
    logChatDebug("run_prompt.begin", {
      sessionKey: resolvedSessionKey,
      isLocalSession: isLocalSessionKey(resolvedSessionKey),
      attachedRunSessionId: String(session.attachedRunSessionIdRef.current || "").trim() || null,
      activeRunId: String(session.activeRunIdRef.current || "").trim() || null,
      lastKnownRunId: String(session.lastKnownRunIdRef.current || "").trim() || null,
      isSending: session.isSendingRef.current,
      promptSubmissionInFlight: session.promptSubmissionInFlightRef.current,
      pendingCancel: session.pendingCancelRef.current,
      clientMessageId,
    });

    onError(null);
    mutateSession(resolvedSessionKey, (target) => {
      target.isSending = true;
      target.isSendingRef.current = true;
      target.activeThinkingSummary = "Thinking...";
      target.pendingQuestion = null;
    });

    let streamStarted = false;
    const currentSessionId = (resolvedSessionKey === DRAFT_SESSION_KEY || isLocalSessionKey(resolvedSessionKey))
      ? null
      : resolvedSessionKey;
    const submitPrompt = () =>
      publishedAppsService.submitCodingAgentPrompt(appId, {
        input: promptText,
        model_id: resolvedModelId,
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
            if (normalizeSessionKey(activeChatSessionIdRef.current) === resolvedSessionKey) {
              activeChatSessionIdRef.current = runActiveSessionId;
              setActiveChatSessionId(runActiveSessionId);
            }
          }
          const targetSessionKey = runActiveSessionId || resolvedSessionKey;
          if (targetSessionKey !== resolvedSessionKey) {
            moveSessionTitleHint(resolvedSessionKey, targetSessionKey);
          }
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

      if (submission.submission_status === "queued") {
        mutateSession(resolvedSessionKey, (target) => {
          target.timeline = target.timeline.map((item) =>
            item.id === userTimelineId ? { ...item, userDeliveryStatus: "queued" } : item,
          );
          target.queuedPrompts = [createQueuedPrompt(promptText, resolvedModelId), ...target.queuedPrompts];
        });
        const queuedSessionId = String(submission.queue_item.chat_session_id || currentSessionId || "").trim();
        const targetSessionKey = ensureSessionKeyByServerSessionId(resolvedSessionKey, queuedSessionId || null);
        getSession(targetSessionKey).promptSubmissionInFlightRef.current = false;
        if (targetSessionKey !== resolvedSessionKey) {
          moveSessionTitleHint(resolvedSessionKey, targetSessionKey);
        }
        if (queuedSessionId) {
          markSessionRunActive(queuedSessionId, submission.active_run_id, "running");
          if (normalizeSessionKey(activeChatSessionIdRef.current) === resolvedSessionKey) {
            activeChatSessionIdRef.current = queuedSessionId;
            setActiveChatSessionId(queuedSessionId);
          }
        }
        const targetSession = getSession(targetSessionKey);
        targetSession.seenRunEventKeysRef.current = new Set();
        streamStarted = true;
        await consumeRunStreamForSession(targetSessionKey, submission.active_run_id, queuedSessionId || null);
        return;
      }

      const run = submission.run;
      const runSessionId = String(run.chat_session_id || currentSessionId || "").trim();
      const targetSessionKey = ensureSessionKeyByServerSessionId(resolvedSessionKey, runSessionId || null);
      getSession(targetSessionKey).promptSubmissionInFlightRef.current = false;
      logChatDebug("run_prompt.submitted", {
        sourceSessionKey: resolvedSessionKey,
        targetSessionKey,
        runId: run.run_id,
        runSessionId: runSessionId || null,
        currentSessionId: currentSessionId || null,
        submissionStatus: submission.submission_status,
      });
      if (targetSessionKey !== resolvedSessionKey) {
        moveSessionTitleHint(resolvedSessionKey, targetSessionKey);
      }
      if (runSessionId) {
        markSessionRunActive(runSessionId, run.run_id, "running");
        if (normalizeSessionKey(activeChatSessionIdRef.current) === resolvedSessionKey) {
          activeChatSessionIdRef.current = runSessionId;
          setActiveChatSessionId(runSessionId);
        }
      }
      mutateSession(targetSessionKey, (target) => {
        target.timeline = target.timeline.map((item) => item.id === userTimelineId ? { ...item, userDeliveryStatus: "sent" } : item);
        target.contextStatus = mergeContextStatus(target.contextStatus, run.context_status);
      });

      if (isLocalSessionKey(resolvedSessionKey)) {
        const draftSession = getSession(DRAFT_SESSION_KEY);
        if (draftSession.pendingCancelRef.current) {
          session.pendingCancelRef.current = true;
          mutateSession(DRAFT_SESSION_KEY, (draft) => {
            draft.pendingCancelRef.current = false;
            draft.isStopping = false;
          });
        }
      }

      if (session.pendingCancelRef.current) {
        await requestCancelForRun(run.run_id, session);
        return;
      }
      const targetSession = getSession(targetSessionKey);
      targetSession.seenRunEventKeysRef.current = new Set();
      streamStarted = true;
      await consumeRunStreamForSession(targetSessionKey, run.run_id, runSessionId || null);
    } catch (err) {
      session.promptSubmissionInFlightRef.current = false;
      logChatDebug("run_prompt.error", {
        sessionKey: resolvedSessionKey,
        error: err instanceof Error ? err.message : String(err || ""),
      });
      mutateSession(resolvedSessionKey, (target) => {
        target.timeline = target.timeline.map((item) => item.id === userTimelineId ? { ...item, userDeliveryStatus: "failed" } : item);
      });
      onError(err instanceof Error ? err.message : "Failed to run coding agent");
    } finally {
      if (!streamStarted) {
        session.promptSubmissionInFlightRef.current = false;
        logChatDebug("run_prompt.cleanup_without_stream", {
          sessionKey: resolvedSessionKey,
          streamStarted,
        });
        mutateSession(resolvedSessionKey, (target) => {
          target.pendingCancelRef.current = false;
          target.isStopping = false;
          target.activeThinkingSummary = "";
          target.isSending = false;
          target.isSendingRef.current = false;
        });
      }
    }
  }, [activeChatSessionIdRef, appId, consumeRunStreamForSession, ensureSessionKeyByServerSessionId, getSession, markSessionRunActive, moveSessionTitleHint, mutateSession, onError, requestCancelForRun, setActiveChatSessionId]);

  const runPromptWithTimeline = useCallback(async (
    sessionKey: string,
    input: string,
    modelId?: string | null,
    clientMessageIdOverride?: string | null,
  ) => {
    const normalizedInput = input.trim();
    if (!normalizedInput) return;
    const clientMessageId = String(clientMessageIdOverride || "").trim() || createClientMessageId();
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
      logChatDebug("queue_drain.skipped", {
        sessionKey,
        isQueueDrainActive: session.isQueueDrainActiveRef.current,
        isSending: session.isSendingRef.current,
        queuedPromptCount: session.queuedPrompts.length,
      });
      return;
    }
    session.isQueueDrainActiveRef.current = true;
    try {
      while (!session.isSendingRef.current) {
        const nextPrompt = session.queuedPrompts[0];
        if (!nextPrompt) {
          break;
        }
        logChatDebug("queue_drain.dequeue", {
          sessionKey,
          promptId: nextPrompt.id,
          queuedPromptCount: session.queuedPrompts.length,
        });
        mutateSession(sessionKey, (target) => {
          target.queuedPrompts = target.queuedPrompts.slice(1);
        });
        await runPromptWithTimeline(sessionKey, nextPrompt.text, nextPrompt.modelId || null);
      }
    } finally {
      session.isQueueDrainActiveRef.current = false;
      logChatDebug("queue_drain.done", {
        sessionKey,
        queuedPromptCount: session.queuedPrompts.length,
        isSending: session.isSendingRef.current,
      });
    }
  }, [getSession, logChatDebug, mutateSession, runPromptWithTimeline]);

  const sendBuilderChat = useCallback(async (rawInput: string) => {
    const input = rawInput.trim();
    if (!input) return;
    let key = normalizeSessionKey(activeChatSessionIdRef.current);
    let sourceSession = getSession(key);
    const attachedServerSessionId = String(sourceSession.attachedRunSessionIdRef.current || "").trim();
    logChatDebug("send_chat.begin", {
      activeChatSessionId: String(activeChatSessionIdRef.current || "").trim() || null,
      initialSessionKey: key,
      isLocalSession: isLocalSessionKey(key),
      attachedServerSessionId: attachedServerSessionId || null,
      sourceIsSending: sourceSession.isSendingRef.current,
      sourcePendingCancel: sourceSession.pendingCancelRef.current,
    });
    if (isLocalSessionKey(key) && attachedServerSessionId && !isLocalSessionKey(attachedServerSessionId)) {
      key = ensureSessionKeyByServerSessionId(key, attachedServerSessionId);
      sourceSession = getSession(key);
      logChatDebug("send_chat.promoted_local_session", {
        promotedToSessionKey: key,
      });
    }
    if (sourceSession.isSendingRef.current || sourceSession.pendingCancelRef.current) {
      logChatDebug("send_chat.queued_on_busy_session", {
        sessionKey: key,
        isSending: sourceSession.isSendingRef.current,
        pendingCancel: sourceSession.pendingCancelRef.current,
      });
      mutateSession(key, (target) => {
        target.queuedPrompts = [...target.queuedPrompts, createQueuedPrompt(input, selectedRunModelId)];
      });
      return;
    }
    let draftRunClientMessageId: string | null = null;
    if (key === DRAFT_SESSION_KEY) {
      draftRunClientMessageId = createClientMessageId();
      key = promoteDraftSessionToLocalSession(createLocalSessionKey(draftRunClientMessageId));
      logChatDebug("send_chat.promoted_draft_session", {
        promotedToSessionKey: key,
        draftRunClientMessageId,
      });
    }
    const session = getSession(key);
    if (session.isSendingRef.current || session.pendingCancelRef.current) {
      logChatDebug("send_chat.queued_after_promotion", {
        sessionKey: key,
        isSending: session.isSendingRef.current,
        pendingCancel: session.pendingCancelRef.current,
      });
      mutateSession(key, (target) => {
        target.queuedPrompts = [...target.queuedPrompts, createQueuedPrompt(input, selectedRunModelId)];
      });
      return;
    }
    if (isLocalSessionKey(key)) {
      setSessionTitleHint(key, input);
    }
    await runPromptWithTimeline(key, input, selectedRunModelId, draftRunClientMessageId);
    const latestSessionKey = normalizeSessionKey(activeChatSessionIdRef.current);
    logChatDebug("send_chat.after_run_prompt", {
      originalSessionKey: key,
      latestSessionKey,
    });
    if (latestSessionKey && latestSessionKey !== key) {
      await drainQueuedPrompts(latestSessionKey);
    }
    await drainQueuedPrompts(key);
  }, [activeChatSessionIdRef, createClientMessageId, drainQueuedPrompts, ensureSessionKeyByServerSessionId, getSession, logChatDebug, mutateSession, promoteDraftSessionToLocalSession, runPromptWithTimeline, selectedRunModelId, setSessionTitleHint]);

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
    const abortLocalStreamAfterConfirmedCancel = () => {
      session.intentionalAbortRef.current = true;
      const reader = session.abortReaderRef.current;
      session.abortReaderRef.current = null;
      if (reader && typeof reader.cancel === "function") {
        void reader.cancel().catch(() => undefined);
      }
    };

    if (runIdToCancel) {
      void requestCancelForRun(runIdToCancel, session)
        .then(() => {
          abortLocalStreamAfterConfirmedCancel();
        })
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

    const sessionId = String(session.attachedRunSessionIdRef.current || activeChatSessionIdRef.current || "").trim();
    if (!sessionId) {
      return;
    }
    if (isLocalSessionKey(sessionId) && !session.attachedRunSessionIdRef.current) {
      return;
    }

    void (async () => {
      try {
        const active = await publishedAppsService.findCodingAgentChatSessionActiveRun(appId, sessionId);
        if (active && !parseTerminalRunStatus(active.status)) {
          await requestCancelForRun(active.run_id, session);
          abortLocalStreamAfterConfirmedCancel();
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
    activeChatSessionIdRef.current = null;
    setActiveChatSessionId(null);
  }, [activeChatSessionIdRef, mutateSession, setActiveChatSessionId]);

  return {
    sendBuilderChat,
    removeQueuedPrompt,
    answerPendingQuestion,
    stopCurrentRun,
    startNewChat,
  };
}
