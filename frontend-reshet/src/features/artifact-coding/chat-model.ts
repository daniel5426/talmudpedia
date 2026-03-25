export type TimelineTone = "default" | "success" | "error";
export type TimelineKind = "user" | "assistant" | "orchestrator" | "tool";
export type ToolRunStatus = "running" | "completed" | "failed";
export type UserDeliveryStatus = "pending" | "sent" | "failed";
export type ArtifactCodingHistoryMessage = {
  id: string;
  run_id: string;
  role: "user" | "assistant" | "orchestrator" | string;
  content: string;
};
export type ArtifactCodingRunEvent = {
  run_id: string;
  event: string;
  stage: string;
  payload: Record<string, unknown>;
  diagnostics?: Array<Record<string, unknown>>;
  ts?: string | null;
};

export type TimelineItem = {
  id: string;
  kind: TimelineKind;
  title: string;
  description?: string;
  tone?: TimelineTone;
  toolCallId?: string;
  toolStatus?: ToolRunStatus;
  toolName?: string;
  toolPath?: string;
  toolDetail?: string;
  assistantStreamId?: string;
  userDeliveryStatus?: UserDeliveryStatus;
  runId?: string;
};

export function finalizeRunningToolItems(
  timeline: TimelineItem[],
  status: Extract<ToolRunStatus, "completed" | "failed">,
  runId?: string | null,
): TimelineItem[] {
  let changed = false;
  const next = timeline.map((item) => {
    if (item.kind !== "tool" || item.toolStatus !== "running") return item;
    if (runId && item.runId !== runId) return item;
    changed = true;
    return {
      ...item,
      toolStatus: status,
      tone: status === "failed" ? "error" : "success",
    };
  });
  return changed ? next : timeline;
}

export function finalizeStreamingAssistantSegment(
  timeline: TimelineItem[],
  assistantStreamId: string | null,
): TimelineItem[] {
  if (!assistantStreamId) return timeline;
  let changed = false;
  const next = timeline.map((item) => {
    if (item.kind !== "assistant" || item.assistantStreamId !== assistantStreamId) {
      return item;
    }
    changed = true;
    return { ...item, assistantStreamId: undefined };
  });
  return changed ? next : timeline;
}

function buildRunTimelineItems(
  runId: string,
  runEvents: ArtifactCodingRunEvent[],
  fallbackAssistantText: string,
): TimelineItem[] {
  const timeline: TimelineItem[] = [];
  const toolIndexByCallId = new Map<string, number>();
  let assistantBuffer = "";
  let assistantSegmentIndex = 0;

  const flushAssistantBuffer = () => {
    const content = assistantBuffer.trim();
    if (!content) {
      assistantBuffer = "";
      return;
    }
    timeline.push({
      id: `${runId}-assistant-${assistantSegmentIndex}`,
      kind: "assistant",
      title: "Assistant",
      description: content,
      runId,
    });
    assistantSegmentIndex += 1;
    assistantBuffer = "";
  };

  for (const event of runEvents) {
    if (event.event === "assistant.delta") {
      assistantBuffer += String(event.payload?.content || "");
      continue;
    }
    if (event.event !== "tool.started" && event.event !== "tool.completed" && event.event !== "tool.failed") {
      continue;
    }
    flushAssistantBuffer();
    const payload = event.payload || {};
    const output = payload.output && typeof payload.output === "object" ? payload.output as Record<string, unknown> : {};
    const toolCallId = String(payload.span_id || timelineId("tool-call"));
    const toolName = String(payload.tool || payload.display_name || "tool");
    const toolStatus = event.event === "tool.started" ? "running" : event.event === "tool.failed" ? "failed" : "completed";
    const nextItem: TimelineItem = {
      id: toolIndexByCallId.has(toolCallId) ? timeline[toolIndexByCallId.get(toolCallId)!].id : `${runId}-tool-${toolCallId}`,
      kind: "tool",
      title: String(output.summary || payload.summary || toolName),
      toolCallId,
      toolStatus,
      tone: toolStatus === "failed" ? "error" : toolStatus === "completed" ? "success" : undefined,
      toolName,
      toolPath: typeof output.path === "string" ? output.path : undefined,
      toolDetail: typeof output.summary === "string" ? output.summary : undefined,
      runId,
    };
    const existingIndex = toolIndexByCallId.get(toolCallId);
    if (existingIndex !== undefined) {
      timeline[existingIndex] = nextItem;
    } else {
      toolIndexByCallId.set(toolCallId, timeline.length);
      timeline.push(nextItem);
    }
  }

  flushAssistantBuffer();
  if (!timeline.some((item) => item.kind === "assistant") && fallbackAssistantText.trim()) {
    timeline.push({
      id: `${runId}-assistant-final`,
      kind: "assistant",
      title: "Assistant",
      description: fallbackAssistantText.trim(),
      runId,
    });
  }
  return timeline;
}

