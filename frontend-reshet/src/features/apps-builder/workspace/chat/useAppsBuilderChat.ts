import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  modelsService,
  publishedAppsService,
  resolveAppsCodingAgentEngine,
} from "@/services";
import type {
  CodingAgentCapabilities,
  CodingAgentChatSession,
  CodingAgentExecutionEngine,
  LogicalModel,
  PublishedAppRevision,
} from "@/services";

import {
  TimelineItem,
  ToolRunStatus,
  TimelineTone,
  describeToolIntent,
  extractPrimaryToolPath,
  timelineId,
} from "./chat-model";
import {
  TerminalRunStatus,
  parseEngineUnavailableDetail,
  parseModelUnavailableDetail,
  parseRevisionConflict,
  parseSse,
  parseTerminalRunStatus,
  resolvePositiveTimeoutMs,
} from "./stream-parsers";

export type QueuedPrompt = {
  id: string;
  text: string;
  createdAt: number;
};

export type UseAppsBuilderChatOptions = {
  appId: string;
  currentRevisionId: string | null;
  activeTab: "preview" | "config";
  ensureDraftDevSession: () => Promise<void>;
  refreshStateSilently: () => Promise<void>;
  onApplyRestoredRevision: (revision: PublishedAppRevision) => void;
  onSetCurrentRevisionId: (revisionId: string | null) => void;
  onError: (message: string | null) => void;
};

export type UseAppsBuilderChatResult = {
  isAgentPanelOpen: boolean;
  setIsAgentPanelOpen: (next: boolean) => void;
  isSending: boolean;
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
  resolvedRunEngine: CodingAgentExecutionEngine;
  queuedPrompts: QueuedPrompt[];
  removeQueuedPrompt: (promptId: string) => void;
  capabilities: CodingAgentCapabilities | null;
  sendBuilderChat: (rawInput: string) => Promise<void>;
  stopCurrentRun: () => void;
  startNewChat: () => void;
  revertToCheckpoint: (userItemId: string, checkpointId: string) => Promise<void>;
  loadChatSession: (sessionId: string) => Promise<void>;
};

