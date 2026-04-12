"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Layers,
  Loader2,
  PlugZap,
  Settings2,
  Target,
  X,
} from "lucide-react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SearchInput } from "@/components/ui/search-input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { formatHttpErrorMessage } from "@/services/http";
import {
  CreateMcpServerRequest,
  McpAccountConnection,
  McpAuthMode,
  McpDiscoveredTool,
  McpServer,
  mcpService,
} from "@/services";
import {
  INTEGRATION_CATALOG,
  INTEGRATION_CATEGORIES,
  INTEGRATION_CATEGORY_LABELS,
  matchServerToCatalog,
  type IntegrationCatalogEntry,
  type IntegrationCategory,
} from "@/services/integration-catalog";
import {
  IntegrationCard,
  ConnectedIntegrationCard,
} from "./IntegrationCard";

// ── Custom server form state ─────────────────────────────────────────────────

type CustomFormState = {
  name: string;
  description: string;
  server_url: string;
  auth_mode: McpAuthMode;
  scopes: string;
  static_bearer_token: string;
  static_headers: string;
  oauth_client_id: string;
  oauth_client_secret: string;
};

const INITIAL_CUSTOM_FORM: CustomFormState = {
  name: "",
  description: "",
  server_url: "",
  auth_mode: "none",
  scopes: "",
  static_bearer_token: "",
  static_headers: "",
  oauth_client_id: "",
  oauth_client_secret: "",
};

function parseHeaders(raw: string): Record<string, string> | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Static headers must be a JSON object.");
  }
  return Object.fromEntries(
    Object.entries(parsed).map(([key, value]) => [String(key), String(value)])
  );
}

// ── Loading skeleton ─────────────────────────────────────────────────────────