export function buildArtifactCodingTimeline(
  messages: ArtifactCodingHistoryMessage[],
  runEvents: ArtifactCodingRunEvent[],
): TimelineItem[] {
  const eventsByRunId = new Map<string, ArtifactCodingRunEvent[]>();
  for (const event of runEvents || []) {
    const list = eventsByRunId.get(event.run_id) || [];
    list.push(event);
    eventsByRunId.set(event.run_id, list);
  }

  const assistantRunIds = new Set(
    (messages || [])
      .filter((message) => message.role === "assistant")
      .map((message) => message.run_id),
  );
  const renderedEventRuns = new Set<string>();
  const timeline: TimelineItem[] = [];
  for (const message of messages || []) {
    if (message.role === "user") {
      timeline.push({
        id: message.id,
        kind: "user",
        title: "You",
        description: message.content,
        userDeliveryStatus: "sent",
        runId: message.run_id,
      });
      if (!assistantRunIds.has(message.run_id) && !renderedEventRuns.has(message.run_id)) {
        timeline.push(...buildRunTimelineItems(message.run_id, eventsByRunId.get(message.run_id) || [], ""));
        renderedEventRuns.add(message.run_id);
      }
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
      if (!assistantRunIds.has(message.run_id) && !renderedEventRuns.has(message.run_id)) {
        timeline.push(...buildRunTimelineItems(message.run_id, eventsByRunId.get(message.run_id) || [], ""));
        renderedEventRuns.add(message.run_id);
      }
      continue;
    }
    timeline.push(...buildRunTimelineItems(message.run_id, eventsByRunId.get(message.run_id) || [], message.content));
    renderedEventRuns.add(message.run_id);
  }
  return timeline;
}

export function timelineId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function isUserTimelineItem(item: TimelineItem): boolean {
  return item.kind === "user";
}

export function isAssistantTimelineItem(item: TimelineItem): boolean {
  return item.kind === "assistant";
}

export function isOrchestratorTimelineItem(item: TimelineItem): boolean {
  return item.kind === "orchestrator";
}

export function isToolTimelineItem(item: TimelineItem): boolean {
  return item.kind === "tool";
}

function normalizeToolName(toolName: string): string {
  return toolName.trim().toLowerCase();
}

export function isReadToolName(toolName: string): boolean {
  const normalized = normalizeToolName(toolName);
  return normalized.includes("read_file") || normalized.includes("get_form_state") || normalized.includes("get_context");
}

export function isSearchToolName(toolName: string): boolean {
  return normalizeToolName(toolName).includes("search");
}

export function isExplorationToolName(toolName: string): boolean {
  return isReadToolName(toolName) || isSearchToolName(toolName) || normalizeToolName(toolName).includes("list_files");
}

export function isEditToolName(toolName: string): boolean {
  const normalized = normalizeToolName(toolName);
  return (
    normalized.includes("replace_file")
    || normalized.includes("update_file_range")
    || normalized.includes("create_file")
    || normalized.includes("delete_file")
    || normalized.includes("rename_file")
    || normalized.includes("set_")
  );
}

export function formatToolPathLabel(path: string): string {
  const normalized = String(path || "").trim().replace(/^\/+/, "");
  return normalized || "artifact";
}

export function formatToolReadPath(path: string): string {
  return formatToolPathLabel(path);
}
