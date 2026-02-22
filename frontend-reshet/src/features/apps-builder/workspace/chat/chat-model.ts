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
  if (normalized === "read" || normalized.includes("read_file")) return "Reading file";
  if (normalized.includes("read_agent_context")) return "Reading agent context";
  if (normalized === "bash" || normalized.includes("run_command")) return "Running command";
  if (normalized === "grep" || normalized.includes("search_code")) return "Searching code";
  if (normalized.includes("todowrite")) return "Updating plan";
  if (normalized.includes("apply_patch")) return "Applying code changes";
  if (normalized.includes("write_file")) return "Editing file";
  if (normalized.includes("list_files")) return "Listing files";
  if (normalized.includes("rename_file")) return "Renaming file";
  if (normalized.includes("delete_file")) return "Deleting file";
  if (normalized.includes("snapshot_files")) return "Snapshotting workspace";
  if (normalized.includes("run_targeted_tests")) return "Running tests";
  if (normalized.includes("build_worker_precheck")) return "Running build precheck";
  return `Running ${toolName || "tool"}`;
}

const DIRECT_PATH_KEYS = [
  "path",
  "file",
  "file_path",
  "filepath",
  "filename",
  "filePath",
  "relative_path",
  "relativePath",
  "relative_workspace_path",
  "workspace_path",
  "target_path",
  "from_path",
  "to_path",
  "fromPath",
  "toPath",
  "target",
] as const;

const WRAPPER_KEYS = [
  "input",
  "output",
  "arguments",
  "args",
  "value",
  "values",
  "params",
  "parameters",
  "payload",
  "data",
  "request",
  "result",
  "state",
  "options",
  "tool_input",
  "toolInput",
] as const;

