export type TimelineTone = "default" | "success" | "error";
export type TimelineKind = "user" | "assistant" | "tool";
export type ToolRunStatus = "running" | "completed" | "failed";
export type UserDeliveryStatus = "pending" | "sent" | "failed";

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

export function timelineId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function isUserTimelineItem(item: TimelineItem): boolean {
  return item.kind === "user";
}

export function isAssistantTimelineItem(item: TimelineItem): boolean {
  return item.kind === "assistant";
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
