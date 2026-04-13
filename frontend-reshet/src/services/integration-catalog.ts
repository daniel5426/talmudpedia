import type { McpAuthMode } from "./mcp";

export type IntegrationCategory =
  | "productivity"
  | "dev_tools"
  | "communication"
  | "data"
  | "design";

export interface IntegrationCatalogEntry {
  slug: string;
  name: string;
  description: string;
  category: IntegrationCategory;
  server_url: string;
  auth_mode: McpAuthMode;
  default_scopes?: string[];
  requires_user_oauth: boolean;
  /** Inline SVG viewBox content (rendered inside a 24×24 viewBox) */
  icon_svg: string;
  /** Brand accent color for the card highlight */
  accent: string;
}

export const INTEGRATION_CATEGORY_LABELS: Record<
  IntegrationCategory,
  { title: string; description: string }
> = {
  productivity: {
    title: "Productivity",
    description: "Email, docs, calendars, and project management.",
  },
  dev_tools: {
    title: "Developer Tools",
    description: "Source control, issue tracking, and observability.",
  },
  communication: {
    title: "Communication",
    description: "Team chat, messaging, and notifications.",
  },
  data: {
    title: "Data & Storage",
    description: "Databases, warehouses, and file storage.",
  },
  design: {
    title: "Design",
    description: "Design tools and creative platforms.",
  },
};