function stripEdgeQuotes(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

function stripPathTagWrappers(value: string): string {
  let cleaned = value.trim();
  let previous = "";
  while (cleaned !== previous) {
    previous = cleaned;
    cleaned = cleaned
      .replace(/^<\s*path\s*>?/i, "")
      .replace(/^path\s*>/i, "")
      .replace(/<\/\s*path\s*>?$/i, "")
      .replace(/<\/\s*path$/i, "")
      .replace(/<\/?path>/gi, "")
      .trim();
  }
  return cleaned;
}

function extractWrappedPathContent(value: string): string | null {
  const match = value.match(/<path>\s*([^<]+?)\s*<\/path>/i);
  if (!match) return null;
  return stripEdgeQuotes(stripPathTagWrappers(match[1] || ""));
}

function normalizeExtractedPath(value: string): string {
  const stripped = stripEdgeQuotes(stripPathTagWrappers(value)).replace(/\\/g, "/").trim();
  if (!stripped) return "";
  if (stripped.endsWith("/workspace")) return "workspace";
  const workspaceIdx = stripped.lastIndexOf("/workspace/");
  if (workspaceIdx >= 0) {
    const relative = stripped.slice(workspaceIdx + "/workspace/".length).replace(/^\/+/, "");
    return relative || "workspace";
  }
  return stripped;
}

function isLikelyPath(value: string): boolean {
  const candidate = normalizeExtractedPath(value);
  if (!candidate) return false;
  if (candidate.length > 400) return false;
  if (candidate.includes("\n")) return false;
  if (/^https?:\/\//i.test(candidate)) return false;
  if (/^@[^/\s]+\/[^/\s]+$/i.test(candidate)) return false;
  if (candidate.startsWith("{") || candidate.startsWith("[")) return false;
  if (
    candidate.startsWith("./") ||
    candidate.startsWith("../") ||
    candidate.startsWith("/") ||
    /^[a-zA-Z]:\\/.test(candidate)
  ) {
    return true;
  }
  if (candidate.includes("/") || candidate.includes("\\")) return true;
  return /\.[a-zA-Z0-9]{1,10}$/.test(candidate);
}

function isLikelyWorkspaceRelativeDirectory(value: string): boolean {
  return /^[a-zA-Z0-9._-]+$/.test(value) && !value.startsWith("@");
}

function extractPathTokenFromText(value: string): string | null {
  const text = value.trim();
  if (!text) return null;

  const quotedMatch = text.match(/["']([^"'\n]*[\\/][^"'\n]+)["']/);
  if (quotedMatch && isLikelyPath(quotedMatch[1])) {
    return stripEdgeQuotes(quotedMatch[1]);
  }

  for (const rawToken of text.split(/\s+/)) {
    const token = rawToken.replace(/^[('"`<]+|[)"'`,;:>]+$/g, "");
    if (!token) continue;
    const eqIndex = token.indexOf("=");
    const candidate = eqIndex >= 0 ? token.slice(eqIndex + 1) : token;
    if (isLikelyPath(candidate)) {
      return normalizeExtractedPath(candidate);
    }
  }

  return null;
}

function extractPathFromString(value: string, seen: Set<unknown>): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const wrapped = extractWrappedPathContent(trimmed);
  if (wrapped && isLikelyPath(wrapped)) {
    return normalizeExtractedPath(wrapped);
  }
  const normalizedTrimmed = normalizeExtractedPath(trimmed);
  const hintsWrappedWorkspacePath =
    /<\/?\s*path\b/i.test(trimmed) ||
    /^path\s*>/i.test(trimmed) ||
    trimmed.includes("/workspace");
  if (
    hintsWrappedWorkspacePath &&
    normalizedTrimmed &&
    (isLikelyPath(normalizedTrimmed) || isLikelyWorkspaceRelativeDirectory(normalizedTrimmed))
  ) {
    return normalizedTrimmed;
  }
  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    try {
      const parsed = JSON.parse(trimmed);
      return extractPrimaryToolPathInternal(parsed, seen);
    } catch {
      // Continue with plain string checks.
    }
  }
  if (isLikelyPath(trimmed)) return normalizeExtractedPath(trimmed);
  return extractPathTokenFromText(trimmed);
}

function extractPrimaryToolPathInternal(value: unknown, seen: Set<unknown>): string | null {
  if (typeof value === "string") {
    return extractPathFromString(value, seen);
  }

  if (Array.isArray(value)) {
    for (const candidate of value) {
      const resolved = extractPrimaryToolPathInternal(candidate, seen);
      if (resolved) return resolved;
    }
    return null;
  }

  if (!value || typeof value !== "object") return null;
  if (seen.has(value)) return null;
  seen.add(value);
  const source = value as Record<string, unknown>;

  for (const key of DIRECT_PATH_KEYS) {
    const resolved = extractPrimaryToolPathInternal(source[key], seen);
    if (resolved) return resolved;
  }

  const paths = source.paths;
  if (Array.isArray(paths)) {
    for (const candidate of paths) {
      const resolved = extractPrimaryToolPathInternal(candidate, seen);
      if (resolved) return resolved;
    }
  }

  const files = source.files;
  if (Array.isArray(files)) {
    for (const candidate of files) {
      const resolved = extractPrimaryToolPathInternal(candidate, seen);
      if (resolved) return resolved;
    }
  }

  for (const key of WRAPPER_KEYS) {
    const resolved = extractPrimaryToolPathInternal(source[key], seen);
    if (resolved) return resolved;
  }

  for (const [key, candidate] of Object.entries(source)) {
    const normalizedKey = key.trim().toLowerCase();
    if (normalizedKey.includes("path") || normalizedKey.includes("file") || normalizedKey.includes("target")) {
      const resolved = extractPrimaryToolPathInternal(candidate, seen);
      if (resolved) return resolved;
    }
  }

  for (const candidate of Object.values(source)) {
    if (!candidate || typeof candidate !== "object") continue;
    const resolved = extractPrimaryToolPathInternal(candidate, seen);
    if (resolved) return resolved;
  }

  return null;
}

export function extractPrimaryToolPath(value: unknown): string | null {
  return extractPrimaryToolPathInternal(value, new Set<unknown>());
}

export function formatToolPathLabel(path: string): string {
  const normalized = normalizeExtractedPath(String(path || ""));
  if (!normalized) return "";
  const tokens = normalized.split("/").filter(Boolean);
  if (tokens.length === 0) return normalized;
  if (tokens.length === 1) return tokens[0];
  return `${tokens[tokens.length - 2]}/${tokens[tokens.length - 1]}`;
}

export function formatToolReadPath(path: string): string {
  return normalizeExtractedPath(String(path || ""));
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
