import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  artifactsService,
  type ArtifactCodingChatSession,
  type ArtifactCodingChatSessionDetail,
  type ArtifactCodingModelOption,
  type ArtifactCodingScopeMode,
} from "@/services/artifacts";

import { TimelineItem, timelineId } from "./chat-model";
import {
  TERMINAL_RUN_EVENTS,
  parsePendingQuestionPayload,
  parseSse,
  parseTerminalRunStatus,
  type ArtifactCodingPendingQuestion,
} from "./stream-parsers";

type UseArtifactCodingChatOptions = {
  tenantSlug?: string;
  tenantId?: string | null;
  artifactId?: string | null;
  draftKey: string;
  isCreateMode: boolean;
  scopeMode?: ArtifactCodingScopeMode;
  initialChatSessionId?: string | null;
  getDraftSnapshot: () => Record<string, unknown>;
  onApplyDraftSnapshot: (snapshot: Record<string, unknown>) => void;
  onResetDraftSnapshot?: () => void;
  onActiveChatSessionChange?: (sessionId: string | null) => void;
  onResolvedArtifactId?: (artifactId: string) => void;
  onError: (message: string | null) => void;
};

type HistoryPage = { hasMore: boolean; nextBeforeMessageId: string | null };
const DRAFT_SESSION_KEY = "__draft__";

function createClientMessageId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function buildTimelineFromDetail(detail: ArtifactCodingChatSessionDetail): TimelineItem[] {
  const eventsByRunId = new Map<string, typeof detail.run_events>();
  for (const event of detail.run_events || []) {
    const list = eventsByRunId.get(event.run_id) || [];
    list.push(event);
    eventsByRunId.set(event.run_id, list);
  }
  const timeline: TimelineItem[] = [];
  for (const message of detail.messages || []) {
    if (message.role === "user") {
      timeline.push({
        id: message.id,
        kind: "user",
        title: "You",
        description: message.content,
        userDeliveryStatus: "sent",
        runId: message.run_id,
      });
      continue;
    }
    if (message.role === "orchestrator") {
      timeline.push({
        id: message.id,
        kind: "orchestrator",
        title: "Orchestrator",
        description: message.content,
        runId: message.run_id,
      });
      continue;
    }
    const runEvents = eventsByRunId.get(message.run_id) || [];
    const latestToolEvents = new Map<string, TimelineItem>();
    for (const event of runEvents) {
      if (!event.event.startsWith("tool.")) continue;
      const output = event.payload || {};
      const toolOutput = output.output && typeof output.output === "object" ? output.output as Record<string, unknown> : {};
      const toolCallId = String(output.span_id || timelineId("tool-call"));
      const toolName = String(output.tool || output.display_name || "tool");
      latestToolEvents.set(toolCallId, {
        id: `tool-history-${toolCallId}`,
        kind: "tool",
        title: String(toolOutput.summary || output.summary || toolName),
        toolCallId,
        toolStatus: event.event === "tool.failed" ? "failed" : event.event === "tool.started" ? "running" : "completed",
        toolName,
        toolPath: typeof toolOutput.path === "string" ? toolOutput.path : undefined,
        toolDetail: typeof toolOutput.summary === "string" ? toolOutput.summary : undefined,
        runId: message.run_id,
      });
    }
    if (latestToolEvents.size > 0) {
      timeline.push(...latestToolEvents.values());
    }
    timeline.push({
      id: message.id,
      kind: "assistant",
      title: "Assistant",
      description: message.content,
      runId: message.run_id,
    });
  }
  return timeline;
}

