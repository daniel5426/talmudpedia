export const APPS_BUILDER_BLOCKED_FILE_PATH_PREFIXES = [
  ".cache/",
  ".talmudpedia/",
  ".opencode/.bun/",
] as const;

export const APPS_BUILDER_BLOCKED_FILE_PATH_EXACT = [
  ".cache",
  ".talmudpedia",
  ".opencode/.bun",
  ".draft-dev.log",
  ".draft-dev-dependency-hash",
] as const;

export const APPS_BUILDER_BLOCKED_FILE_PATH_SEGMENTS = [
  "node_modules",
] as const;

function normalizeBuilderFilePath(path: string): string {
  return String(path || "").replace(/\\/g, "/").trim().replace(/^\/+/, "");
}

export function isAppsBuilderBlockedFilePath(path: string): boolean {
  const normalized = normalizeBuilderFilePath(path);
  if (!normalized) return true;

  if (APPS_BUILDER_BLOCKED_FILE_PATH_EXACT.includes(normalized as (typeof APPS_BUILDER_BLOCKED_FILE_PATH_EXACT)[number])) {
    return true;
  }
  if (APPS_BUILDER_BLOCKED_FILE_PATH_PREFIXES.some((prefix) => normalized.startsWith(prefix))) {
    return true;
  }

  const segments = normalized.split("/").filter(Boolean);
  if (segments.some((segment) => APPS_BUILDER_BLOCKED_FILE_PATH_SEGMENTS.includes(segment as (typeof APPS_BUILDER_BLOCKED_FILE_PATH_SEGMENTS)[number]))) {
    return true;
  }
  return false;
}

export function filterAppsBuilderFiles<T extends Record<string, string>>(files: T | Record<string, string> | null | undefined): Record<string, string> {
  const source = files || {};
  const filtered: Record<string, string> = {};
  for (const [rawPath, rawContent] of Object.entries(source)) {
    const normalizedPath = normalizeBuilderFilePath(rawPath);
    if (!normalizedPath || isAppsBuilderBlockedFilePath(normalizedPath)) {
      continue;
    }
    filtered[normalizedPath] = typeof rawContent === "string" ? rawContent : String(rawContent);
  }
  return filtered;
}
