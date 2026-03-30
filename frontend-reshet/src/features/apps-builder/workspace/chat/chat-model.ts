export type TimelineTone = "default" | "success" | "error";
export type TimelineKind = "user" | "assistant" | "tool";
export type ToolRunStatus = "running" | "completed" | "failed";
export type UserDeliveryStatus = "pending" | "queued" | "sent" | "failed";

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
  checkpointId?: string;
  userDeliveryStatus?: UserDeliveryStatus;
  clientMessageId?: string;
  queueItemId?: string;
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
  if (normalized === "bash" || normalized.includes("run_command") || normalized === "command") return "Running command";
  if (normalized === "grep" || normalized.includes("search_code") || normalized === "glob" || normalized === "codesearch") return "Searching code";
  if (normalized.includes("todowrite")) return "Updating plan";
  if (normalized.includes("apply_patch")) return "Running edit";
  if (normalized.includes("write_file")) return "Editing file";
  if (normalized.includes("list_files")) return "Listing files";
  if (normalized.includes("rename_file")) return "Renaming file";
  if (normalized.includes("delete_file")) return "Deleting file";
  if (normalized.includes("snapshot_files")) return "Snapshotting workspace";
  if (normalized.includes("run_targeted_tests")) return "Running tests";
  if (normalized.includes("build_worker_precheck")) return "Running build precheck";
  return `Running ${toolName || "tool"}`;
}