export const INTEGRATION_CATALOG: IntegrationCatalogEntry[] = [
  // ── Productivity ──────────────────────────────────────────────────
  {
    slug: "notion",
    name: "Notion",
    description: "Read and write pages, databases, and blocks.",
    category: "productivity",
    server_url: "https://mcp.notion.com/mcp",
    auth_mode: "oauth_user_account",
    requires_user_oauth: true,
    accent: "#000000",
    icon_svg: `<path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L18.29 2.09c-.466-.373-.98-.746-2.055-.653L3.459 2.57c-.466.046-.56.28-.374.466zM5.252 7.5v14.367c0 .793.373 1.073 1.213 1.026l14.515-.84c.84-.046.933-.56.933-1.166V6.753c0-.606-.233-.886-.746-.84l-15.17.886c-.56.047-.746.327-.746.7zm14.328.746c.093.42 0 .84-.42.886l-.7.14v10.633c-.606.327-1.166.513-1.633.513-.746 0-.933-.233-1.493-.933l-4.574-7.186v6.953l1.446.327s0 .84-1.166.84l-3.22.186c-.093-.186 0-.653.327-.746l.84-.233V9.854l-1.166-.093c-.093-.42.14-1.026.793-1.073l3.46-.233 4.76 7.28v-6.44l-1.213-.14c-.093-.513.28-.886.746-.933z" fill="currentColor"/>`,
  },
  {
    slug: "airtable",
    name: "Airtable",
    description: "Query and update records in Airtable bases.",
    category: "productivity",
    server_url: "https://mcp.airtable.com/mcp",
    auth_mode: "oauth_user_account",
    requires_user_oauth: true,
    accent: "#18BFFF",
    icon_svg: `<path d="M11.52 2.386l-8.22 3.12a.96.96 0 00-.02 1.788l8.34 3.26a2.4 2.4 0 001.76 0l8.34-3.26a.96.96 0 00-.02-1.788l-8.22-3.12a2.4 2.4 0 00-1.96 0zM20.4 8.88L12 12.24 3.6 8.88v1.56l8.04 3.48a.96.96 0 00.72 0l8.04-3.48V8.88zM20.4 13.44L12 16.8l-8.4-3.36v1.56l8.04 3.48a.96.96 0 00.72 0l8.04-3.48v-1.56z" fill="currentColor"/>`,
  },

  // ── Developer Tools ───────────────────────────────────────────────
  {
    slug: "github",
    name: "GitHub",
    description: "Manage repos, issues, PRs, and code search.",
    category: "dev_tools",
    server_url: "https://api.githubcopilot.com/mcp",
    auth_mode: "oauth_user_account",
    default_scopes: ["repo", "read:org"],
    requires_user_oauth: true,
    accent: "#24292F",
    icon_svg: `<path d="M12 2A10 10 0 002 12c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0012 2z" fill="currentColor"/>`,
  },
  {
    slug: "linear",
    name: "Linear",
    description: "Create and query issues, projects, and cycles.",
    category: "dev_tools",
    server_url: "https://mcp.linear.app/mcp",
    auth_mode: "oauth_user_account",
    requires_user_oauth: true,
    accent: "#5E6AD2",
    icon_svg: `<path d="M3.357 14.098a.3.3 0 01-.08-.325 9.537 9.537 0 012.24-3.54L12 3.75l6.483 6.483a9.537 9.537 0 012.24 3.54.3.3 0 01-.08.325l-3.386 3.386a.3.3 0 01-.419.012A6.588 6.588 0 0012 15.75a6.588 6.588 0 00-4.839 1.746.3.3 0 01-.418-.012z" fill="currentColor"/>`,
  },
  {
    slug: "sentry",
    name: "Sentry",
    description: "Query errors, events, and performance data.",
    category: "dev_tools",
    server_url: "https://mcp.sentry.dev/mcp",
    auth_mode: "oauth_user_account",
    requires_user_oauth: true,
    accent: "#362D59",
    icon_svg: `<path d="M13.96 2.32a1.87 1.87 0 00-3.22 0L7.6 8a10.2 10.2 0 015.5 8.84h-1.87a8.33 8.33 0 00-4.47-7.33l-2.7 4.68A3.87 3.87 0 006.1 18.7h1.87a2 2 0 01-1.12-3.22l1.24-2.15A6.45 6.45 0 0111.36 18.84h3.75a12.06 12.06 0 00-5.97-11.41l1.16-2a14.03 14.03 0 017 13.41h1.87a1.04 1.04 0 00.96-.56l1.42-2.46a1.87 1.87 0 000-1.87z" fill="currentColor"/>`,
  },
  {
    slug: "gitlab",
    name: "GitLab",
    description: "Manage merge requests, issues, and CI/CD pipelines.",
    category: "dev_tools",
    server_url: "https://gitlab.com/api/v4/mcp",
    auth_mode: "oauth_user_account",
    requires_user_oauth: true,
    accent: "#FC6D26",
    icon_svg: `<path d="M12 21.35l-7.19-5.5a1.31 1.31 0 01-.48-1.47L5.6 10.6l1.64-5.05a.66.66 0 011.24 0L10.12 10.6h3.76l1.64-5.05a.66.66 0 011.24 0L18.4 10.6l1.27 3.78a1.31 1.31 0 01-.48 1.47z" fill="currentColor"/>`,
  },

  // ── Communication ─────────────────────────────────────────────────
  {
    slug: "slack",
    name: "Slack",
    description: "Send messages, query channels, and manage threads.",
    category: "communication",
    server_url: "https://mcp.slack.com/mcp",
    auth_mode: "oauth_user_account",
    default_scopes: ["chat:write", "channels:read", "channels:history"],
    requires_user_oauth: true,
    accent: "#4A154B",
    icon_svg: `<path d="M5.042 15.165a2.528 2.528 0 01-2.52 2.523A2.528 2.528 0 010 15.165a2.527 2.527 0 012.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 012.521-2.52 2.527 2.527 0 012.521 2.52v6.313A2.528 2.528 0 018.834 24a2.528 2.528 0 01-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 01-2.521-2.52A2.528 2.528 0 018.834 0a2.528 2.528 0 012.521 2.522v2.52H8.834zm0 1.271a2.528 2.528 0 012.521 2.521 2.528 2.528 0 01-2.521 2.521H2.522A2.528 2.528 0 010 8.834a2.528 2.528 0 012.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 012.522-2.521A2.528 2.528 0 0124 8.834a2.528 2.528 0 01-2.522 2.521h-2.522V8.834zm-1.27 0a2.528 2.528 0 01-2.523 2.521 2.527 2.527 0 01-2.52-2.521V2.522A2.527 2.527 0 0115.163 0a2.528 2.528 0 012.523 2.522v6.312zM15.163 18.956a2.528 2.528 0 012.523 2.522A2.528 2.528 0 0115.163 24a2.527 2.527 0 01-2.52-2.522v-2.522h2.52zm0-1.27a2.527 2.527 0 01-2.52-2.523 2.527 2.527 0 012.52-2.52h6.315A2.528 2.528 0 0124 15.163a2.528 2.528 0 01-2.522 2.523h-6.315z" fill="currentColor"/>`,
  },

  // ── Design ────────────────────────────────────────────────────────
  {
    slug: "figma",
    name: "Figma",
    description: "Access design files, components, and styles.",
    category: "design",
    server_url: "https://mcp.figma.com/mcp",
    auth_mode: "oauth_user_account",
    requires_user_oauth: true,
    accent: "#F24E1E",
    icon_svg: `<path d="M5 5.5A3.5 3.5 0 018.5 2H12v7H8.5A3.5 3.5 0 015 5.5zM5 12a3.5 3.5 0 013.5-3.5H12V12h.5H12v3.5H8.5A3.5 3.5 0 015 12zm0 6.5A3.5 3.5 0 018.5 15H12v3.5a3.5 3.5 0 01-7 0zM12 2h3.5a3.5 3.5 0 110 7H12V2zm0 7h3.5a3.5 3.5 0 110 7H15.5h.039A3.5 3.5 0 0112 12.5V9z" fill="currentColor"/>`,
  },
];

