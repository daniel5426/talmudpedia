export type TimelineTone = "default" | "success" | "error";
export type TimelineKind = "user" | "assistant" | "tool";
export type ToolRunStatus = "running" | "completed" | "failed";

export type TimelineItem = {
  id: string;
  kind: TimelineKind;
  title: string;
  description?: string;
  tone?: TimelineTone;
  toolCallId?: string;
  toolStatus?: ToolRunStatus;
  assistantStreamId?: string;
  checkpointId?: string;
};

export function timelineId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeToolName(toolName: string): string {
  return toolName.trim().toLowerCase();
}

export function describeToolIntent(toolName: string): string {
  const normalized = normalizeToolName(toolName);
  if (normalized.includes("read_file")) return "Reading file";
  if (normalized.includes("write_file")) return "Editing file";
  if (normalized.includes("search_code")) return "Searching code";
  if (normalized.includes("list_files")) return "Listing files";
  if (normalized.includes("rename_file")) return "Renaming file";
  if (normalized.includes("delete_file")) return "Deleting file";
  if (normalized.includes("snapshot_files")) return "Snapshotting workspace";
  if (normalized.includes("run_targeted_tests")) return "Running tests";
  if (normalized.includes("build_worker_precheck")) return "Running build precheck";
  return `Running ${toolName || "tool"}`;
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
