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
  toolName?: string;
  toolPath?: string;
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

function pickString(value: unknown): string {
  if (typeof value !== "string") return "";
  const trimmed = value.trim();
  return trimmed;
}

export function extractPrimaryToolPath(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const source = value as Record<string, unknown>;
  const directPath =
    pickString(source.path) ||
    pickString(source.filePath) ||
    pickString(source.from_path) ||
    pickString(source.to_path) ||
    pickString(source.fromPath) ||
    pickString(source.toPath);
  if (directPath) return directPath;

  const nestedInput = source.input;
  if (nestedInput && typeof nestedInput === "object") {
    const nested = nestedInput as Record<string, unknown>;
    const nestedPath =
      pickString(nested.path) ||
      pickString(nested.filePath) ||
      pickString(nested.from_path) ||
      pickString(nested.to_path) ||
      pickString(nested.fromPath) ||
      pickString(nested.toPath);
    if (nestedPath) return nestedPath;
  }
  return null;
}

export function formatToolPathLabel(path: string): string {
  const normalized = String(path || "").trim();
  if (!normalized) return "";
  const tokens = normalized.split("/").filter(Boolean);
  if (tokens.length === 0) return normalized;
  if (tokens.length === 1) return tokens[0];
  return `${tokens[tokens.length - 2]}/${tokens[tokens.length - 1]}`;
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