export function useArtifactCodingChat({
  tenantSlug,
  tenantId,
  artifactId,
  draftKey,
  isCreateMode,
  scopeMode = "locked",
  initialChatSessionId = null,
  getDraftSnapshot,
  onApplyDraftSnapshot,
  onResetDraftSnapshot,
  onActiveChatSessionChange,
  onResolvedArtifactId,
  onError,
}: UseArtifactCodingChatOptions) {
  const [isAgentPanelOpen, setIsAgentPanelOpen] = useState(false);
  const [chatSessions, setChatSessions] = useState<ArtifactCodingChatSession[]>([]);
  const [activeChatSessionId, setActiveChatSessionId] = useState<string | null>(null);
  const [timelinesBySession, setTimelinesBySession] = useState<Record<string, TimelineItem[]>>({});
  const [isStopping, setIsStopping] = useState(false);
  const [isLoadingOlderHistory, setIsLoadingOlderHistory] = useState(false);
  const [historyPagesBySession, setHistoryPagesBySession] = useState<Record<string, HistoryPage>>({});
  const [chatModels, setChatModels] = useState<ArtifactCodingModelOption[]>([]);
  const [selectedRunModelId, setSelectedRunModelId] = useState<string | null>(null);
  const [isModelSelectorOpen, setIsModelSelectorOpen] = useState(false);
  const [revertingRunId, setRevertingRunId] = useState<string | null>(null);
  const [activeThinkingBySession, setActiveThinkingBySession] = useState<Record<string, string>>({});
  const [pendingQuestionsBySession, setPendingQuestionsBySession] = useState<Record<string, ArtifactCodingPendingQuestion | null>>({});
  const [isAnsweringQuestion, setIsAnsweringQuestion] = useState(false);
  const [activeRunIdsBySession, setActiveRunIdsBySession] = useState<Record<string, string | null>>({});
  const abortReaderMapRef = useRef<Map<string, ReadableStreamDefaultReader<Uint8Array>>>(new Map());
  const activeSessionRef = useRef<string | null>(null);
  const previousScopeRef = useRef<{ artifactId: string | null | undefined; draftKey: string }>({ artifactId, draftKey });
  const activeSessionKey = activeChatSessionId || DRAFT_SESSION_KEY;
  const timeline = timelinesBySession[activeSessionKey] || [];
  const activeThinkingSummary = activeThinkingBySession[activeSessionKey] || "";
  const pendingQuestion = pendingQuestionsBySession[activeSessionKey] || null;
  const activeRunId = activeRunIdsBySession[activeSessionKey] || null;
  const isSending = Boolean(activeRunId);
  const hasOlderHistory = Boolean(historyPagesBySession[activeSessionKey]?.hasMore);
  const runningSessionIds = useMemo(
    () => Object.entries(activeRunIdsBySession).filter(([, runId]) => Boolean(runId)).map(([sessionId]) => sessionId),
    [activeRunIdsBySession],
  );

  const setTimelineForSession = useCallback((sessionKey: string, nextTimeline: TimelineItem[]) => {
    setTimelinesBySession((current) => ({ ...current, [sessionKey]: nextTimeline }));
  }, []);

  const updateTimelineForSession = useCallback((sessionKey: string, updater: (current: TimelineItem[]) => TimelineItem[]) => {
    setTimelinesBySession((current) => ({ ...current, [sessionKey]: updater(current[sessionKey] || []) }));
  }, []);

  const refreshSessions = useCallback(async () => {
    if (scopeMode === "locked" && !artifactId && !draftKey) return;
    const sessions = await artifactsService.listCodingAgentChatSessions(
      {
        artifactId: artifactId || undefined,
        draftKey: scopeMode === "locked" ? draftKey || undefined : undefined,
        scopeMode: scopeMode === "standalone" ? "standalone" : undefined,
        limit: 25,
      },
      tenantSlug,
    );
    setChatSessions(sessions);
  }, [artifactId, draftKey, scopeMode, tenantSlug]);

  const applySessionDetail = useCallback((detail: ArtifactCodingChatSessionDetail, beforeMessageId?: string | null) => {
    onApplyDraftSnapshot(detail.draft_snapshot || {});
    if (detail.session.artifact_id) {
      onResolvedArtifactId?.(detail.session.artifact_id);
    }
    const nextTimeline = buildTimelineFromDetail(detail);
    if (beforeMessageId) {
      updateTimelineForSession(detail.session.id, (current) => [...nextTimeline, ...current]);
    } else {
      setTimelineForSession(detail.session.id, nextTimeline);
    }
    setHistoryPagesBySession((current) => ({
      ...current,
      [detail.session.id]: {
        hasMore: Boolean(detail.paging?.has_more),
        nextBeforeMessageId: String(detail.paging?.next_before_message_id || "").trim() || null,
      },
    }));
    setActiveChatSessionId(detail.session.id);
    activeSessionRef.current = detail.session.id;
    setActiveRunIdsBySession((current) => ({
      ...current,
      [detail.session.id]: detail.session.active_run_id || current[detail.session.id] || null,
    }));
  }, [onApplyDraftSnapshot, onResolvedArtifactId, setTimelineForSession, updateTimelineForSession]);

  const loadSessionDetail = useCallback(async (sessionId: string, beforeMessageId?: string | null) => {
    const detail = await artifactsService.getCodingAgentChatSession(sessionId, {
      limit: 12,
      before_message_id: beforeMessageId,
      tenantSlug,
    });
    applySessionDetail(detail, beforeMessageId);
  }, [applySessionDetail, tenantSlug]);

  const stopCurrentRun = useCallback(async () => {
    if (!activeRunId) return;
    setIsStopping(true);
    try {
      await artifactsService.cancelCodingAgentRun(activeRunId, tenantSlug);
      const reader = abortReaderMapRef.current.get(activeSessionKey) || null;
      abortReaderMapRef.current.delete(activeSessionKey);
      if (reader) {
        await reader.cancel().catch(() => undefined);
      }
      setActiveRunIdsBySession((current) => ({ ...current, [activeSessionKey]: null }));
    } finally {
      setIsStopping(false);
    }
  }, [activeRunId, activeSessionKey, tenantSlug]);

  const consumeRunStream = useCallback(async (runId: string, sessionId: string) => {
    const sessionKey = sessionId || DRAFT_SESSION_KEY;
    const response = await artifactsService.streamCodingAgentRun(runId, tenantId);
    if (!response.ok || !response.body) {
      throw new Error("Failed to open artifact coding stream");
    }
    const reader = response.body.getReader();
    abortReaderMapRef.current.set(sessionKey, reader);
    const decoder = new TextDecoder();
    let buffer = "";
    let assistantText = "";
    const currentAssistantStreamId = `assistant-${runId}`;
    setActiveRunIdsBySession((current) => ({ ...current, [sessionKey]: runId }));
    setIsStopping(false);
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
        const event = parseSse(frame);
        if (!event) continue;
        if (event.event === "assistant.delta") {
          assistantText += String(event.payload?.content || "");
          updateTimelineForSession(sessionKey, (current) => {
            const existingIndex = current.findIndex((item) => item.kind === "assistant" && item.assistantStreamId === currentAssistantStreamId);
            if (existingIndex >= 0) {
              const next = [...current];
              next[existingIndex] = { ...next[existingIndex], description: assistantText };
              return next;
            }
            return [...current, { id: timelineId("assistant"), kind: "assistant", title: "Assistant", description: assistantText, assistantStreamId: currentAssistantStreamId, runId }];
          });
          continue;
        }
        if (event.event === "tool.started" || event.event === "tool.completed") {
          const payload = (event.payload || {}) as Record<string, unknown>;
          const output = payload.output && typeof payload.output === "object" ? payload.output as Record<string, unknown> : {};
          const toolCallId = String(payload.span_id || timelineId("tool"));
          const toolName = String(payload.tool || "tool");
          updateTimelineForSession(sessionKey, (current) => {
            const existingIndex = current.findIndex((item) => item.kind === "tool" && item.toolCallId === toolCallId);
            const nextItem: TimelineItem = {
              id: existingIndex >= 0 ? current[existingIndex].id : timelineId("tool"),
              kind: "tool",
              title: String(output.summary || payload.summary || toolName),
              toolCallId,
              toolStatus: event.event === "tool.started" ? "running" : "completed",
              toolName,
              toolPath: typeof output.path === "string" ? output.path : undefined,
              toolDetail: typeof output.summary === "string" ? output.summary : undefined,
              runId,
            };
            if (existingIndex >= 0) {
              const next = [...current];
              next[existingIndex] = nextItem;
              return next;
            }
            return [...current, nextItem];
          });
          if (
            event.event === "tool.completed"
            && output.draft_snapshot
            && typeof output.draft_snapshot === "object"
            && activeSessionRef.current === sessionId
          ) {
            onApplyDraftSnapshot(output.draft_snapshot as Record<string, unknown>);
          }
          continue;
        }
        if (event.event === "reasoning.update") {
          const summary = String(event.payload?.summary || event.payload?.message || "").trim();
          if (summary) {
            setActiveThinkingBySession((current) => ({ ...current, [sessionKey]: summary }));
          }
          continue;
        }
        const maybeQuestion = parsePendingQuestionPayload(event.payload);
        if (maybeQuestion) {
          setPendingQuestionsBySession((current) => ({ ...current, [sessionKey]: maybeQuestion }));
        }
        if (TERMINAL_RUN_EVENTS.has(event.event)) {
          setActiveRunIdsBySession((current) => ({ ...current, [sessionKey]: null }));
          setActiveThinkingBySession((current) => ({ ...current, [sessionKey]: "" }));
          const terminal = parseTerminalRunStatus(event.event.replace("run.", ""));
          if (terminal !== "paused") {
            setPendingQuestionsBySession((current) => ({ ...current, [sessionKey]: null }));
            await refreshSessions();
            if (activeSessionRef.current === sessionId) {
              await loadSessionDetail(sessionId);
            }
          }
        }
      }
    }
    abortReaderMapRef.current.delete(sessionKey);
    setActiveRunIdsBySession((current) => ({ ...current, [sessionKey]: null }));
    setActiveThinkingBySession((current) => ({ ...current, [sessionKey]: "" }));
    await refreshSessions();
    if (activeSessionRef.current === sessionId) {
      await loadSessionDetail(sessionId);
    }
  }, [loadSessionDetail, onApplyDraftSnapshot, refreshSessions, tenantId, updateTimelineForSession]);

  const sendMessage = useCallback(async (text: string) => {
    const prompt = String(text || "").trim();
    if (!prompt) return;
    const clientMessageId = createClientMessageId();
    const targetSessionKey = activeChatSessionId || DRAFT_SESSION_KEY;
    updateTimelineForSession(targetSessionKey, (current) => [
      ...current,
      { id: clientMessageId, kind: "user", title: "You", description: prompt, userDeliveryStatus: "pending" },
    ]);
    const response = await artifactsService.submitCodingAgentPrompt(
      {
        input: prompt,
        chat_session_id: activeChatSessionId || undefined,
        artifact_id: artifactId || undefined,
        draft_key: scopeMode === "locked" && (isCreateMode || !artifactId) ? draftKey : undefined,
        scope_mode: scopeMode,
        model_id: selectedRunModelId,
        client_message_id: clientMessageId,
        draft_snapshot: getDraftSnapshot(),
      },
      tenantSlug,
    );
    setActiveChatSessionId(response.chat_session_id);
    activeSessionRef.current = response.chat_session_id;
    setTimelinesBySession((current) => {
      const sourceTimeline = current[targetSessionKey] || [];
      const nextTimeline: TimelineItem[] = sourceTimeline.map((item) =>
        item.id === clientMessageId ? { ...item, userDeliveryStatus: "sent" as const, runId: response.run.run_id } : item,
      );
      const next = { ...current, [response.chat_session_id]: nextTimeline };
      if (targetSessionKey === DRAFT_SESSION_KEY && response.chat_session_id !== DRAFT_SESSION_KEY) {
        delete next[DRAFT_SESSION_KEY];
      }
      return next;
    });
    await refreshSessions();
    await consumeRunStream(response.run.run_id, response.chat_session_id);
  }, [activeChatSessionId, artifactId, consumeRunStream, draftKey, getDraftSnapshot, isCreateMode, refreshSessions, scopeMode, selectedRunModelId, tenantSlug, updateTimelineForSession]);

  const loadOlderHistory = useCallback(async () => {
    const historyPage = historyPagesBySession[activeSessionKey] || { hasMore: false, nextBeforeMessageId: null };
    if (!activeChatSessionId || !historyPage.nextBeforeMessageId) return;
    setIsLoadingOlderHistory(true);
    try {
      await loadSessionDetail(activeChatSessionId, historyPage.nextBeforeMessageId);
    } finally {
      setIsLoadingOlderHistory(false);
    }
  }, [activeChatSessionId, activeSessionKey, historyPagesBySession, loadSessionDetail]);

  const answerPendingQuestion = useCallback(async (answers: string[][]) => {
    if (!pendingQuestion || !activeRunId) return;
    setIsAnsweringQuestion(true);
    try {
      await artifactsService.answerCodingAgentRunQuestion(
        activeRunId,
        { question_id: pendingQuestion.requestId, answers },
        tenantSlug,
      );
      setPendingQuestionsBySession((current) => ({ ...current, [activeSessionKey]: null }));
      if (activeSessionRef.current) {
        await consumeRunStream(activeRunId, activeSessionRef.current);
      }
    } finally {
      setIsAnsweringQuestion(false);
    }
  }, [activeRunId, activeSessionKey, consumeRunStream, pendingQuestion, tenantSlug]);

  const revertToRun = useCallback(async (runId: string) => {
    if (!activeChatSessionId) return;
    setRevertingRunId(runId);
    try {
      const detail = await artifactsService.revertCodingAgentSession(
        activeChatSessionId,
        { run_id: runId },
        tenantSlug,
      );
      applySessionDetail(detail);
      await refreshSessions();
    } finally {
      setRevertingRunId(null);
    }
  }, [activeChatSessionId, applySessionDetail, refreshSessions, tenantSlug]);

  useEffect(() => {
    void refreshSessions().then(async () => {
      const models = await artifactsService.listCodingAgentModels();
      setChatModels(models);
      if (initialChatSessionId) {
        await loadSessionDetail(initialChatSessionId);
      }
    }).catch((error) => {
      onError(error instanceof Error ? error.message : "Failed to load artifact coding chat");
    });
  }, [initialChatSessionId, loadSessionDetail, onError, refreshSessions]);

  useEffect(() => {
    const previous = previousScopeRef.current;
    previousScopeRef.current = { artifactId, draftKey };
    const sameDraftPromotedToSaved = !previous.artifactId && artifactId && previous.draftKey === draftKey;
    if (sameDraftPromotedToSaved) {
      return;
    }
    if (scopeMode === "standalone") {
      return;
    }
    setActiveChatSessionId(null);
    activeSessionRef.current = null;
    setTimelinesBySession({});
    setPendingQuestionsBySession({});
    setIsStopping(false);
    setActiveRunIdsBySession({});
    setActiveThinkingBySession({});
    setHistoryPagesBySession({});
  }, [artifactId, draftKey, scopeMode]);

  const activateDraftChat = useCallback(() => {
    setActiveChatSessionId(null);
    activeSessionRef.current = null;
    setTimelineForSession(DRAFT_SESSION_KEY, []);
    setHistoryPagesBySession((current) => ({
      ...current,
      [DRAFT_SESSION_KEY]: { hasMore: false, nextBeforeMessageId: null },
    }));
    onResetDraftSnapshot?.();
    onApplyDraftSnapshot(scopeMode === "standalone" ? {} : getDraftSnapshot());
  }, [getDraftSnapshot, onApplyDraftSnapshot, onResetDraftSnapshot, scopeMode, setTimelineForSession]);

  const startNewChat = useCallback(() => {
    activateDraftChat();
    setIsAgentPanelOpen(true);
  }, [activateDraftChat]);

  useEffect(() => {
    onActiveChatSessionChange?.(activeChatSessionId);
  }, [activeChatSessionId, onActiveChatSessionChange]);

  const selectedRunModelLabel = useMemo(() => {
    const selected = chatModels.find((model) => model.id === selectedRunModelId);
    return selected?.label || "Auto";
  }, [chatModels, selectedRunModelId]);

  return {
    isAgentPanelOpen,
    setIsAgentPanelOpen,
    isSending,
    isStopping,
    timeline,
    activeThinkingSummary,
    chatSessions,
    activeChatSessionId,
    activateDraftChat,
    startNewChat,
    loadChatSession: loadSessionDetail,
    sendMessage,
    stopCurrentRun,
    chatModels,
    selectedRunModelId,
    setSelectedRunModelId,
    isModelSelectorOpen,
    setIsModelSelectorOpen,
    revertingRunId,
    selectedRunModelLabel,
    pendingQuestion,
    isAnsweringQuestion,
    runningSessionIds,
    hasOlderHistory,
    isLoadingOlderHistory,
    loadOlderHistory,
    answerPendingQuestion,
    revertToRun,
    refreshChatSessions: refreshSessions,
  };
}
