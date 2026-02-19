import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  modelsService,
  publishedAppsService,
  resolveAppsCodingAgentEngine,
} from "@/services";
import type {
  CodingAgentChatSession,
  CodingAgentExecutionEngine,
  CodingAgentStreamEvent,
  LogicalModel,
  PublishedAppRevision,
  RevisionConflictResponse,
} from "@/services";

import {
  TimelineItem,
  ToolRunStatus,
  TimelineTone,
  describeToolIntent,
  isAssistantTimelineItem,
  isToolTimelineItem,
  isUserTimelineItem,
  timelineId,
} from "./chat-model";

type CodingAgentModelUnavailableDetail = {
  code: "CODING_AGENT_MODEL_UNAVAILABLE";
  field: "model_id";
  message: string;
};

type CodingAgentEngineUnavailableDetail = {
  code: "CODING_AGENT_ENGINE_UNAVAILABLE" | "CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME";
  field: "engine";
  message: string;
};

const parseSse = (raw: string): CodingAgentStreamEvent | null => {
  const dataLines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("data:"));
  if (dataLines.length === 0) return null;
  const payload = dataLines.map((line) => line.slice(5).trimStart()).join("\n");
  if (!payload || payload === "[DONE]") return null;
  try {
    return JSON.parse(payload) as CodingAgentStreamEvent;
  } catch {
    return null;
  }
};

