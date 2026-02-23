import type { MutableRefObject } from "react";

import { publishedAppsService } from "@/services";

import { describeToolIntent, extractPrimaryToolPath, timelineId } from "./chat-model";
import { parseRunActiveDetail, parseSse, resolvePositiveTimeoutMs, TERMINAL_RUN_EVENTS } from "./stream-parsers";

type TerminalStatus = "completed" | "failed" | "cancelled" | "paused";

type ConsumeRunStreamOptions = {
  appId: string;
  runId: string;
  fromSeq?: number;
  replay?: boolean;
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
  refreshQueue: (sessionId: string | null | undefined) => Promise<void>;
};

export async function consumeRunStream(options: ConsumeRunStreamOptions): Promise<void> {
  const {
    appId,
    runId,
    fromSeq = 1,
    replay = true,
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
    const useDefaultStreamParams = fromSeq <= 1 && replay;
    const response = useDefaultStreamParams
      ? await publishedAppsService.streamCodingAgentRun(appId, normalizedRunId)
      : await publishedAppsService.streamCodingAgentRun(appId, normalizedRunId, {
          fromSeq,
          replay,
        });
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
    let sawRunFailure = false;
    let sawTerminalEvent = false;
    let sawInactivityTimeout = false;
    let sawMaxDurationTimeout = false;
    let terminalStatus: TerminalStatus | null = null;

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
    const ASSISTANT_DELTA_FLUSH_MS = resolvePositiveTimeoutMs(
      process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_ASSISTANT_DELTA_FLUSH_MS,
      45,
    );
    const ASSISTANT_DELTA_FLUSH_CHARS = Math.max(
      1,
      Number.parseInt(
        String(process.env.NEXT_PUBLIC_APPS_CODING_AGENT_STREAM_ASSISTANT_DELTA_FLUSH_CHARS || "80"),
        10,
      ) || 80,
    );

    const runStartedAt = Date.now();
    let lastEventAt = Date.now();
    let lastAssistantFlushAt = Date.now();
    let pendingAssistantDelta = "";
    let pendingRead:
      | Promise<{ ok: true; result: ReadableStreamReadResult<Uint8Array> } | { ok: false; error: unknown }>
      | null = null;

    const flushAssistantDelta = (force = false) => {
      if (!pendingAssistantDelta) {
        return;
      }
      const now = Date.now();
      const elapsedSinceFlush = now - lastAssistantFlushAt;
      if (
        !force &&
        pendingAssistantDelta.length < ASSISTANT_DELTA_FLUSH_CHARS &&
        elapsedSinceFlush < ASSISTANT_DELTA_FLUSH_MS
      ) {
        return;
      }
      assistantText += pendingAssistantDelta;
      pendingAssistantDelta = "";
      lastAssistantFlushAt = now;
      if (assistantText.trim()) {
        setActiveThinkingSummary("");
        upsertAssistantTimeline(currentStreamId, assistantText);
      }
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
        if (typeof reader.cancel === "function") {
          void reader.cancel().catch(() => undefined);
        }
        break;
      }
      if (now - lastEventAt > STALL_TIMEOUT_MS) {
        sawInactivityTimeout = true;
        sawRunFailure = true;
        if (typeof reader.cancel === "function") {
          void reader.cancel().catch(() => undefined);
        }
        break;
      }

      const pollTimeoutMs = pendingAssistantDelta
        ? Math.max(10, Math.min(READ_POLL_TIMEOUT_MS, ASSISTANT_DELTA_FLUSH_MS))
        : READ_POLL_TIMEOUT_MS;
      const readResult = await readWithPollingTimeout(pollTimeoutMs);
      if (!readResult) {
        flushAssistantDelta(false);
        continue;
      }
      const { done, value } = readResult;
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      let splitIndex = buffer.indexOf("\n\n");
      while (splitIndex >= 0) {
        const raw = buffer.slice(0, splitIndex).trim();
        buffer = buffer.slice(splitIndex + 2);
        const parsed = parseSse(raw);
        if (!parsed) {
          splitIndex = buffer.indexOf("\n\n");
          continue;
        }

        const seq = Number(parsed.seq || 0);
        if (seq > 0) {
          const eventKey = `${normalizedRunId}:${seq}`;
          if (seenRunEventKeysRef.current.has(eventKey)) {
            splitIndex = buffer.indexOf("\n\n");
            continue;
          }
          seenRunEventKeysRef.current.add(eventKey);
        }

        lastEventAt = Date.now();
        const payload = (parsed.payload || {}) as Record<string, unknown>;

        if (parsed.event === "assistant.delta" && payload.content) {
          pendingAssistantDelta += String(payload.content);
          flushAssistantDelta(false);
          splitIndex = buffer.indexOf("\n\n");
          continue;
        }
        flushAssistantDelta(true);

        if (parsed.event === "plan.updated") {
          const summary = String(payload.summary || "").trim();
          if (summary && summary.toLowerCase() !== "coding-agent run started") {
            latestSummary = summary;
            setActiveThinkingSummary(summary);
          }
        }

        if (parsed.event === "tool.started") {
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
          const toolName = String(payload.tool || "tool");
          const toolCallId = String(payload.span_id || `${toolName}-${timelineId("call")}`);
          const toolPath = extractPrimaryToolPath(payload.output || payload);
          upsertToolTimeline(toolCallId, describeToolIntent(toolName), "completed", toolName, toolPath);
        }

        if (parsed.event === "tool.failed") {
          const toolName = String(payload.tool || "tool");
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

        splitIndex = buffer.indexOf("\n\n");
      }

      if (sawTerminalEvent) {
        break;
      }

      flushAssistantDelta(false);
    }
    flushAssistantDelta(true);

    if (sawMaxDurationTimeout && !intentionalAbortRef.current) {
      onError("Coding-agent run exceeded maximum duration. The run was stopped to recover.");
    } else if (sawInactivityTimeout && !intentionalAbortRef.current) {
      onError("Coding-agent stream stalled before completion. The run was stopped to recover.");
    } else if (!sawTerminalEvent && !intentionalAbortRef.current) {
      sawRunFailure = true;
      onError("Coding-agent stream ended before a terminal event.");
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
      await refreshQueue(activeChatSessionIdRef.current);
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