function CatalogSkeleton() {
  return (
    <div className="space-y-8 px-6 py-6">
      {[1, 2].map((section) => (
        <div key={section}>
          <Skeleton className="h-4 w-32 mb-4" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="rounded-xl border border-border/40 p-4 space-y-3"
              >
                <div className="flex items-start gap-3">
                  <Skeleton className="h-11 w-11 rounded-xl shrink-0" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-3 w-full" />
                  </div>
                </div>
                <div className="flex justify-end pt-2 border-t border-border/30">
                  <Skeleton className="h-7 w-16 rounded-md" />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function McpSettingsPage() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [toolsByServer, setToolsByServer] = useState<
    Record<string, McpDiscoveredTool[]>
  >({});
  const [connectionsByServer, setConnectionsByServer] = useState<
    Record<string, McpAccountConnection | null>
  >({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Custom server sheet
  const [customSheetOpen, setCustomSheetOpen] = useState(false);
  const [customForm, setCustomForm] =
    useState<CustomFormState>(INITIAL_CUSTOM_FORM);
  const [customSubmitting, setCustomSubmitting] = useState(false);

  // Search
  const [searchQuery, setSearchQuery] = useState("");

  // ── Data loading ─────────────────────────────────────────────────

  const loadServers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const serverList = await mcpService.listServers();
      setServers(serverList);
      const connectionEntries = await Promise.all(
        serverList.map(
          async (server) =>
            [server.id, await mcpService.getMyConnection(server.id)] as const
        )
      );
      setConnectionsByServer(Object.fromEntries(connectionEntries));
    } catch (err) {
      setError(formatHttpErrorMessage(err, "Failed to load integrations."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadServers();
  }, [loadServers]);

  // Listen for OAuth popup callback
  useEffect(() => {
    function onMessage(event: MessageEvent) {
      if (event.data?.type !== "mcp-oauth-complete") return;
      loadServers();
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [loadServers]);

  // ── Server ↔ catalog matching ────────────────────────────────────

  const serverByCatalogSlug = useMemo(() => {
    const map: Record<string, McpServer> = {};
    for (const server of servers) {
      const entry = matchServerToCatalog(server.server_url);
      if (entry) {
        map[entry.slug] = server;
      }
    }
    return map;
  }, [servers]);

  const connectedServers = useMemo(() => {
    return servers.filter((s) => s.is_active);
  }, [servers]);

  // Servers that don't match any catalog entry (truly custom)
  const customServers = useMemo(() => {
    return servers.filter((s) => !matchServerToCatalog(s.server_url));
  }, [servers]);

  const connectedCount = connectedServers.length;

  // ── Search filtering ─────────────────────────────────────────────

  const filteredCatalog = useMemo(() => {
    if (!searchQuery.trim()) return INTEGRATION_CATALOG;
    const q = searchQuery.toLowerCase();
    return INTEGRATION_CATALOG.filter(
      (entry) =>
        entry.name.toLowerCase().includes(q) ||
        entry.description.toLowerCase().includes(q) ||
        entry.category.toLowerCase().includes(q)
    );
  }, [searchQuery]);

  const filteredByCategory = useMemo(() => {
    const groups: Record<IntegrationCategory, IntegrationCatalogEntry[]> = {
      productivity: [],
      dev_tools: [],
      communication: [],
      data: [],
      design: [],
    };
    for (const entry of filteredCatalog) {
      groups[entry.category].push(entry);
    }
    return groups;
  }, [filteredCatalog]);

  // ── Actions ──────────────────────────────────────────────────────

  async function handleAddFromCatalog(
    entry: IntegrationCatalogEntry
  ): Promise<void> {
    setError(null);
    try {
      const payload: CreateMcpServerRequest = {
        name: entry.name,
        description: entry.description,
        server_url: entry.server_url,
        auth_mode: entry.auth_mode,
        auth_config: entry.default_scopes
          ? { scopes: entry.default_scopes }
          : undefined,
      };
      const server = await mcpService.createServer(payload);

      // Test the server
      try {
        await mcpService.testServer(server.id);
      } catch {
        // Test may fail — that's OK, we still created the server
      }

      // If no OAuth needed, sync immediately
      if (!entry.requires_user_oauth) {
        try {
          await mcpService.syncServer(server.id);
        } catch {
          // Sync may fail — user can retry
        }
      }

      await loadServers();

      // If OAuth needed, start auth flow automatically
      if (entry.requires_user_oauth) {
        try {
          const result = await mcpService.startAuth(server.id);
          window.open(
            result.authorization_url,
            "_blank",
            "noopener,noreferrer,width=760,height=820"
          );
        } catch {
          // Auth start may fail — user can retry from the card
        }
      }
    } catch (err) {
      setError(formatHttpErrorMessage(err, `Failed to add ${entry.name}.`));
    }
  }

  async function handleConnect(serverId: string): Promise<void> {
    setError(null);
    try {
      const result = await mcpService.startAuth(serverId);
      window.open(
        result.authorization_url,
        "_blank",
        "noopener,noreferrer,width=760,height=820"
      );
    } catch (err) {
      setError(formatHttpErrorMessage(err, "Failed to start OAuth flow."));
    }
  }

  async function handleDisconnect(serverId: string): Promise<void> {
    setError(null);
    try {
      await mcpService.disconnectMyConnection(serverId);
      await loadServers();
    } catch (err) {
      setError(
        formatHttpErrorMessage(err, "Failed to disconnect account.")
      );
    }
  }

  async function handleSync(serverId: string): Promise<void> {
    setError(null);
    try {
      await mcpService.syncServer(serverId);
      await loadServers();
      const tools = await mcpService.listTools(serverId);
      setToolsByServer((current) => ({ ...current, [serverId]: tools }));
    } catch (err) {
      setError(
        formatHttpErrorMessage(err, "Failed to sync tools.")
      );
    }
  }

  async function handleCreateCustomServer(): Promise<void> {
    setCustomSubmitting(true);
    setError(null);
    try {
      const payload: CreateMcpServerRequest = {
        name: customForm.name.trim(),
        description: customForm.description.trim() || undefined,
        server_url: customForm.server_url.trim(),
        auth_mode: customForm.auth_mode,
        static_bearer_token:
          customForm.static_bearer_token.trim() || undefined,
        static_headers: parseHeaders(customForm.static_headers),
        auth_config: customForm.scopes.trim()
          ? {
              scopes: customForm.scopes
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
            }
          : undefined,
        oauth_client_id: customForm.oauth_client_id.trim() || undefined,
        oauth_client_secret:
          customForm.oauth_client_secret.trim() || undefined,
      };
      await mcpService.createServer(payload);
      setCustomForm(INITIAL_CUSTOM_FORM);
      setCustomSheetOpen(false);
      await loadServers();
    } catch (err) {
      setError(
        formatHttpErrorMessage(err, "Failed to create custom server.")
      );
    } finally {
      setCustomSubmitting(false);
    }
  }

  // ── Render: All tab grid ─────────────────────────────────────────

  function renderAllTab() {
    return (
      <div className="space-y-8">
        {INTEGRATION_CATEGORIES.map((category) => {
          const entries = filteredByCategory[category];
          if (entries.length === 0) return null;
          const categoryInfo = INTEGRATION_CATEGORY_LABELS[category];
          return (
            <section key={category}>
              <div className="mb-3">
                <h2 className="text-sm font-semibold text-foreground">
                  {categoryInfo.title}
                </h2>
                <p className="text-xs text-muted-foreground/60 mt-0.5">
                  {categoryInfo.description}
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {entries.map((entry) => (
                  <IntegrationCard
                    key={entry.slug}
                    entry={entry}
                    server={serverByCatalogSlug[entry.slug] ?? null}
                    connection={
                      serverByCatalogSlug[entry.slug]
                        ? connectionsByServer[
                            serverByCatalogSlug[entry.slug].id
                          ] ?? null
                        : null
                    }
                    onAdd={handleAddFromCatalog}
                    onConnect={handleConnect}
                    onDisconnect={handleDisconnect}
                    onSync={handleSync}
                  />
                ))}
              </div>
            </section>
          );
        })}

        {filteredCatalog.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Search className="h-8 w-8 text-muted-foreground/30 mb-3" />
            <p className="text-sm font-medium text-muted-foreground">
              No integrations found
            </p>
            <p className="text-xs text-muted-foreground/60 mt-1">
              Try a different search term
            </p>
          </div>
        )}
      </div>
    );
  }

  // ── Render: Connected tab ────────────────────────────────────────

  function renderConnectedTab() {
    if (connectedServers.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <PlugZap className="h-8 w-8 text-muted-foreground/30 mb-3" />
          <p className="text-sm font-medium text-muted-foreground">
            No integrations connected yet
          </p>
          <p className="text-xs text-muted-foreground/60 mt-1">
            Switch to the &quot;All&quot; tab to browse and add integrations
          </p>
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {connectedServers.map((server) => {
          const catalogEntry = matchServerToCatalog(server.server_url);
          const serverTools = toolsByServer[server.id] ?? [];
          return (
            <ConnectedIntegrationCard
              key={server.id}
              entry={catalogEntry}
              server={server}
              connection={connectionsByServer[server.id] ?? null}
              toolCount={serverTools.length}
              onConnect={handleConnect}
              onDisconnect={handleDisconnect}
              onSync={handleSync}
            />
          );
        })}
      </div>
    );
  }

  // ── Render: Custom server sheet ──────────────────────────────────

  function renderCustomServerSheet() {
    return (
      <Sheet open={customSheetOpen} onOpenChange={setCustomSheetOpen}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-md flex flex-col p-0 gap-0 overflow-y-auto"
        >
          <SheetHeader className="px-5 pt-5 pb-4 border-b space-y-0">
            <SheetTitle className="text-base">Custom MCP Server</SheetTitle>
            <SheetDescription className="text-xs mt-0.5">
              Add an unlisted MCP server by providing the URL and auth
              configuration manually.
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 px-5 py-5 space-y-4 overflow-y-auto">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input
                value={customForm.name}
                onChange={(event) =>
                  setCustomForm((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
                className="h-9"
              />
            </div>
            <div className="space-y-2">
              <Label>Server URL</Label>
              <Input
                placeholder="https://mcp.example.com/mcp"
                value={customForm.server_url}
                onChange={(event) =>
                  setCustomForm((current) => ({
                    ...current,
                    server_url: event.target.value,
                  }))
                }
                className="h-9"
              />
            </div>
            <div className="space-y-2">
              <Label>Auth Mode</Label>
              <Select
                value={customForm.auth_mode}
                onValueChange={(value: McpAuthMode) =>
                  setCustomForm((current) => ({
                    ...current,
                    auth_mode: value,
                  }))
                }
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  <SelectItem value="static_bearer">Static bearer</SelectItem>
                  <SelectItem value="static_headers">
                    Static headers
                  </SelectItem>
                  <SelectItem value="oauth_user_account">
                    OAuth user account
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea
                value={customForm.description}
                onChange={(event) =>
                  setCustomForm((current) => ({
                    ...current,
                    description: event.target.value,
                  }))
                }
                className="min-h-[60px]"
              />
            </div>

            {customForm.auth_mode === "static_bearer" && (
              <div className="space-y-2">
                <Label>Bearer Token</Label>
                <Input
                  type="password"
                  value={customForm.static_bearer_token}
                  onChange={(event) =>
                    setCustomForm((current) => ({
                      ...current,
                      static_bearer_token: event.target.value,
                    }))
                  }
                  className="h-9"
                />
              </div>
            )}

            {customForm.auth_mode === "static_headers" && (
              <div className="space-y-2">
                <Label>Static Headers JSON</Label>
                <Textarea
                  placeholder='{"Authorization":"Bearer ..."}'
                  value={customForm.static_headers}
                  onChange={(event) =>
                    setCustomForm((current) => ({
                      ...current,
                      static_headers: event.target.value,
                    }))
                  }
                />
              </div>
            )}

            {customForm.auth_mode === "oauth_user_account" && (
              <>
                <div className="space-y-2">
                  <Label>Scopes</Label>
                  <Input
                    placeholder="mcp:tools, mcp:resources"
                    value={customForm.scopes}
                    onChange={(event) =>
                      setCustomForm((current) => ({
                        ...current,
                        scopes: event.target.value,
                      }))
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-2">
                  <Label>OAuth Client ID</Label>
                  <Input
                    value={customForm.oauth_client_id}
                    onChange={(event) =>
                      setCustomForm((current) => ({
                        ...current,
                        oauth_client_id: event.target.value,
                      }))
                    }
                    className="h-9"
                  />
                </div>
                <div className="space-y-2">
                  <Label>OAuth Client Secret</Label>
                  <Input
                    type="password"
                    value={customForm.oauth_client_secret}
                    onChange={(event) =>
                      setCustomForm((current) => ({
                        ...current,
                        oauth_client_secret: event.target.value,
                      }))
                    }
                    className="h-9"
                  />
                </div>
              </>
            )}
          </div>

          <div className="border-t px-5 py-4">
            <Button
              className="w-full"
              onClick={handleCreateCustomServer}
              disabled={
                customSubmitting ||
                !customForm.name.trim() ||
                !customForm.server_url.trim()
              }
            >
              {customSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <PlugZap className="h-4 w-4 mr-2" />
              )}
              Create Server
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <>
      <div className="mx-auto max-w-7xl">
        {/* ── Page title + search + custom server button ── */}
        <div className="mb-6 flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-medium text-foreground">
              MCP Servers
            </h2>
            <p className="text-xs text-muted-foreground/70 mt-0.5">
              Connect external services to supercharge your agents with real-world tools.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs shrink-0"
            onClick={() => setCustomSheetOpen(true)}
          >
            <Settings2 className="h-3.5 w-3.5 mr-1.5" />
            Custom Server
          </Button>
        </div>

          {/* ── Error banner ── */}
          {error && (
            <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {loading ? (
            <CatalogSkeleton />
          ) : (
            <Tabs defaultValue="all" className="gap-0">
              {/* ── Tab bar + search row ── */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
                <SearchInput
                  placeholder="Search integrations..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  wrapperClassName="w-64"
                />

                <TabsList>
                  <TabsTrigger value="all" className="gap-1.5">
                    <Layers className="h-3.5 w-3.5" />
                    All
                  </TabsTrigger>
                  <TabsTrigger value="connected" className="gap-1.5">
                    <Target className="h-3.5 w-3.5" />
                    Connected
                    {connectedCount > 0 && (
                      <span className="ml-1 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-emerald-500/15 px-1 text-[10px] font-medium text-emerald-600">
                        {connectedCount}
                      </span>
                    )}
                  </TabsTrigger>
                </TabsList>
              </div>

              {/* ── Tab content ── */}
              <TabsContent value="all">{renderAllTab()}</TabsContent>
              <TabsContent value="connected">
                {renderConnectedTab()}
              </TabsContent>
            </Tabs>
          )}
        </div>
      {renderCustomServerSheet()}
    </>
  );
}
