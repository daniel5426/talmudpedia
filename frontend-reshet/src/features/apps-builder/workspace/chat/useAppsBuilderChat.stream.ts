import type { MutableRefObject } from "react";

import { publishedAppsService } from "@/services";

import { describeToolIntent, extractPrimaryToolPath, timelineId } from "./chat-model";
import {
  type CodingAgentPendingQuestion,
  parsePendingQuestionPayload,
  parseRunActiveDetail,
  parseSse,
  parseTerminalRunStatus,
  resolvePositiveTimeoutMs,
  TERMINAL_RUN_EVENTS,
} from "./stream-parsers";

type TerminalStatus = "completed" | "failed" | "cancelled" | "paused";
type ConsumeRunStreamOptions = {
  appId: string;
  runId: string;
  runSessionId?: string | null;
  streamAttachmentId?: number;
  getCurrentStreamAttachmentId?: () => number;
  activeTab: "preview" | "config";
  activeChatSessionIdRef: MutableRefObject<string | null>;
  setIsSending: (next: boolean) => void;
  setIsStopping: (next: boolean) => void;
  setActiveThinkingSummary: (next: string) => void;
  isSendingRef: MutableRefObject<boolean>;
  pendingCancelRef: MutableRefObject<boolean>;
  intentionalAbortRef: MutableRefObject<boolean>;
  activeRunIdRef: MutableRefObject<string | null>;
  lastKnownRunIdRef: MutableRefObject<string | null>;
  abortReaderRef: MutableRefObject<ReadableStreamDefaultReader<Uint8Array> | null>;
  isMountedRef: MutableRefObject<boolean>;
  seenRunEventKeysRef: MutableRefObject<Set<string>>;
  onError: (message: string | null) => void;
  onSetCurrentRevisionId: (revisionId: string | null) => void;
  pushTimeline: (item: {
    kind?: "assistant" | "user" | "tool";
    title: string;
    description?: string;
    tone?: "default" | "success" | "error";
  }) => void;
  upsertAssistantTimeline: (assistantStreamId: string, description: string) => void;
  upsertToolTimeline: (
    toolCallId: string,
    title: string,
    status: "running" | "completed" | "failed",
    toolName: string,
    toolPath?: string | null,
  ) => void;
  finalizeRunningTools: (status: "completed" | "failed") => void;
  attachCheckpointToLastUser: (checkpointId: string) => void;
  refreshStateSilently: () => Promise<void>;
  ensureDraftDevSession: () => Promise<void>;
  loadChatSessions: () => Promise<unknown[]>;
  requestCancelForRun: (runId: string) => Promise<void>;
  onQuestionAsked: (question: CodingAgentPendingQuestion) => void;
  onQuestionResolved: (requestId?: string) => void;
  shouldEnsureDraftPreviewAfterRun?: (params: {
    runId: string;
    sessionId: string | null;
    terminalStatus: TerminalStatus | null;
  }) => boolean;
  onRunTerminalized?: (params: {
    sessionId: string;
    runId: string;
    terminalStatus: TerminalStatus | null;
    sawTerminalEvent: boolean;
  }) => void | Promise<void>;
  onPostRunHydrationStateChange?: (inProgress: boolean) => void;
};

function findSseFrameBoundary(buffer: string): { index: number; delimiterLength: number } | null {
  const lfBoundary = buffer.indexOf("\n\n");
  const crlfBoundary = buffer.indexOf("\r\n\r\n");
  if (lfBoundary < 0 && crlfBoundary < 0) {
    return null;
  }
  if (lfBoundary < 0) {
    return { index: crlfBoundary, delimiterLength: 4 };
  }
  if (crlfBoundary < 0) {
    return { index: lfBoundary, delimiterLength: 2 };
  }
  if (lfBoundary <= crlfBoundary) {
    return { index: lfBoundary, delimiterLength: 2 };
  }
  return { index: crlfBoundary, delimiterLength: 4 };
}

