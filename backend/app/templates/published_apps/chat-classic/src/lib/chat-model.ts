function normalizeToolName(toolName: string): string {
  return toolName.trim().toLowerCase();
}

export function describeToolIntent(toolName: string): string {
  const normalized = normalizeToolName(toolName);
  if (normalized === "read" || normalized.includes("read_file")) return "Reading file";
  if (normalized === "grep" || normalized === "glob" || normalized.includes("search")) return "Searching code";
  if (normalized.includes("bash") || normalized.includes("command")) return "Running command";
  if (normalized.includes("write") || normalized.includes("edit") || normalized.includes("patch")) return "Editing file";
  if (normalized.includes("fetch")) return "Fetching data";
  return `Running ${toolName || "tool"}`;
}

export function isReadToolName(toolName: string): boolean {
  const normalized = normalizeToolName(toolName);
  return normalized === "read" || normalized.includes("read_file");
}

export function isSearchToolName(toolName: string): boolean {
  const normalized = normalizeToolName(toolName);
  return normalized === "grep" || normalized === "glob" || normalized.includes("search");
}

export function isExplorationToolName(toolName: string): boolean {
  return isReadToolName(toolName) || isSearchToolName(toolName);
}

export function isEditToolName(toolName: string): boolean {
  const normalized = normalizeToolName(toolName);
  return normalized.includes("apply_patch") || normalized.includes("write") || normalized.includes("edit");
}

const PATH_KEYS = [
  "path",
  "file",
  "file_path",
  "filepath",
  "filename",
  "relative_path",
  "workspace_path",
  "target_path",
  "from_path",
  "to_path",
];

const WRAPPER_KEYS = [
  "input",
  "arguments",
  "args",
  "params",
  "parameters",
  "payload",
  "data",
  "request",
];

function isLikelyPath(value: string): boolean {
  const candidate = value.trim();
  if (!candidate || candidate.length > 260) return false;
  if (candidate.includes("\n")) return false;
  if (/^https?:\/\//i.test(candidate)) return false;
  return candidate.startsWith("/") || candidate.startsWith("./") || candidate.startsWith("../") || candidate.includes("/");
}

export function extractToolPath(data: Record<string, unknown>, depth = 0): string {
  if (depth > 2) return "";
  for (const key of PATH_KEYS) {
    const value = data[key];
    if (typeof value === "string" && isLikelyPath(value)) {
      return value.trim();
    }
  }
  for (const key of WRAPPER_KEYS) {
    const value = data[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const nested = extractToolPath(value as Record<string, unknown>, depth + 1);
      if (nested) return nested;
    }
  }
  return "";
}

export function formatToolPathLabel(path: string): string {
  const clean = path.trim();
  if (!clean) return "";
  const normalized = clean.replace(/\\/g, "/");
  const workspaceIndex = normalized.indexOf("/workspace/");
  if (workspaceIndex >= 0) {
    return normalized.slice(workspaceIndex + "/workspace/".length);
  }
  return normalized;
}

export function formatToolReadPath(path: string): string {
  return formatToolPathLabel(path) || "workspace";
}

export function formatDetailLabel(data: Record<string, unknown>): string {
  const raw =
    (typeof data.query === "string" && data.query) ||
    (typeof data.pattern === "string" && data.pattern) ||
    (typeof data.command === "string" && data.command) ||
    (typeof data.description === "string" && data.description) ||
    "";
  return raw.trim();
}

export function inferReasoningText(kind: string, data: Record<string, unknown>): string {
  if (kind.includes("reason") || kind.includes("think") || kind.includes("analysis")) {
    return (
      (typeof data.label === "string" && data.label.trim()) ||
      (typeof data.description === "string" && data.description.trim()) ||
      "Thinking"
    );
  }
  if (kind.includes("retriev")) {
    return (
      (typeof data.query === "string" && `Searching for "${data.query}"`) ||
      "Retrieving sources"
    );
  }
  return "";
}