export function useAppsBuilderChat({
  appId,
  currentRevisionId,
  activeTab,
  ensureDraftDevSession,
  refreshStateSilently,
  onApplyRestoredRevision,
  onSetCurrentRevisionId,
  onError,
}: UseAppsBuilderChatOptions): UseAppsBuilderChatResult {
  const [isAgentPanelOpen, setIsAgentPanelOpenState] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [isUndoing, setIsUndoing] = useState(false);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [activeThinkingSummary, setActiveThinkingSummary] = useState("");
  const [chatSessions, setChatSessions] = useState<CodingAgentChatSession[]>([]);
  const [activeChatSessionId, setActiveChatSessionId] = useState<string | null>(null);
  const [chatModels, setChatModels] = useState<LogicalModel[]>([]);
  const [selectedRunModelId, setSelectedRunModelId] = useState<string | null>(null);
  const [isModelSelectorOpen, setIsModelSelectorOpen] = useState(false);
  const [queuedPrompts, setQueuedPrompts] = useState<QueuedPrompt[]>([]);
  const [capabilities, setCapabilities] = useState<CodingAgentCapabilities | null>(null);

  const abortReaderRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
  const activeRunIdRef = useRef<string | null>(null);
  const lastKnownRunIdRef = useRef<string | null>(null);
  const cancelInFlightRunIdRef = useRef<string | null>(null);
  const pendingCancelRef = useRef(false);
  const intentionalAbortRef = useRef(false);
  const isSendingRef = useRef(false);
  const isMountedRef = useRef(true);
  const executePromptRef = useRef<(promptText: string) => Promise<void>>(async () => undefined);
  const queuedPromptsRef = useRef<QueuedPrompt[]>([]);

  useEffect(() => {
    isSendingRef.current = isSending;
  }, [isSending]);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      intentionalAbortRef.current = true;
      const reader = abortReaderRef.current;
      abortReaderRef.current = null;
      if (reader && typeof reader.cancel === "function") {
        void reader.cancel().catch(() => undefined);
      }
    };
  }, []);

  const resolvedRunEngine = useMemo(() => resolveAppsCodingAgentEngine(), []);
  const selectedRunModelLabel = useMemo(() => {
    if (!selectedRunModelId) return "Auto";
    const match = chatModels.find((model) => model.id === selectedRunModelId);
    return match?.name || "Auto";
  }, [chatModels, selectedRunModelId]);

  const setIsAgentPanelOpen = useCallback((next: boolean) => {
    setIsAgentPanelOpenState(next);
  }, []);

  const pushTimeline = useCallback((item: Omit<TimelineItem, "id" | "kind"> & { kind?: TimelineItem["kind"] }) => {
    setTimeline((prev) => [...prev, { ...item, kind: item.kind || "assistant", id: timelineId("timeline") }]);
  }, []);

  const upsertAssistantTimeline = useCallback((assistantStreamId: string, description: string) => {
    setTimeline((prev) => {
      const existingIndex = prev.findIndex(
        (item) => item.kind === "assistant" && item.assistantStreamId === assistantStreamId,
      );
      if (existingIndex >= 0) {
        const next = [...prev];
        next[existingIndex] = {
          ...next[existingIndex],
          description,
          tone: "default",
        };
        return next;
      }
      return [
        ...prev,
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
  }, []);

  const upsertToolTimeline = useCallback(
    (
      toolCallId: string,
      title: string,
      status: ToolRunStatus,
      toolName: string,
      toolPath?: string | null,
    ) => {
      setTimeline((prev) => {
        const existingIndex = prev.findIndex(
          (item) => item.kind === "tool" && item.toolCallId === toolCallId,
        );
        const nextTone: TimelineTone | undefined = status === "failed" ? "error" : status === "completed" ? "success" : undefined;
        if (existingIndex >= 0) {
          const next = [...prev];
          next[existingIndex] = {
            ...next[existingIndex],
            title,
            toolStatus: status,
            tone: nextTone,
            toolName,
            toolPath: toolPath || next[existingIndex].toolPath,
          };
          return next;
        }
        return [
          ...prev,
          {
            id: timelineId("tool"),
            kind: "tool",
            toolCallId,
            toolStatus: status,
            title,
            tone: nextTone,
            toolName,
            toolPath: toolPath || undefined,
          },
        ];
      });
    },
    [],
  );

  const finalizeRunningTools = useCallback((status: Extract<ToolRunStatus, "completed" | "failed">) => {
    setTimeline((prev) => {
      let changed = false;
      const next = prev.map((item) => {
        if (item.kind !== "tool" || item.toolStatus !== "running") return item;
        changed = true;
        return {
          ...item,
          toolStatus: status,
          tone: status === "failed" ? "error" : "success",
        };
      });
      return changed ? next : prev;
    });
  }, []);

  const attachCheckpointToLastUser = useCallback((checkpointId: string) => {
    setTimeline((prev) => {
      for (let i = prev.length - 1; i >= 0; i--) {
        if (prev[i].kind === "user" && !prev[i].checkpointId) {
          const next = [...prev];
          next[i] = { ...next[i], checkpointId };
          return next;
        }
      }
      return prev;
    });
  }, []);

  const removeQueuedPrompt = useCallback((promptId: string) => {
    queuedPromptsRef.current = queuedPromptsRef.current.filter((item) => item.id !== promptId);
    setQueuedPrompts(queuedPromptsRef.current);
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

  const loadChatSessions = useCallback(async () => {
    try {
      const sessions = await publishedAppsService.listCodingAgentChatSessions(appId, 50);
      setChatSessions(sessions);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load coding-agent chat sessions");
    }
  }, [appId, onError]);

  const loadCapabilities = useCallback(async () => {
    try {
      const response = await publishedAppsService.getCodingAgentCapabilities(appId);
      setCapabilities(response);
    } catch {
      setCapabilities(null);
    }
  }, [appId]);

  const getPersistedTerminalRun = useCallback(
    async (runId: string): Promise<{ status: TerminalRunStatus; error: string | null } | null> => {
      try {
        const run = await publishedAppsService.getCodingAgentRun(appId, runId);
        const terminalStatus = parseTerminalRunStatus(run.status);
        if (!terminalStatus) {
          return null;
        }
        return {
          status: terminalStatus,
          error: String(run.error || "").trim() || null,
        };
      } catch {
        return null;
      }
    },
    [appId],
  );

  useEffect(() => {
    void loadChatModels();
    void loadChatSessions();
    void loadCapabilities();
  }, [loadCapabilities, loadChatModels, loadChatSessions]);

  const stopCurrentRun = useCallback(() => {
    intentionalAbortRef.current = true;
    pendingCancelRef.current = true;
    if (isSendingRef.current) {
      setActiveThinkingSummary("");
      setIsSending(false);
      isSendingRef.current = false;
    }
    const runIdToCancel = activeRunIdRef.current || lastKnownRunIdRef.current;
    if (runIdToCancel && cancelInFlightRunIdRef.current !== runIdToCancel) {
      cancelInFlightRunIdRef.current = runIdToCancel;
      void publishedAppsService.cancelCodingAgentRun(appId, runIdToCancel).catch((err) => {
        const message = err instanceof Error ? err.message : "Failed to cancel current run";
        onError(message);
      }).finally(() => {
        if (cancelInFlightRunIdRef.current === runIdToCancel) {
          cancelInFlightRunIdRef.current = null;
        }
      });
    }
    const reader = abortReaderRef.current;
    if (reader) {
      abortReaderRef.current = null;
      if (typeof reader.cancel === "function") {
        void reader.cancel().catch(() => undefined);
      }
    }
  }, [appId, onError]);

  const loadChatSession = useCallback(async (sessionId: string) => {
    if (isSendingRef.current) {
      stopCurrentRun();
    }
    onError(null);
    try {
      const detail = await publishedAppsService.getCodingAgentChatSession(appId, sessionId, 300);
      const restoredTimeline: TimelineItem[] = detail.messages
        .filter((item) => (item.role === "user" || item.role === "assistant") && String(item.content || "").trim().length > 0)
        .map((item) => ({
          id: `history-${item.id}`,
          kind: item.role,
          title: item.role === "user" ? "User request" : "Assistant",
          description: item.content,
          tone: "default",
        }));
      setTimeline(restoredTimeline);
      setActiveChatSessionId(detail.session.id);
      queuedPromptsRef.current = [];
      setQueuedPrompts([]);
      setActiveThinkingSummary("");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load coding-agent chat session");
    }
  }, [appId, onError, stopCurrentRun]);

  const executePrompt = useCallback(async (promptText: string) => {
    const input = promptText.trim();
    if (!input) return;

    setIsSending(true);
    isSendingRef.current = true;
    onError(null);
    setActiveThinkingSummary("Thinking...");
    pushTimeline({ kind: "user", title: "User request", description: input });

    intentionalAbortRef.current = false;
    activeRunIdRef.current = null;

    let shouldSuppressErrors = false;

    try {
      const clientMessageId = `msg-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      const createRun = async (baseRevisionId?: string) =>
        publishedAppsService.createCodingAgentRun(appId, {
          input,
          base_revision_id: baseRevisionId,
          model_id: selectedRunModelId,
          engine: resolvedRunEngine,
          chat_session_id: activeChatSessionId || undefined,
          client_message_id: clientMessageId,
        });

      let run;
      try {
        run = await createRun(currentRevisionId || undefined);
      } catch (err: any) {
        const engineUnavailable = parseEngineUnavailableDetail(err?.message);
        if (engineUnavailable) {
          throw new Error(engineUnavailable.message);
        }
        const modelUnavailable = parseModelUnavailableDetail(err?.message);
        if (modelUnavailable) {
          throw new Error(modelUnavailable.message);
        }
        const conflict = parseRevisionConflict(err?.message);
        if (!conflict) {
          throw err;
        }
        const latestRevisionId = String(conflict.latest_revision_id || "").trim();
        setActiveThinkingSummary("Draft changed. Refreshing and retrying...");
        await refreshStateSilently();
        run = await createRun(latestRevisionId || undefined);
        if (latestRevisionId) {
          onSetCurrentRevisionId(latestRevisionId);
        }
      }

      activeRunIdRef.current = run.run_id;
      lastKnownRunIdRef.current = run.run_id;
      if (run.chat_session_id) {
        setActiveChatSessionId(run.chat_session_id);
      }
      if (pendingCancelRef.current || intentionalAbortRef.current) {
        pendingCancelRef.current = false;
        const runIdToCancel = activeRunIdRef.current || lastKnownRunIdRef.current;
        if (runIdToCancel && cancelInFlightRunIdRef.current !== runIdToCancel) {
          cancelInFlightRunIdRef.current = runIdToCancel;
          void publishedAppsService.cancelCodingAgentRun(appId, runIdToCancel).catch((err) => {
            const message = err instanceof Error ? err.message : "Failed to cancel current run";
            onError(message);
          }).finally(() => {
            if (cancelInFlightRunIdRef.current === runIdToCancel) {
              cancelInFlightRunIdRef.current = null;
            }
          });
        }
        shouldSuppressErrors = true;
        return;
      }

      const assistantStreamId = `assistant-${run.run_id}`;
      const response = await publishedAppsService.streamCodingAgentRun(appId, run.run_id);
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
          // Keep fallback message.
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
      let currentStreamId = assistantStreamId;
      let segmentCounter = 0;
      let latestSummary = "";
      let latestResultRevisionId = "";
      let sawRunFailure = false;
      let sawTerminalEvent = false;
      let sawInactivityTimeout = false;
      let sawMaxDurationTimeout = false;
      let resolvedMissingTerminalFromBackend = false;
      let reconciledTerminalStatus: TerminalRunStatus | null = null;
      let reconciledTerminalError: string | null = null;
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

      const readWithPollingTimeout = async (): Promise<ReadableStreamReadResult<Uint8Array> | null> => {
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
            setTimeout(() => resolve(timeoutToken), READ_POLL_TIMEOUT_MS);
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
        const readResult = await readWithPollingTimeout();
        if (!readResult) {
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
          lastEventAt = Date.now();

          const payload = (parsed.payload || {}) as Record<string, unknown>;

          if (parsed.event === "assistant.delta" && payload.content) {
            assistantText += String(payload.content);
            if (assistantText.trim()) {
              setActiveThinkingSummary("");
              upsertAssistantTimeline(currentStreamId, assistantText);
            }
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
            const toolCallId = String(payload.span_id || `${toolName}-${timelineId("call")}`);
            const toolPath = extractPrimaryToolPath(payload.input || payload);
            if (assistantText.trim()) {
              upsertAssistantTimeline(currentStreamId, assistantText.trim());
            }
            assistantText = "";
            segmentCounter++;
            currentStreamId = `${assistantStreamId}-seg${segmentCounter}`;
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
            finalizeRunningTools("failed");
            const failureMessage = String(
              parsed.diagnostics?.[0]?.message || payload.error || "Coding-agent run failed",
            );
            if (!intentionalAbortRef.current) {
              onError(failureMessage);
            } else {
              shouldSuppressErrors = true;
            }
          }

          if (parsed.event !== "run.failed" && Array.isArray(parsed.diagnostics) && parsed.diagnostics.length > 0) {
            const diagnosticMessage = String(parsed.diagnostics[0]?.message || "").trim();
            if (diagnosticMessage && !intentionalAbortRef.current) {
              onError(diagnosticMessage);
            }
          }

          if (parsed.event === "run.completed") {
            sawTerminalEvent = true;
            finalizeRunningTools("completed");
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
      }

      if (!sawTerminalEvent && !intentionalAbortRef.current) {
        const runIdToReconcile = activeRunIdRef.current || lastKnownRunIdRef.current || run.run_id;
        if (runIdToReconcile) {
          const persistedTerminalRun = await getPersistedTerminalRun(runIdToReconcile);
          if (persistedTerminalRun) {
            resolvedMissingTerminalFromBackend = true;
            reconciledTerminalStatus = persistedTerminalRun.status;
            reconciledTerminalError = persistedTerminalRun.error;
            sawTerminalEvent = true;
            sawRunFailure = persistedTerminalRun.status !== "completed" && persistedTerminalRun.status !== "paused";
          }
        }
      }

      if (sawMaxDurationTimeout && !intentionalAbortRef.current && !resolvedMissingTerminalFromBackend) {
        onError("Coding-agent run exceeded maximum duration. The run was stopped to recover.");
      } else if (sawInactivityTimeout && !intentionalAbortRef.current && !resolvedMissingTerminalFromBackend) {
        onError("Coding-agent stream stalled before completion. The run was stopped to recover.");
      } else if (!sawTerminalEvent && !intentionalAbortRef.current) {
        sawRunFailure = true;
        onError("Coding-agent stream ended before a terminal event.");
      } else if (
        !intentionalAbortRef.current &&
        reconciledTerminalStatus &&
        reconciledTerminalStatus !== "completed" &&
        reconciledTerminalStatus !== "paused"
      ) {
        onError(
          reconciledTerminalError || (reconciledTerminalStatus === "cancelled" ? "Run cancelled." : "Coding-agent run failed"),
        );
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
          await ensureDraftDevSession();
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
          if (!intentionalAbortRef.current && isMountedRef.current) {
            onError(err instanceof Error ? err.message : "Failed to refresh builder state after run");
          }
        }
      } else {
        void finalizeAfterRun().catch((err) => {
          if (!intentionalAbortRef.current && isMountedRef.current) {
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
      if (!intentionalAbortRef.current && !isAbortError) {
        onError(err instanceof Error ? err.message : "Failed to run coding agent");
      } else {
        shouldSuppressErrors = true;
      }
    } finally {
      abortReaderRef.current = null;
      activeRunIdRef.current = null;
      pendingCancelRef.current = false;
      cancelInFlightRunIdRef.current = null;
      lastKnownRunIdRef.current = null;
      intentionalAbortRef.current = false;
      if (!isMountedRef.current) {
        return;
      }
      setActiveThinkingSummary("");
      setIsSending(false);
      isSendingRef.current = false;

      let nextQueuedPrompt: QueuedPrompt | null = null;
      if (queuedPromptsRef.current.length > 0) {
        const [nextPrompt, ...remaining] = queuedPromptsRef.current;
        nextQueuedPrompt = nextPrompt;
        queuedPromptsRef.current = remaining;
        setQueuedPrompts(remaining);
      }
      if (nextQueuedPrompt) {
        void executePromptRef.current(nextQueuedPrompt.text);
      }
    }
  }, [
    activeChatSessionId,
    activeTab,
    appId,
    attachCheckpointToLastUser,
    currentRevisionId,
    ensureDraftDevSession,
    getPersistedTerminalRun,
    loadChatSessions,
    onError,
    onSetCurrentRevisionId,
    pushTimeline,
    refreshStateSilently,
    resolvedRunEngine,
    selectedRunModelId,
    upsertAssistantTimeline,
    upsertToolTimeline,
    finalizeRunningTools,
  ]);

  useEffect(() => {
    executePromptRef.current = executePrompt;
  }, [executePrompt]);

  const sendBuilderChat = useCallback(async (rawInput: string) => {
    const input = rawInput.trim();
    if (!input) return;

    if (isSendingRef.current || pendingCancelRef.current) {
      const nextPrompt = {
        id: timelineId("queued"),
        text: input,
        createdAt: Date.now(),
      };
      queuedPromptsRef.current = [...queuedPromptsRef.current, nextPrompt];
      setQueuedPrompts(queuedPromptsRef.current);
      return;
    }

    await executePrompt(input);
  }, [executePrompt]);

  const startNewChat = useCallback(() => {
    if (isSendingRef.current) stopCurrentRun();
    setTimeline([]);
    queuedPromptsRef.current = [];
    setQueuedPrompts([]);
    setActiveThinkingSummary("");
    setActiveChatSessionId(null);
  }, [stopCurrentRun]);

  const revertToCheckpoint = useCallback(async (userItemId: string, checkpointId: string) => {
    if (isSendingRef.current) stopCurrentRun();
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
  }, [activeTab, appId, ensureDraftDevSession, onApplyRestoredRevision, onError, stopCurrentRun]);

  return {
    isAgentPanelOpen,
    setIsAgentPanelOpen,
    isSending,
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
    resolvedRunEngine,
    queuedPrompts,
    removeQueuedPrompt,
    capabilities,
    sendBuilderChat,
    stopCurrentRun,
    startNewChat,
    revertToCheckpoint,
    loadChatSession,
  };
}