export const INTEGRATION_CATEGORIES: IntegrationCategory[] = [
  "productivity",
  "dev_tools",
  "communication",
  "data",
  "design",
];

type CatalogServerLike = {
  id: string;
  server_url: string;
  is_active?: boolean;
  sync_status?: string;
  tool_snapshot_version?: number;
  updated_at?: string;
};

export function findCatalogEntry(
  slug: string
): IntegrationCatalogEntry | undefined {
  return INTEGRATION_CATALOG.find((entry) => entry.slug === slug);
}

export function getCatalogEntriesByCategory(
  category: IntegrationCategory
): IntegrationCatalogEntry[] {
  return INTEGRATION_CATALOG.filter((entry) => entry.category === category);
}

export function normalizeCatalogServerUrl(serverUrl: string): string {
  return String(serverUrl || "").replace(/\/+$/, "").trim().toLowerCase();
}

function getCatalogHostname(serverUrl: string): string | null {
  try {
    return new URL(serverUrl).hostname.toLowerCase();
  } catch {
    return null;
  }
}

/**
 * Match a configured McpServer to a catalog entry by URL prefix.
 * Returns the entry slug or null if it's a custom (unlisted) server.
 */
export function matchServerToCatalog(
  serverUrl: string
): IntegrationCatalogEntry | null {
  const normalized = normalizeCatalogServerUrl(serverUrl);
  const directMatch =
    INTEGRATION_CATALOG.find((entry) =>
      normalized.startsWith(normalizeCatalogServerUrl(entry.server_url))
    ) ?? null;
  if (directMatch) return directMatch;

  const hostname = getCatalogHostname(serverUrl);
  if (!hostname) return null;

  const hostnameMatches = INTEGRATION_CATALOG.filter(
    (entry) => getCatalogHostname(entry.server_url) === hostname
  );
  return hostnameMatches.length === 1 ? hostnameMatches[0] : null;
}

export function pickPreferredCatalogServer<T extends CatalogServerLike>(
  entry: IntegrationCatalogEntry,
  servers: T[],
  options?: { connectedServerIds?: ReadonlySet<string> }
): T | null {
  if (servers.length === 0) return null;
  const connectedServerIds = options?.connectedServerIds;
  const targetUrl = normalizeCatalogServerUrl(entry.server_url);

  const ranked = [...servers].sort((left, right) => {
    const leftScore =
      (normalizeCatalogServerUrl(left.server_url) === targetUrl ? 1000 : 0) +
      (connectedServerIds?.has(left.id) ? 200 : 0) +
      (left.sync_status === "ready" ? 100 : 0) +
      (left.is_active === false ? -50 : 0) +
      Math.min(left.tool_snapshot_version ?? 0, 50);
    const rightScore =
      (normalizeCatalogServerUrl(right.server_url) === targetUrl ? 1000 : 0) +
      (connectedServerIds?.has(right.id) ? 200 : 0) +
      (right.sync_status === "ready" ? 100 : 0) +
      (right.is_active === false ? -50 : 0) +
      Math.min(right.tool_snapshot_version ?? 0, 50);
    if (leftScore !== rightScore) return rightScore - leftScore;

    const leftUpdated = Date.parse(left.updated_at ?? "") || 0;
    const rightUpdated = Date.parse(right.updated_at ?? "") || 0;
    if (leftUpdated !== rightUpdated) return rightUpdated - leftUpdated;

    return left.id.localeCompare(right.id);
  });

  return ranked[0] ?? null;
}