const parseRevisionConflict = (detail: unknown): RevisionConflictResponse | null => {
  let parsed: unknown = detail;
  if (typeof parsed === "string") {
    const text = parsed.trim();
    if (!text) return null;
    try {
      parsed = JSON.parse(text);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== "object") {
    return null;
  }
  const candidate = parsed as Partial<RevisionConflictResponse>;
  if (candidate.code !== "REVISION_CONFLICT") {
    return null;
  }
  if (!candidate.latest_revision_id || !candidate.latest_updated_at) {
    return null;
  }
  return {
    code: "REVISION_CONFLICT",
    latest_revision_id: String(candidate.latest_revision_id),
    latest_updated_at: String(candidate.latest_updated_at),
    message: String(candidate.message || "Draft revision is stale"),
  };
};

const parseModelUnavailableDetail = (detail: unknown): CodingAgentModelUnavailableDetail | null => {
  let parsed: unknown = detail;
  if (typeof parsed === "string") {
    const text = parsed.trim();
    if (!text) return null;
    try {
      parsed = JSON.parse(text);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== "object") {
    return null;
  }
  const candidate = parsed as Partial<CodingAgentModelUnavailableDetail>;
  if (candidate.code !== "CODING_AGENT_MODEL_UNAVAILABLE") {
    return null;
  }
  if (candidate.field !== "model_id") {
    return null;
  }
  return {
    code: "CODING_AGENT_MODEL_UNAVAILABLE",
    field: "model_id",
    message: String(candidate.message || "Selected model is unavailable. Pick another model and retry."),
  };
};

const parseEngineUnavailableDetail = (detail: unknown): CodingAgentEngineUnavailableDetail | null => {
  let parsed: unknown = detail;
  if (typeof parsed === "string") {
    const text = parsed.trim();
    if (!text) return null;
    try {
      parsed = JSON.parse(text);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== "object") {
    return null;
  }
  const candidate = parsed as Partial<CodingAgentEngineUnavailableDetail>;
  if (candidate.field !== "engine") {
    return null;
  }
  if (candidate.code !== "CODING_AGENT_ENGINE_UNAVAILABLE" && candidate.code !== "CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME") {
    return null;
  }
  return {
    code: candidate.code,
    field: "engine",
    message: String(candidate.message || "Selected engine is unavailable for this runtime."),
  };
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

  const abortReaderRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);

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

  const upsertToolTimeline = useCallback((toolCallId: string, title: string, status: ToolRunStatus) => {
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
        },
      ];
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

  const stopCurrentRun = useCallback(() => {
    if (abortReaderRef.current) {
      abortReaderRef.current.cancel();
      abortReaderRef.current = null;
    }
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

  useEffect(() => {
    void loadChatModels();
    void loadChatSessions();
  }, [loadChatModels, loadChatSessions]);

  const loadChatSession = useCallback(async (sessionId: string) => {
    if (isSending) {
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
      setActiveThinkingSummary("");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load coding-agent chat session");
    }
  }, [appId, isSending, onError, stopCurrentRun]);

  const sendBuilderChat = useCallback(async (rawInput: string) => {
    const input = rawInput.trim();
    if (!input) return;

    setIsSending(true);
    onError(null);
    setActiveThinkingSummary("Thinking...");
    pushTimeline({ kind: "user", title: "User request", description: input });

    try {
      const createRun = async (baseRevisionId?: string) =>
        publishedAppsService.createCodingAgentRun(appId, {
          input,
          base_revision_id: baseRevisionId,
          model_id: selectedRunModelId,
          engine: resolvedRunEngine,
          chat_session_id: activeChatSessionId || undefined,
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

      if (run.chat_session_id) {
        setActiveChatSessionId(run.chat_session_id);
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

      while (true) {
        const { done, value } = await reader.read();
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
            if (assistantText.trim()) {
              upsertAssistantTimeline(currentStreamId, assistantText.trim());
            }
            assistantText = "";
            segmentCounter++;
            currentStreamId = `${assistantStreamId}-seg${segmentCounter}`;
            upsertToolTimeline(toolCallId, describeToolIntent(toolName), "running");
          }

          if (parsed.event === "tool.completed") {
            const toolName = String(payload.tool || "tool");
            const toolCallId = String(payload.span_id || `${toolName}-${timelineId("call")}`);
            upsertToolTimeline(toolCallId, describeToolIntent(toolName), "completed");
          }

          if (parsed.event === "tool.failed") {
            const toolName = String(payload.tool || "tool");
            const toolCallId = String(payload.span_id || `${toolName}-${timelineId("call")}`);
            upsertToolTimeline(toolCallId, describeToolIntent(toolName), "failed");
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
            const failureMessage = String(
              parsed.diagnostics?.[0]?.message || payload.error || "Coding-agent run failed",
            );
            onError(failureMessage);
          }

          if (parsed.event !== "run.failed" && Array.isArray(parsed.diagnostics) && parsed.diagnostics.length > 0) {
            const diagnosticMessage = String(parsed.diagnostics[0]?.message || "").trim();
            if (diagnosticMessage) {
              onError(diagnosticMessage);
            }
          }

          splitIndex = buffer.indexOf("\n\n");
        }
      }

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

      await refreshStateSilently();
      if (activeTab === "preview") {
        await ensureDraftDevSession();
      }
      if (latestResultRevisionId) {
        onSetCurrentRevisionId(latestResultRevisionId);
      }
      await loadChatSessions();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to run coding agent");
    } finally {
      abortReaderRef.current = null;
      setActiveThinkingSummary("");
      setIsSending(false);
    }
  }, [
    activeChatSessionId,
    activeTab,
    appId,
    attachCheckpointToLastUser,
    currentRevisionId,
    ensureDraftDevSession,
    loadChatSessions,
    onError,
    onSetCurrentRevisionId,
    pushTimeline,
    refreshStateSilently,
    resolvedRunEngine,
    selectedRunModelId,
    upsertAssistantTimeline,
    upsertToolTimeline,
  ]);

  const startNewChat = useCallback(() => {
    if (isSending) stopCurrentRun();
    setTimeline([]);
    setActiveThinkingSummary("");
    setActiveChatSessionId(null);
  }, [isSending, stopCurrentRun]);

  const revertToCheckpoint = useCallback(async (userItemId: string, checkpointId: string) => {
    if (isSending) stopCurrentRun();
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
  }, [activeTab, appId, ensureDraftDevSession, isSending, onApplyRestoredRevision, onError, stopCurrentRun]);

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
    sendBuilderChat,
    stopCurrentRun,
    startNewChat,
    revertToCheckpoint,
    loadChatSession,
  };
}
