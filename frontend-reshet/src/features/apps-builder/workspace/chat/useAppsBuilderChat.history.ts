import type { CodingAgentChatMessage, CodingAgentChatSessionDetail, CodingAgentRunEvent } from "@/services";

import {
  describeToolIntent,
  extractPrimaryToolPath,
  type TimelineItem,
} from "./chat-model";

function normalizeToolStatus(eventName: CodingAgentRunEvent["event"]): "running" | "completed" | "failed" {
  if (eventName === "tool.completed") return "completed";
  if (eventName === "tool.failed") return "failed";
  return "running";
}

function normalizeToolTone(status: "running" | "completed" | "failed"): TimelineItem["tone"] {
  if (status === "completed") return "success";
  if (status === "failed") return "error";
  return undefined;
}

function buildToolTimelineItemsForRun(runId: string, runEvents: CodingAgentRunEvent[]): TimelineItem[] {
  const toolByCallId = new Map<string, TimelineItem>();
  const orderedCallIds: string[] = [];
  const seenCallIds = new Set<string>();
  const runningCallIdsByToolName = new Map<string, string[]>();
  const allCallIdsByToolName = new Map<string, string[]>();
  let syntheticCallCounter = 0;

  for (const event of runEvents) {
    const payload = event.payload && typeof event.payload === "object" ? event.payload : {};
    const toolName = String((payload as Record<string, unknown>).tool || "tool");
    const spanIdRaw = String((payload as Record<string, unknown>).span_id || "").trim();
    const normalizedToolName = toolName.trim().toLowerCase() || "tool";
    let toolCallId = spanIdRaw;
    if (!toolCallId) {
      if (event.event === "tool.started") {
        toolCallId = `${runId}-tool-${syntheticCallCounter++}`;
      } else {
        const runningIds = runningCallIdsByToolName.get(normalizedToolName) || [];
        if (runningIds.length > 0) {
          toolCallId = runningIds[0];
        } else {
          const knownIds = allCallIdsByToolName.get(normalizedToolName) || [];
          toolCallId = knownIds[knownIds.length - 1] || `${runId}-tool-${syntheticCallCounter++}`;
        }
      }
    }
    if (!seenCallIds.has(toolCallId)) {
      orderedCallIds.push(toolCallId);
      seenCallIds.add(toolCallId);
    }
    if (!allCallIdsByToolName.has(normalizedToolName)) {
      allCallIdsByToolName.set(normalizedToolName, []);
    }
    if (!(allCallIdsByToolName.get(normalizedToolName) || []).includes(toolCallId)) {
      allCallIdsByToolName.get(normalizedToolName)!.push(toolCallId);
    }
    const nextStatus = normalizeToolStatus(event.event);
    const tone = normalizeToolTone(nextStatus);
    const pathSource =
      event.event === "tool.started"
        ? ((payload as Record<string, unknown>).input ?? payload)
        : ((payload as Record<string, unknown>).output ?? payload);
    const nextPath = extractPrimaryToolPath(pathSource);
    const existing = toolByCallId.get(toolCallId);
    toolByCallId.set(toolCallId, {
      id: existing?.id || `history-tool-${runId}-${toolByCallId.size + 1}`,
      kind: "tool",
      toolCallId,
      toolStatus: nextStatus,
      title: describeToolIntent(toolName),
      tone,
      toolName,
      toolPath: nextPath || existing?.toolPath || undefined,
    });
    if (nextStatus === "running") {
      if (!runningCallIdsByToolName.has(normalizedToolName)) {
        runningCallIdsByToolName.set(normalizedToolName, []);
      }
      const runningIds = runningCallIdsByToolName.get(normalizedToolName)!;
      if (!runningIds.includes(toolCallId)) {
        runningIds.push(toolCallId);
      }
    } else {
      const runningIds = runningCallIdsByToolName.get(normalizedToolName) || [];
      runningCallIdsByToolName.set(
        normalizedToolName,
        runningIds.filter((id) => id !== toolCallId),
      );
    }
  }

  const items: TimelineItem[] = [];
  for (const callId of orderedCallIds) {
    const baseItem = toolByCallId.get(callId);
    if (!baseItem) {
      continue;
    }
    // Restored history is terminal; never leave historical rows shimmering.
    const item =
      baseItem.toolStatus === "running"
        ? { ...baseItem, toolStatus: "completed" as const, tone: "success" as const }
        : baseItem;
    if (item) {
      items.push(item);
    }
  }
  return items;
}

function normalizeHistoryMessage(message: CodingAgentChatMessage): TimelineItem | null {
  const role = String(message.role || "").trim().toLowerCase();
  const content = String(message.content || "").trim();
  if (!content) {
    return null;
  }
  if (role === "user") {
    return {
      id: `history-${message.id}`,
      kind: "user",
      title: "User request",
      description: content,
      tone: "default",
      userDeliveryStatus: "sent",
    };
  }
  if (role === "assistant") {
    return {
      id: `history-${message.id}`,
      kind: "assistant",
      title: "Assistant",
      description: content,
      tone: "default",
    };
  }
  return null;
}

export function buildTimelineFromChatHistory(detail: CodingAgentChatSessionDetail): TimelineItem[] {
  const runEventsByRunId = new Map<string, CodingAgentRunEvent[]>();
  for (const event of detail.run_events || []) {
    const runId = String(event.run_id || "").trim();
    if (!runId) continue;
    if (!runEventsByRunId.has(runId)) {
      runEventsByRunId.set(runId, []);
    }
    runEventsByRunId.get(runId)!.push(event);
  }

  const emittedRunToolEvents = new Set<string>();
  const timeline: TimelineItem[] = [];
  for (const message of detail.messages || []) {
    const normalized = normalizeHistoryMessage(message);
    if (!normalized) {
      continue;
    }
    if (normalized.kind === "assistant") {
      const runId = String(message.run_id || "").trim();
      if (runId && !emittedRunToolEvents.has(runId)) {
        const runEvents = runEventsByRunId.get(runId) || [];
        timeline.push(...buildToolTimelineItemsForRun(runId, runEvents));
        emittedRunToolEvents.add(runId);
      }
    }
    timeline.push(normalized);
  }

  return timeline;
}
