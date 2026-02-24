import type { MutableRefObject } from "react";

import { publishedAppsService } from "@/services";

import { describeToolIntent, extractPrimaryToolPath, timelineId } from "./chat-model";
import {
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
};

const WRITE_TOOL_HINTS = [
  "apply_patch",
  "write",
  "rename",
  "delete",
  "remove",
  "move",
  "mkdir",
  "touch",
  "create",
  "edit",
  "replace",
  "insert",
  "append",
  "prepend",
];

function isLikelyWorkspaceWriteTool(toolName: string): boolean {
  const normalized = String(toolName || "").trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return WRITE_TOOL_HINTS.some((hint) => normalized.includes(hint));
}

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
  } = options;

  const normalizedRunId = String(runId || "").trim();
  if (!normalizedRunId) {
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

  try {
    const response = await publishedAppsService.streamCodingAgentRun(appId, normalizedRunId);
    if (!response.ok) {
      let message = `Failed to stream coding-agent run (${response.status})`;
      try {
        const payload = await response.json();
        const detail = payload?.detail;
        if (typeof detail === "string") {
          message = detail;
        } else if (detail && typeof detail === "object") {
          message = JSON.stringify(detail);
        }
      } catch {
        // keep fallback
      }
      throw new Error(message);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("Streaming reader unavailable");
    }
    abortReaderRef.current = reader;

    const decoder = new TextDecoder();
    let buffer = "";
    let assistantText = "";
    let currentStreamId = `assistant-${normalizedRunId}`;
    let segmentCounter = 0;
    let latestSummary = "";
    let latestResultRevisionId = "";
    let latestBackendFailureMessage = "";
    let sawRunFailure = false;
    let sawTerminalEvent = false;
    let sawInactivityTimeout = false;
    let sawMaxDurationTimeout = false;
    let recoveryCancelAttempted = false;
    let recoveryCancelConfirmed = false;
    let terminalStatus: TerminalStatus | null = null;
    let sawLikelyWriteToolEvent = false;

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
    const runStartedAt = Date.now();
    let lastEventAt = Date.now();
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
      if (!pendingRead) {
        pendingRead = reader
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

    while (true) {
      if (intentionalAbortRef.current) {
        sawTerminalEvent = true;
        shouldSuppressErrors = true;
        break;
      }
      const now = Date.now();
      if (now - runStartedAt > MAX_RUN_DURATION_MS) {
        sawMaxDurationTimeout = true;
        sawRunFailure = true;
        await requestRecoveryCancel();
        if (typeof reader.cancel === "function") {
          void reader.cancel().catch(() => undefined);
        }
        break;
      }
      if (now - lastEventAt > STALL_TIMEOUT_MS) {
        sawInactivityTimeout = true;
        sawRunFailure = true;
        await requestRecoveryCancel();
        if (typeof reader.cancel === "function") {
          void reader.cancel().catch(() => undefined);
        }
        break;
      }

      const readResult = await readWithPollingTimeout(READ_POLL_TIMEOUT_MS);
      if (!readResult) {
        continue;
      }
      const { done, value } = readResult;
      if (done) break;

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

        if (parsed.event === "assistant.delta" && payload.content) {
          const chunkText = String(payload.content);
          assistantText += chunkText;
          parsedAssistantDeltasInThisRead += 1;
          if (assistantText.trim()) {
            setActiveThinkingSummary("");
            upsertAssistantTimeline(currentStreamId, assistantText);
          }
          // If many frames arrive in one read burst, explicitly yield for paint so
          // the chat does not collapse all deltas into one final render.
          if (
            parsedEventsInThisRead > 1 &&
            (parsedAssistantDeltasInThisRead <= 6 || parsedAssistantDeltasInThisRead % 4 === 0)
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
          const toolName = String(payload.tool || "tool");
          if (isLikelyWorkspaceWriteTool(toolName)) {
            sawLikelyWriteToolEvent = true;
          }
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
          const toolName = String(payload.tool || "tool");
          if (isLikelyWorkspaceWriteTool(toolName)) {
            sawLikelyWriteToolEvent = true;
          }
          const toolCallId = String(payload.span_id || `${toolName}-${timelineId("call")}`);
          const toolPath = extractPrimaryToolPath(payload.output || payload);
          upsertToolTimeline(toolCallId, describeToolIntent(toolName), "completed", toolName, toolPath);
        }

        if (parsed.event === "tool.failed") {
          const toolName = String(payload.tool || "tool");
          if (isLikelyWorkspaceWriteTool(toolName)) {
            sawLikelyWriteToolEvent = true;
          }
          const toolCallId = String(payload.span_id || `${toolName}-${timelineId("call")}`);
          const toolPath = extractPrimaryToolPath(payload.output || payload);
          upsertToolTimeline(toolCallId, describeToolIntent(toolName), "failed", toolName, toolPath);
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
          const failureMessage = String(
            parsed.diagnostics?.[0]?.message || payload.error || "Coding-agent run failed",
          );
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
          if (typeof reader.cancel === "function") {
            void reader.cancel().catch(() => undefined);
          }
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
    if (sawMaxDurationTimeout && !intentionalAbortRef.current) {
      onError(
        recoveryCancelConfirmed
          ? "Coding-agent run exceeded maximum duration. The run was stopped to recover."
          : "Coding-agent run exceeded maximum duration and cancellation could not be confirmed.",
      );
    } else if (sawInactivityTimeout && !intentionalAbortRef.current) {
      onError(
        recoveryCancelConfirmed
          ? "Coding-agent stream stalled before completion. The run was stopped to recover."
          : "Coding-agent stream stalled before completion and cancellation could not be confirmed.",
      );
    } else if (!sawTerminalEvent && !intentionalAbortRef.current) {
      const reconciledImmediately = await reconcileTerminalStateFromBackend();
      const TERMINAL_RECONCILE_TIMEOUT_MS = resolvePositiveTimeoutMs(
        process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_TERMINAL_RECONCILE_TIMEOUT_MS,
        5000,
      );
      if (!reconciledImmediately) {
        await requestRecoveryCancel();
        const reconciledAfterRecovery = await waitForBackendTerminalState(TERMINAL_RECONCILE_TIMEOUT_MS);
        if (!reconciledAfterRecovery) {
          sawRunFailure = true;
          onError(
            recoveryCancelConfirmed
              ? "Coding-agent stream ended before a terminal event. The run was stopped to recover."
              : "Coding-agent stream ended before a terminal event and cancellation could not be confirmed.",
          );
        }
      }
      if (terminalStatus === "failed" && !pendingCancelRef.current) {
        onError(latestBackendFailureMessage || "Coding-agent run failed");
      }
    } else if (
      !intentionalAbortRef.current &&
      terminalStatus === "failed" &&
      !pendingCancelRef.current
    ) {
      onError("Coding-agent run failed");
    }

    if (!intentionalAbortRef.current) {
      finalizeRunningTools(sawRunFailure ? "failed" : "completed");
    }

    if (!intentionalAbortRef.current) {
      const finalAssistantText =
        assistantText.trim() ||
        latestSummary ||
        (sawRunFailure
          ? ""
          : "I can help with code changes in this app workspace. Tell me what you want to change.");

      if (assistantText.trim()) {
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
      const waitForResultRevisionIfNeeded = async () => {
        if (terminalStatus !== "completed" || !sawLikelyWriteToolEvent) {
          return;
        }
        const timeoutMs = resolvePositiveTimeoutMs(
          process.env.NEXT_PUBLIC_APPS_CODING_AGENT_POST_RUN_REVISION_WAIT_TIMEOUT_MS,
          30000,
        );
        const pollMs = Math.min(
          timeoutMs,
          resolvePositiveTimeoutMs(process.env.NEXT_PUBLIC_APPS_CODING_AGENT_POST_RUN_REVISION_WAIT_POLL_MS, 400),
        );
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline && !intentionalAbortRef.current) {
          try {
            const run = await publishedAppsService.getCodingAgentRun(appId, normalizedRunId);
            const status = parseTerminalRunStatus(run.status);
            if (status && status !== "completed") {
              return;
            }
            const revisionId = String(run.result_revision_id || run.checkpoint_revision_id || "").trim();
            if (revisionId) {
              latestResultRevisionId = revisionId;
              return;
            }
          } catch {
            // Best-effort polling only.
          }
          await new Promise<void>((resolve) => {
            setTimeout(resolve, pollMs);
          });
        }
      };

      const waitForBuilderDraftRevisionIfNeeded = async () => {
        if (terminalStatus !== "completed") {
          return;
        }
        const expectedRevisionId = String(latestResultRevisionId || "").trim();
        if (!expectedRevisionId) {
          return;
        }
        const timeoutMs = resolvePositiveTimeoutMs(
          process.env.NEXT_PUBLIC_APPS_CODING_AGENT_POST_RUN_BUILDER_STATE_WAIT_TIMEOUT_MS,
          30000,
        );
        const pollMs = Math.min(
          timeoutMs,
          resolvePositiveTimeoutMs(
            process.env.NEXT_PUBLIC_APPS_CODING_AGENT_POST_RUN_BUILDER_STATE_WAIT_POLL_MS,
            400,
          ),
        );
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline && !intentionalAbortRef.current) {
          try {
            const state = await publishedAppsService.getBuilderState(appId);
            const draftRevisionId = String(
              state.current_draft_revision?.id || state.app?.current_draft_revision_id || "",
            ).trim();
            if (draftRevisionId && draftRevisionId === expectedRevisionId) {
              return;
            }
          } catch {
            // Best-effort polling only.
          }
          await new Promise<void>((resolve) => {
            setTimeout(resolve, pollMs);
          });
        }
      };

      await waitForResultRevisionIfNeeded();
      await waitForBuilderDraftRevisionIfNeeded();
      await refreshStateSilently();
      if (activeTab === "preview") {
        const maxEnsureAttempts = 6;
        for (let attempt = 0; attempt < maxEnsureAttempts; attempt += 1) {
          try {
            await ensureDraftDevSession();
            break;
          } catch (err) {
            const runActive = parseRunActiveDetail(err instanceof Error ? err.message : String(err || ""));
            if (!runActive) {
              throw err;
            }
            const conflictingRunId = String(runActive.active_run_id || "").trim();
            if (conflictingRunId && conflictingRunId !== normalizedRunId) {
              break;
            }
            if (attempt + 1 >= maxEnsureAttempts) {
              throw err;
            }
            const retryDelayMs = 120 * (attempt + 1);
            await new Promise<void>((resolve) => {
              setTimeout(resolve, retryDelayMs);
            });
          }
        }
      }
      if (latestResultRevisionId) {
        onSetCurrentRevisionId(latestResultRevisionId);
      }
      await loadChatSessions();
    };

    if (process.env.NODE_ENV === "test") {
      try {
        await finalizeAfterRun();
      } catch (err) {
        if (!intentionalAbortRef.current && isMountedRef.current && !shouldSuppressErrors) {
          onError(err instanceof Error ? err.message : "Failed to refresh builder state after run");
        }
      }
    } else {
      void finalizeAfterRun().catch((err) => {
        if (!intentionalAbortRef.current && isMountedRef.current && !shouldSuppressErrors) {
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
    if (!intentionalAbortRef.current && !isAbortError && !shouldSuppressErrors) {
      onError(err instanceof Error ? err.message : "Failed to run coding agent");
    }
  } finally {
    abortReaderRef.current = null;
    activeRunIdRef.current = null;
    lastKnownRunIdRef.current = null;
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