export async function consumeRunStream(options: ConsumeRunStreamOptions): Promise<void> {
  const {
    appId,
    runId,
    runSessionId,
    streamAttachmentId,
    getCurrentStreamAttachmentId,
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
    onQuestionAsked,
    onQuestionResolved,
    shouldEnsureDraftPreviewAfterRun,
    onRunTerminalized,
    onPostRunHydrationStateChange,
  } = options;

  const normalizedRunId = String(runId || "").trim();
  const normalizedRunSessionId = String(runSessionId || activeChatSessionIdRef.current || "").trim();
  const resolvedStreamAttachmentId = Number.isFinite(Number(streamAttachmentId))
    ? Number(streamAttachmentId)
    : 0;
  const resolvedGetCurrentStreamAttachmentId =
    typeof getCurrentStreamAttachmentId === "function"
      ? getCurrentStreamAttachmentId
      : () => resolvedStreamAttachmentId;
  const isCurrentAttachment = (): boolean =>
    resolvedGetCurrentStreamAttachmentId() === resolvedStreamAttachmentId;
  const canMutateUi = (): boolean => isCurrentAttachment() && isMountedRef.current;
  if (!normalizedRunId) {
    return;
  }
  if (!isCurrentAttachment()) {
    return;
  }

  setIsSending(true);
  isSendingRef.current = true;
  setIsStopping(Boolean(pendingCancelRef.current));
  onError(null);
  if (!pendingCancelRef.current) {
    setActiveThinkingSummary("Thinking...");
  }

  intentionalAbortRef.current = false;
  activeRunIdRef.current = normalizedRunId;
  lastKnownRunIdRef.current = normalizedRunId;

  let shouldSuppressErrors = false;
  let sawTerminalEvent = false;
  let terminalStatus: TerminalStatus | null = null;
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  const logRunFailureDebug = (
    reason: string,
    details: Record<string, unknown> = {},
  ): void => {
    if (typeof console === "undefined" || typeof console.error !== "function") {
      return;
    }
    console.error("[coding-agent][run-failed]", {
      reason,
      appId,
      runId: normalizedRunId,
      runSessionId: normalizedRunSessionId || null,
      ...details,
    });
  };

  try {
    const decoder = new TextDecoder();
    let buffer = "";
    let assistantText = "";
    let sawAssistantOutput = false;
    let sawToolActivity = false;
    let currentStreamId = `assistant-${normalizedRunId}`;
    let segmentCounter = 0;
    let latestSummary = "";
    let latestResultRevisionId = "";
    let latestBackendFailureMessage = "";
    let sawRunFailure = false;
    let sawInactivityTimeout = false;
    let sawMaxDurationTimeout = false;
    let recoveryCancelAttempted = false;
    let recoveryCancelConfirmed = false;

    const STALL_TIMEOUT_MS = resolvePositiveTimeoutMs(
      process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_STALL_TIMEOUT_MS,
      45000,
    );
    const MAX_RUN_DURATION_MS = resolvePositiveTimeoutMs(
      process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_MAX_DURATION_MS,
      240000,
    );
    const READ_POLL_TIMEOUT_MS = Math.min(
      STALL_TIMEOUT_MS,
      resolvePositiveTimeoutMs(process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_READ_POLL_TIMEOUT_MS, 2000),
    );
    const autoCancelRecoveryRaw = String(
      process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_AUTO_CANCEL_RECOVERY_ENABLED || "0",
    )
      .trim()
      .toLowerCase();
    const AUTO_CANCEL_RECOVERY_ENABLED = autoCancelRecoveryRaw === "1" || autoCancelRecoveryRaw === "true";
    const runStartedAt = Date.now();
    let lastEventAt = Date.now();
    let maxDurationNoticeShown = false;
    let stallNoticeShown = false;
    let pendingRead:
      | Promise<{ ok: true; result: ReadableStreamReadResult<Uint8Array> } | { ok: false; error: unknown }>
      | null = null;
    const yieldForPaint = async (): Promise<void> => {
      if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
        await new Promise<void>((resolve) => {
          window.requestAnimationFrame(() => resolve());
        });
        return;
      }
      await new Promise<void>((resolve) => {
        setTimeout(resolve, 0);
      });
    };

    const readWithPollingTimeout = async (
      timeoutMs: number,
    ): Promise<ReadableStreamReadResult<Uint8Array> | null> => {
      const activeReader = reader;
      if (!activeReader) {
        return null;
      }
      if (!pendingRead) {
        pendingRead = activeReader
          .read()
          .then(
            (result) => ({ ok: true as const, result }),
            (error: unknown) => ({ ok: false as const, error }),
          );
      }
      const timeoutToken = Symbol("coding-agent-stream-read-timeout");
      const raced = await Promise.race<
        { ok: true; result: ReadableStreamReadResult<Uint8Array> } | { ok: false; error: unknown } | typeof timeoutToken
      >([
        pendingRead,
        new Promise<typeof timeoutToken>((resolve) => {
          setTimeout(() => resolve(timeoutToken), timeoutMs);
        }),
      ]);
      if (raced === timeoutToken) {
        return null;
      }
      pendingRead = null;
      if (!raced.ok) {
        throw raced.error;
      }
      return raced.result;
    };

    const requestRecoveryCancel = async (): Promise<void> => {
      if (pendingCancelRef.current || recoveryCancelAttempted) {
        return;
      }
      recoveryCancelAttempted = true;
      pendingCancelRef.current = true;
      setIsStopping(true);
      try {
        await requestCancelForRun(normalizedRunId);
        recoveryCancelConfirmed = true;
      } catch (err) {
        if (!intentionalAbortRef.current) {
          onError(err instanceof Error ? err.message : "Failed to cancel stuck coding-agent run");
        }
      }
    };

    const reconcileTerminalStateFromBackend = async (): Promise<boolean> => {
      try {
        const run = await publishedAppsService.getCodingAgentRun(appId, normalizedRunId);
        const terminal = parseTerminalRunStatus(run.status);
        if (!terminal) {
          return false;
        }
        sawTerminalEvent = true;
        terminalStatus = terminal;
        if (terminal === "failed") {
          sawRunFailure = true;
          latestBackendFailureMessage = String(run.error || "").trim();
        }
        return true;
      } catch {
        return false;
      }
    };

    const waitForBackendTerminalState = async (timeoutMs: number): Promise<boolean> => {
      const deadline = Date.now() + timeoutMs;
      while (Date.now() < deadline && !intentionalAbortRef.current) {
        const reconciled = await reconcileTerminalStateFromBackend();
        if (reconciled) {
          return true;
        }
        await new Promise<void>((resolve) => {
          setTimeout(resolve, 250);
        });
      }
      return false;
    };

    const openStreamReader = async (): Promise<boolean> => {
      const response = await publishedAppsService.streamCodingAgentRun(appId, normalizedRunId);
      if (!response.ok) {
        let message = `Failed to stream coding-agent run (${response.status})`;
        let errorPayload: unknown = null;
        let responseDetail: unknown = null;
        try {
          const payload = await response.json();
          errorPayload = payload;
          responseDetail = (payload as { detail?: unknown } | null)?.detail ?? null;
          if (typeof responseDetail === "string") {
            message = responseDetail;
          } else if (responseDetail && typeof responseDetail === "object") {
            message = JSON.stringify(responseDetail);
          }
        } catch {
          // keep fallback
        }
        logRunFailureDebug("stream_response_not_ok", {
          status: response.status,
          statusText: response.statusText,
          responsePayload: errorPayload,
        });
        throw new Error(message);
      }
      const nextReader = response.body?.getReader();
      if (!nextReader) {
        throw new Error("Streaming reader unavailable");
      }
      reader = nextReader;
      abortReaderRef.current = nextReader;
      pendingRead = null;
      buffer = "";
      lastEventAt = Date.now();
      return true;
    };

    while (true) {
      if (intentionalAbortRef.current) {
        sawTerminalEvent = true;
        shouldSuppressErrors = true;
        break;
      }
      if (!isCurrentAttachment()) {
        sawTerminalEvent = true;
        shouldSuppressErrors = true;
        break;
      }
      if (!reader) {
        const opened = await openStreamReader();
        if (!opened) {
          if (sawTerminalEvent || intentionalAbortRef.current || !isCurrentAttachment()) {
            break;
          }
          continue;
        }
      }

      const now = Date.now();
      if (now - runStartedAt > MAX_RUN_DURATION_MS) {
        sawMaxDurationTimeout = true;
        if (AUTO_CANCEL_RECOVERY_ENABLED) {
          sawRunFailure = true;
          await requestRecoveryCancel();
          if (reader && typeof reader.cancel === "function") {
            void reader.cancel().catch(() => undefined);
          }
          break;
        }
        if (!maxDurationNoticeShown && isCurrentAttachment()) {
          onError("Coding-agent run is still active beyond the local stream duration limit. Waiting for backend progress.");
          maxDurationNoticeShown = true;
        }
      }
      if (now - lastEventAt > STALL_TIMEOUT_MS) {
        sawInactivityTimeout = true;
        if (AUTO_CANCEL_RECOVERY_ENABLED) {
          sawRunFailure = true;
          await requestRecoveryCancel();
          if (reader && typeof reader.cancel === "function") {
            void reader.cancel().catch(() => undefined);
          }
          break;
        }
        // Non-destructive stall handling: keep the run alive and continue polling.
        lastEventAt = now;
        if (!stallNoticeShown && isCurrentAttachment()) {
          onError("No stream updates yet. The run is still active; waiting for backend progress.");
          stallNoticeShown = true;
        }
      }

      let readResult: ReadableStreamReadResult<Uint8Array> | null = null;
      try {
        readResult = await readWithPollingTimeout(READ_POLL_TIMEOUT_MS);
      } catch (readError) {
        pendingRead = null;
        const reconciled = await reconcileTerminalStateFromBackend();
        if (reconciled) {
          break;
        }
        if (reader && typeof reader.cancel === "function") {
          void reader.cancel().catch(() => undefined);
        }
        reader = null;
        abortReaderRef.current = null;
        logRunFailureDebug("stream_read_error", {
          error: readError instanceof Error ? readError.message : String(readError || ""),
        });
        break;
      }
      if (!readResult) {
        continue;
      }
      const { done, value } = readResult;
      if (done) {
        pendingRead = null;
        if (!sawTerminalEvent && !intentionalAbortRef.current) {
          const reconciled = await reconcileTerminalStateFromBackend();
          if (reconciled) {
            break;
          }
          if (reader && typeof reader.cancel === "function") {
            void reader.cancel().catch(() => undefined);
          }
          reader = null;
          abortReaderRef.current = null;
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      let boundary = findSseFrameBoundary(buffer);
      let parsedEventsInThisRead = 0;
      let parsedAssistantDeltasInThisRead = 0;
      while (boundary) {
        const raw = buffer.slice(0, boundary.index).trim();
        buffer = buffer.slice(boundary.index + boundary.delimiterLength);
        const parsed = parseSse(raw);
        if (!parsed) {
          boundary = findSseFrameBoundary(buffer);
          continue;
        }

        parsedEventsInThisRead += 1;
        const seq = Number(parsed.seq || 0);
        if (seq > 0) {
          const eventKey = `${normalizedRunId}:${seq}`;
          if (seenRunEventKeysRef.current.has(eventKey)) {
            boundary = findSseFrameBoundary(buffer);
            continue;
          }
          seenRunEventKeysRef.current.add(eventKey);
        }

        lastEventAt = Date.now();
        const payload = (parsed.payload || {}) as Record<string, unknown>;
        if (!isCurrentAttachment()) {
          sawTerminalEvent = true;
          shouldSuppressErrors = true;
          break;
        }

        if (parsed.event === "assistant.delta" && payload.content) {
          const chunkText = String(payload.content);
          assistantText += chunkText;
          parsedAssistantDeltasInThisRead += 1;
          if (assistantText.trim()) {
            sawAssistantOutput = true;
            setActiveThinkingSummary("");
            upsertAssistantTimeline(currentStreamId, assistantText);
          }
          // If many frames arrive in one read burst, explicitly yield for paint so
          // the chat does not collapse all deltas into one final render.
          if (
            parsedEventsInThisRead > 1 &&
            (parsedAssistantDeltasInThisRead <= 8 || parsedAssistantDeltasInThisRead % 2 === 0)
          ) {
            await yieldForPaint();
          }
          boundary = findSseFrameBoundary(buffer);
          continue;
        }

        if (parsed.event === "plan.updated") {
          const summary = String(payload.summary || "").trim();
          if (summary && summary.toLowerCase() !== "coding-agent run started") {
            latestSummary = summary;
            setActiveThinkingSummary(summary);
          }
        }

        if (parsed.event === "tool.started") {
          sawToolActivity = true;
          const toolName = String(payload.tool || "tool");
          const toolCallId = String(payload.span_id || `${toolName}-${timelineId("call")}`);
          const toolPath = extractPrimaryToolPath(payload.input || payload);
          if (assistantText.trim()) {
            upsertAssistantTimeline(currentStreamId, assistantText.trim());
          }
          assistantText = "";
          segmentCounter += 1;
          currentStreamId = `assistant-${normalizedRunId}-seg${segmentCounter}`;
          upsertToolTimeline(toolCallId, describeToolIntent(toolName), "running", toolName, toolPath);
        }

        if (parsed.event === "tool.completed") {
          sawToolActivity = true;
          const toolName = String(payload.tool || "tool");
          const toolCallId = String(payload.span_id || `${toolName}-${timelineId("call")}`);
          const toolPath = extractPrimaryToolPath(payload.output || payload);
          upsertToolTimeline(toolCallId, describeToolIntent(toolName), "completed", toolName, toolPath);
        }

        if (parsed.event === "tool.failed") {
          sawToolActivity = true;
          const toolName = String(payload.tool || "tool");
          const toolCallId = String(payload.span_id || `${toolName}-${timelineId("call")}`);
          const toolPath = extractPrimaryToolPath(payload.output || payload);
          upsertToolTimeline(toolCallId, describeToolIntent(toolName), "failed", toolName, toolPath);
        }

        if (parsed.event === "tool.question") {
          sawToolActivity = true;
          const pendingQuestion = parsePendingQuestionPayload(payload);
          if (pendingQuestion) {
            onQuestionAsked(pendingQuestion);
          }
        }

        if (parsed.event === "tool.question.answered" || parsed.event === "tool.question.rejected") {
          sawToolActivity = true;
          const requestId = String(payload.request_id || payload.requestId || "").trim() || undefined;
          onQuestionResolved(requestId);
        }

        if (
          parsedEventsInThisRead > 1 &&
          (
            parsed.event === "tool.started"
            || parsed.event === "tool.completed"
            || parsed.event === "tool.failed"
            || parsed.event === "tool.question"
            || parsed.event === "tool.question.answered"
            || parsed.event === "tool.question.rejected"
          )
        ) {
          await yieldForPaint();
        }

        if (parsed.event === "revision.created") {
          const revisionId = String(payload.revision_id || "");
          latestResultRevisionId = revisionId || latestResultRevisionId;
          if (revisionId) {
            onSetCurrentRevisionId(revisionId);
          }
        }

        if (parsed.event === "checkpoint.created") {
          const revisionId = String(payload.revision_id || "");
          const checkpointId = String(payload.checkpoint_id || "");
          if (revisionId) {
            onSetCurrentRevisionId(revisionId);
          }
          if (checkpointId) {
            attachCheckpointToLastUser(checkpointId);
          }
        }

        if (parsed.event === "run.failed") {
          sawRunFailure = true;
          sawTerminalEvent = true;
          terminalStatus = "failed";
          finalizeRunningTools("failed");
          const payloadFailureMessage = String(payload.error || payload.message || payload.reason || "").trim();
          const failureMessage = String(
            parsed.diagnostics?.[0]?.message || payloadFailureMessage || "Coding-agent run failed",
          );
          latestBackendFailureMessage = failureMessage;
          logRunFailureDebug("run.failed_event", {
            event: parsed.event,
            seq: parsed.seq,
            ts: parsed.ts,
            stage: parsed.stage,
            streamEvent: parsed,
            eventPayload: parsed.payload,
            diagnostics: parsed.diagnostics,
            resolvedFailureMessage: failureMessage,
          });
          if (!intentionalAbortRef.current && !pendingCancelRef.current) {
            onError(failureMessage);
          } else {
            shouldSuppressErrors = true;
          }
        }

        if (parsed.event !== "run.failed" && Array.isArray(parsed.diagnostics) && parsed.diagnostics.length > 0) {
          const diagnosticMessage = String(parsed.diagnostics[0]?.message || "").trim();
          if (diagnosticMessage && !intentionalAbortRef.current && !pendingCancelRef.current) {
            onError(diagnosticMessage);
          }
        }

        if (TERMINAL_RUN_EVENTS.has(parsed.event)) {
          sawTerminalEvent = true;
          onQuestionResolved();
          if (parsed.event === "run.cancelled") {
            terminalStatus = "cancelled";
          } else if (parsed.event === "run.paused") {
            terminalStatus = "paused";
          } else if (parsed.event === "run.completed") {
            terminalStatus = "completed";
          }
          finalizeRunningTools(parsed.event === "run.failed" ? "failed" : "completed");
        }

        if (sawTerminalEvent) {
          if (reader && typeof reader.cancel === "function") {
            void reader.cancel().catch(() => undefined);
          }
          reader = null;
          abortReaderRef.current = null;
          pendingRead = null;
          break;
        }

        if (parsedEventsInThisRead % 12 === 0) {
          await yieldForPaint();
        }
        boundary = findSseFrameBoundary(buffer);
      }

      if (sawTerminalEvent) {
        break;
      }
    }
    if (sawMaxDurationTimeout && !sawTerminalEvent && !intentionalAbortRef.current) {
      if (isCurrentAttachment()) {
        onError(
          AUTO_CANCEL_RECOVERY_ENABLED
            ? (recoveryCancelConfirmed
              ? "Coding-agent run exceeded maximum duration. The run was stopped to recover."
              : "Coding-agent run exceeded maximum duration and cancellation could not be confirmed.")
            : "Coding-agent run exceeded the local stream duration limit. The run may still be active.",
        );
      }
    } else if (sawInactivityTimeout && !sawTerminalEvent && !intentionalAbortRef.current) {
      if (isCurrentAttachment()) {
        onError(
          AUTO_CANCEL_RECOVERY_ENABLED
            ? (recoveryCancelConfirmed
              ? "Coding-agent stream stalled before completion. The run was stopped to recover."
              : "Coding-agent stream stalled before completion and cancellation could not be confirmed.")
            : "Coding-agent stream stalled before completion. The run may still be active.",
        );
      }
    } else if (!sawTerminalEvent && !intentionalAbortRef.current) {
      const reconciledImmediately = await reconcileTerminalStateFromBackend();
      const TERMINAL_RECONCILE_TIMEOUT_MS = resolvePositiveTimeoutMs(
        process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_TERMINAL_RECONCILE_TIMEOUT_MS,
        5000,
      );
      if (!reconciledImmediately) {
        if (AUTO_CANCEL_RECOVERY_ENABLED) {
          await requestRecoveryCancel();
          const reconciledAfterRecovery = await waitForBackendTerminalState(TERMINAL_RECONCILE_TIMEOUT_MS);
          if (!reconciledAfterRecovery) {
            sawRunFailure = true;
            if (isCurrentAttachment()) {
              onError(
                recoveryCancelConfirmed
                  ? "Coding-agent stream ended before a terminal event. The run was stopped to recover."
                  : "Coding-agent stream ended before a terminal event and cancellation could not be confirmed.",
              );
            }
          }
        } else {
          const reconciledAfterWait = await waitForBackendTerminalState(TERMINAL_RECONCILE_TIMEOUT_MS);
          if (!reconciledAfterWait && isCurrentAttachment()) {
            onError("Coding-agent stream disconnected before a terminal event. The run may still be active.");
          }
        }
      }
      if (terminalStatus === "failed" && !pendingCancelRef.current && isCurrentAttachment()) {
        onError(latestBackendFailureMessage || "Coding-agent run failed");
      }
    } else if (
      !intentionalAbortRef.current &&
      terminalStatus === "failed" &&
      !pendingCancelRef.current
    ) {
      if (isCurrentAttachment()) {
        onError(latestBackendFailureMessage || "Coding-agent run failed");
      }
    }

    if (!intentionalAbortRef.current && (sawRunFailure || sawTerminalEvent)) {
      finalizeRunningTools(sawRunFailure ? "failed" : "completed");
    }

    if (!intentionalAbortRef.current) {
      const finalAssistantText =
        assistantText.trim() ||
        latestSummary;

      if (assistantText.trim()) {
        sawAssistantOutput = true;
        upsertAssistantTimeline(currentStreamId, assistantText.trim());
      } else if (finalAssistantText) {
        pushTimeline({
          kind: "assistant",
          title: "Assistant",
          description: finalAssistantText,
          tone: "default",
        });
      }
    }

    const finalizeAfterRun = async () => {
      const isAttachedRun = (): boolean =>
        String(activeRunIdRef.current || "").trim() === normalizedRunId;
      const parseRunActiveFromError = (err: unknown) =>
        parseRunActiveDetail(err instanceof Error ? err.message : String(err || ""));
      let activeRunCount: number | null = null;
      if (isCurrentAttachment() && isAttachedRun()) {
        try {
          const state = await publishedAppsService.getBuilderState(appId);
          activeRunCount = Number(state?.draft_dev?.active_coding_run_count || 0);
        } catch {
          activeRunCount = null;
        }
      }
      const hasActiveRunsInScope = activeRunCount !== null && activeRunCount > 0;
      if (isCurrentAttachment() && isAttachedRun() && !hasActiveRunsInScope) {
        try {
          await refreshStateSilently();
        } catch (err) {
          if (!parseRunActiveFromError(err)) {
            throw err;
          }
        }
      }
      const shouldEnsurePreview =
        shouldEnsureDraftPreviewAfterRun?.({
          runId: normalizedRunId,
          sessionId: normalizedRunSessionId || null,
          terminalStatus,
        }) ?? isAttachedRun();
      if (
        isCurrentAttachment()
        && isAttachedRun()
        && !hasActiveRunsInScope
        && activeTab === "preview"
        && shouldEnsurePreview
      ) {
        try {
          await ensureDraftDevSession();
        } catch (err) {
          if (!parseRunActiveFromError(err)) {
            throw err;
          }
        }
      }
      if (isCurrentAttachment() && isAttachedRun() && !hasActiveRunsInScope && latestResultRevisionId) {
        onSetCurrentRevisionId(latestResultRevisionId);
      }
      if (isCurrentAttachment()) {
        await loadChatSessions();
      }
    };

    const finalizeAfterRunWithTracking = async () => {
      onPostRunHydrationStateChange?.(true);
      try {
        await finalizeAfterRun();
      } finally {
        onPostRunHydrationStateChange?.(false);
      }
    };

    if (process.env.NODE_ENV === "test") {
      try {
        await finalizeAfterRunWithTracking();
      } catch (err) {
        if (!intentionalAbortRef.current && canMutateUi() && !shouldSuppressErrors) {
          onError(err instanceof Error ? err.message : "Failed to refresh builder state after run");
        }
      }
    } else {
      void finalizeAfterRunWithTracking().catch((err) => {
        if (!intentionalAbortRef.current && canMutateUi() && !shouldSuppressErrors) {
          onError(err instanceof Error ? err.message : "Failed to refresh builder state after run");
        }
      });
    }
  } catch (err) {
    const isAbortError =
      typeof err === "object" &&
      err !== null &&
      "name" in err &&
      String((err as { name?: string }).name || "") === "AbortError";
    if (!isAbortError) {
      logRunFailureDebug("stream_consume_exception", {
        error: err,
      });
    }
    if (!intentionalAbortRef.current && !isAbortError && !shouldSuppressErrors && isCurrentAttachment()) {
      onError(err instanceof Error ? err.message : "Failed to run coding agent");
    }
  } finally {
    if (reader && typeof reader.cancel === "function") {
      void reader.cancel().catch(() => undefined);
    }
    reader = null;
    if (!intentionalAbortRef.current && normalizedRunSessionId && onRunTerminalized) {
      try {
        await onRunTerminalized({
          sessionId: normalizedRunSessionId,
          runId: normalizedRunId,
          terminalStatus,
          sawTerminalEvent,
        });
      } catch {
        // Best-effort callback; stream cleanup must continue.
      }
    }
    if (!isCurrentAttachment()) {
      return;
    }
    onQuestionResolved();
    abortReaderRef.current = null;
    if (activeRunIdRef.current === normalizedRunId) {
      activeRunIdRef.current = null;
    }
    if (lastKnownRunIdRef.current === normalizedRunId) {
      lastKnownRunIdRef.current = null;
    }
    pendingCancelRef.current = false;
    setIsStopping(false);
    if (!isMountedRef.current) {
      return;
    }
    setActiveThinkingSummary("");
    setIsSending(false);
    isSendingRef.current = false;
  }
}
