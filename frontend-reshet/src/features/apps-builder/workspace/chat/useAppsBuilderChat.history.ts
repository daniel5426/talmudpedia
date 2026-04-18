import type { CodingAgentChatMessage, CodingAgentChatSessionDetail } from "@/services";

import {
  describeToolIntent,
  extractToolPathForEvent,
  extractToolTitleForEvent,
  type TimelineItem,
} from "./chat-model";

function normalizeHistoryMessage(message: CodingAgentChatMessage): TimelineItem | null {
  const role = String(message.role || "").trim().toLowerCase();
  const content = String(message.content || "").trim();
  if (role === "user") {
    return {
      id: `history-${message.id}`,
      kind: "user",
      title: "User request",
      description: content,
      tone: "default",
      userDeliveryStatus: "sent",
      clientMessageId: String(message.id || "").trim() || undefined,
    };
  }
  if (role === "assistant") {
    return {
      id: `history-${message.id}`,
      kind: "assistant",
      title: "Assistant",
      description: content,
      tone: "default",
      assistantStreamId: String(message.id || "").trim() || undefined,
    };
  }
  return null;
}

function buildToolTimelineItems(message: CodingAgentChatMessage): TimelineItem[] {
  const items: TimelineItem[] = [];
  for (const part of message.parts || []) {
    if (String(part.type || "").trim().toLowerCase() !== "tool") {
      continue;
    }
    const state = part.state || {};
    const statusRaw = String(state.status || "").trim().toLowerCase();
    const toolName = String(part.tool || "").trim() || "tool";
    const toolCallId = String(part.call_id || part.id || "").trim() || `tool-${message.id}-${items.length + 1}`;
    const payload = {
      tool: toolName,
      span_id: toolCallId,
      input: state.input || undefined,
      output: state.output,
      error: state.error || undefined,
    };
    const status =
      statusRaw === "error"
        ? "failed"
        : statusRaw === "completed"
          ? "completed"
          : "running";
    const toolPath = extractToolPathForEvent(toolName, payload);
    let title =
      extractToolTitleForEvent(toolName, payload, status === "running" ? "completed" : status, toolPath || undefined)
      || String(state.title || "").trim()
      || describeToolIntent(toolName);
    if (
      toolName.trim().toLowerCase() === "bash"
      && status === "completed"
      && /^run\s+/i.test(title)
    ) {
      title = `Ran ${title.replace(/^run\s+/i, "").trim()}`;
    }
    items.push({
      id: `history-tool-${toolCallId}`,
      kind: "tool",
      toolCallId,
      toolStatus: status === "running" ? "completed" : status,
      title,
      tone: status === "failed" ? "error" : "success",
      toolName,
      toolPath: toolPath || undefined,
      toolDetail: String(state.error || "").trim() || undefined,
    });
  }
  return items;
}

export function buildTimelineFromChatHistory(detail: CodingAgentChatSessionDetail): TimelineItem[] {
  const timeline: TimelineItem[] = [];
  for (const message of detail.messages || []) {
    const normalized = normalizeHistoryMessage(message);
    if (!normalized) {
      continue;
    }
    if (normalized.kind === "assistant") {
      timeline.push(...buildToolTimelineItems(message));
    }
    timeline.push(normalized);
  }
  return timeline;
}