function prettifyActionToken(token: string): string {
  return token
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function inferPlatformActionSubject(action: string): string | null {
  const normalized = action.trim().toLowerCase();
  const subject = normalized.split(".").slice(0, -1).join(".");

  const subjectMap: Record<string, string> = {
    "agents.nodes": "agent node types",
    "agents.graph": "agent graph",
    "agents": "agent",
    "rag.operators": "RAG operators",
    "rag.graph": "RAG graph",
    "rag": "RAG pipeline",
    "tools": "tools",
    "artifacts": "artifacts",
    "models": "models",
    "credentials": "credentials",
    "knowledge_stores": "knowledge stores",
    "auth": "auth settings",
    "orchestration": "orchestration settings",
  };

  return subjectMap[subject] || null;
}

function inferPlatformActionTitle(action: string, status: ToolRunStatus): string | null {
  const normalized = action.trim().toLowerCase();
  if (!normalized) return null;
  const exactTitleMap: Record<string, string> = {
    "agents.nodes.catalog": "List agent node types",
    "agents.nodes.schema": "Get node schemas",
    "agents.nodes.validate": "Validate agent nodes",
    "agents.validate": "Validate agent",
    "rag.operators.catalog": "List RAG operators",
    "rag.operators.schema": "Get RAG operator schemas",
  };
  if (exactTitleMap[normalized]) {
    return exactTitleMap[normalized];
  }
  const tokens = normalized.split(".");
  const verb = tokens[tokens.length - 1] || "";
  const subject = inferPlatformActionSubject(normalized);
  if (!subject) return null;

  if (verb === "catalog" || verb.startsWith("list_")) {
    return `List ${subject}`;
  }
  if (verb === "schema") {
    return `Get ${subject} schemas`;
  }
  if (verb === "validate" || verb.startsWith("validate_")) {
    return `Validate ${subject}`;
  }
  if (verb === "get" || verb.startsWith("get_")) {
    return `Get ${subject}`;
  }
  if (verb === "create" || verb.startsWith("create_")) {
    return `Create ${subject}`;
  }
  if (verb === "update" || verb.startsWith("update_") || verb.startsWith("set_") || verb.startsWith("attach_")) {
    return `Update ${subject}`;
  }
  if (verb === "compile" || verb.startsWith("compile_")) {
    return `Compile ${subject}`;
  }
  if (verb === "publish" || verb.startsWith("publish_") || verb === "promote" || verb.startsWith("promote_")) {
    return `${status === "completed" ? "Published" : "Publishing"} ${subject}`;
  }
  if (verb === "delete" || verb.startsWith("delete_") || verb === "remove" || verb.startsWith("remove_")) {
    return `Delete ${subject}`;
  }

  return `${prettifyActionToken(verb)} ${subject}`;
}

export function isReadToolName(toolName: string): boolean {
  const normalized = normalizeToolName(toolName);
  return normalized === "read" || normalized.includes("read_file");
}

export function isSearchToolName(toolName: string): boolean {
  const normalized = normalizeToolName(toolName);
  return normalized === "grep" || normalized === "glob" || normalized === "codesearch" || normalized.includes("search_code");
}

export function isExplorationToolName(toolName: string): boolean {
  return isReadToolName(toolName) || isSearchToolName(toolName);
}

export function isEditToolName(toolName: string): boolean {
  const normalized = normalizeToolName(toolName);
  return normalized.includes("apply_patch") || normalized.includes("write_file") || normalized === "edit";
}

export function isCommandToolName(toolName: string): boolean {
  const normalized = normalizeToolName(toolName);
  return normalized === "bash" || normalized.includes("run_command") || normalized === "command";
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
  const tempWorkspaceByUuid = stripped.match(
    /\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/(.+)$/i,
  );
  if (tempWorkspaceByUuid && tempWorkspaceByUuid[1]) {
    const relative = tempWorkspaceByUuid[1].replace(/^\/+/, "");
    if (relative) return relative;
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

function extractPatchFilePath(patchText: string): string | null {
  const lines = patchText.split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    const match = line.match(/^\*\*\*\s+(?:Update|Add|Delete)\s+File:\s+(.+)$/i);
    if (!match) continue;
    const candidate = normalizeExtractedPath(match[1] || "");
    if (candidate) return candidate;
  }
  return null;
}

export function extractToolPathForEvent(toolName: string, payload: unknown): string | null {
  const normalized = normalizeToolName(toolName);
  const source = (payload && typeof payload === "object" ? payload : {}) as Record<string, unknown>;
  const inputPath = extractPrimaryToolPath(source.input);
  if (inputPath) return inputPath;
  if (normalized.includes("apply_patch")) {
    const patchText = String(((source.input as Record<string, unknown> | undefined)?.patchText) || "").trim();
    if (patchText) {
      const patchPath = extractPatchFilePath(patchText);
      if (patchPath) return patchPath;
    }
  }
  if (isCommandToolName(toolName)) {
    return null;
  }
  return extractPrimaryToolPath(source.output ?? source);
}

function firstNonEmptyString(values: unknown[]): string {
  for (const value of values) {
    const normalized = String(value || "").trim();
    if (normalized) return normalized;
  }
  return "";
}

export function extractToolTitleForEvent(
  toolName: string,
  payload: unknown,
  status: ToolRunStatus,
  toolPath?: string | null,
): string {
  if (isEditToolName(toolName)) {
    const pathLabel = formatToolPathLabel(String(toolPath || ""));
    if (status === "completed") {
      return pathLabel ? `Edited ${pathLabel}` : "Edited file";
    }
    if (status === "running") {
      return pathLabel ? `Editing ${pathLabel}` : "Editing file";
    }
  }
  const source = (payload && typeof payload === "object" ? payload : {}) as Record<string, unknown>;
  const input = (source.input && typeof source.input === "object" ? source.input : {}) as Record<string, unknown>;
  const output = (source.output && typeof source.output === "object" ? source.output : {}) as Record<string, unknown>;
  const action = firstNonEmptyString([
    source.action,
    input.action,
    output.action,
  ]);
  const actionTitle = inferPlatformActionTitle(action, status);
  if (actionTitle) return actionTitle;
  const title = firstNonEmptyString([
    source.title,
    output.title,
    output.description,
    input.title,
    input.description,
    typeof source.display_name === "string" && source.display_name.length <= 48 ? source.display_name : "",
    typeof source.summary === "string" && source.summary.length <= 48 ? source.summary : "",
  ]);
  return title || describeToolIntent(toolName);
}

export function extractToolDetailForEvent(toolName: string, payload: unknown): string | null {
  const normalized = normalizeToolName(toolName);
  if (!isSearchToolName(normalized)) return null;
  const source = (payload && typeof payload === "object" ? payload : {}) as Record<string, unknown>;
  const input = (source.input && typeof source.input === "object" ? source.input : {}) as Record<string, unknown>;
  const output = (source.output && typeof source.output === "object" ? source.output : {}) as Record<string, unknown>;
  const detail = firstNonEmptyString([
    source.title,
    input.pattern,
    input.query,
    input.path,
    input.filePath,
    output.title,
  ]);
  return detail || null;
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
