"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Link2, Loader2, PlugZap, RefreshCw, Shield, Unplug } from "lucide-react";

import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { formatHttpErrorMessage } from "@/services/http";
import {
  CreateMcpServerRequest,
  McpAccountConnection,
  McpAuthMode,
  McpDiscoveredTool,
  McpServer,
  mcpService,
} from "@/services";

type FormState = {
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

const INITIAL_FORM: FormState = {
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
    Object.entries(parsed).map(([key, value]) => [String(key), String(value)]),
  );
}

export default function McpSettingsPage() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [toolsByServer, setToolsByServer] = useState<Record<string, McpDiscoveredTool[]>>({});
  const [connectionsByServer, setConnectionsByServer] = useState<Record<string, McpAccountConnection | null>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [activeServerId, setActiveServerId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(INITIAL_FORM);

  const activeServer = useMemo(
    () => servers.find((server) => server.id === activeServerId) ?? null,
    [activeServerId, servers],
  );

  const loadServers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const serverList = await mcpService.listServers();
      setServers(serverList);
      setActiveServerId((current) => current ?? serverList[0]?.id ?? null);
      const connectionEntries = await Promise.all(
        serverList.map(async (server) => [server.id, await mcpService.getMyConnection(server.id)] as const),
      );
      setConnectionsByServer(Object.fromEntries(connectionEntries));
    } catch (err) {
      setError(formatHttpErrorMessage(err, "Failed to load MCP servers."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadServers();
  }, [loadServers]);

  useEffect(() => {
    function onMessage(event: MessageEvent) {
      if (event.data?.type !== "mcp-oauth-complete") return;
      loadServers();
      if (activeServerId) {
        void loadTools(activeServerId);
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [activeServerId, loadServers, loadTools]);

  const loadTools = useCallback(async (serverId: string) => {
    try {
      const tools = await mcpService.listTools(serverId);
      setToolsByServer((current) => ({ ...current, [serverId]: tools }));
    } catch (err) {
      setError(formatHttpErrorMessage(err, "Failed to load discovered tools."));
    }
  }, []);

  async function handleCreateServer() {
    setSubmitting(true);
    setError(null);
    try {
      const payload: CreateMcpServerRequest = {
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        server_url: form.server_url.trim(),
        auth_mode: form.auth_mode,
        static_bearer_token: form.static_bearer_token.trim() || undefined,
        static_headers: parseHeaders(form.static_headers),
        auth_config: form.scopes.trim()
          ? { scopes: form.scopes.split(",").map((item) => item.trim()).filter(Boolean) }
          : undefined,
        oauth_client_id: form.oauth_client_id.trim() || undefined,
        oauth_client_secret: form.oauth_client_secret.trim() || undefined,
      };
      const server = await mcpService.createServer(payload);
      setForm(INITIAL_FORM);
      await loadServers();
      setActiveServerId(server.id);
    } catch (err) {
      setError(formatHttpErrorMessage(err, "Failed to create MCP server."));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTest(serverId: string) {
    setError(null);
    try {
      await mcpService.testServer(serverId);
      await loadServers();
    } catch (err) {
      setError(formatHttpErrorMessage(err, "Failed to test MCP server."));
    }
  }

  async function handleSync(serverId: string) {
    setError(null);
    try {
      await mcpService.syncServer(serverId);
      await loadServers();
      await loadTools(serverId);
    } catch (err) {
      setError(formatHttpErrorMessage(err, "Failed to sync MCP server."));
    }
  }

  async function handleConnect(serverId: string) {
    setError(null);
    try {
      const result = await mcpService.startAuth(serverId);
      window.open(result.authorization_url, "_blank", "noopener,noreferrer,width=760,height=820");
    } catch (err) {
      setError(formatHttpErrorMessage(err, "Failed to start MCP OAuth flow."));
    }
  }

  async function handleDisconnect(serverId: string) {
    setError(null);
    try {
      await mcpService.disconnectMyConnection(serverId);
      await loadServers();
    } catch (err) {
      setError(formatHttpErrorMessage(err, "Failed to disconnect MCP account."));
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 py-6">
      <div className="flex items-center justify-between gap-4">
        <div className="space-y-2">
          <CustomBreadcrumb
            items={[
              { label: "Settings", href: "/admin/settings" },
              { label: "MCP Servers", active: true },
            ]}
          />
          <h1 className="text-2xl font-semibold tracking-tight">MCP Servers</h1>
          <p className="text-sm text-muted-foreground">
            Create tenant MCP servers, test discovery, and connect your own account when the server requires user OAuth.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/admin/settings">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Settings
          </Link>
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="rounded-xl border border-border/60 bg-background p-5">
          <div className="mb-4">
            <h2 className="text-sm font-semibold">New MCP Server</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Streamable HTTP only for now. OAuth is handled per user when needed.
            </p>
          </div>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
            </div>
            <div className="space-y-2">
              <Label>Server URL</Label>
              <Input
                placeholder="https://mcp.example.com/mcp"
                value={form.server_url}
                onChange={(event) => setForm((current) => ({ ...current, server_url: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Auth Mode</Label>
              <Select value={form.auth_mode} onValueChange={(value: McpAuthMode) => setForm((current) => ({ ...current, auth_mode: value }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  <SelectItem value="static_bearer">Static bearer</SelectItem>
                  <SelectItem value="static_headers">Static headers</SelectItem>
                  <SelectItem value="oauth_user_account">OAuth user account</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} />
            </div>

            {form.auth_mode === "static_bearer" && (
              <div className="space-y-2">
                <Label>Bearer Token</Label>
                <Input
                  type="password"
                  value={form.static_bearer_token}
                  onChange={(event) => setForm((current) => ({ ...current, static_bearer_token: event.target.value }))}
                />
              </div>
            )}

            {form.auth_mode === "static_headers" && (
              <div className="space-y-2">
                <Label>Static Headers JSON</Label>
                <Textarea
                  placeholder='{"Authorization":"Bearer ..."}'
                  value={form.static_headers}
                  onChange={(event) => setForm((current) => ({ ...current, static_headers: event.target.value }))}
                />
              </div>
            )}

            {form.auth_mode === "oauth_user_account" && (
              <>
                <div className="space-y-2">
                  <Label>Scopes</Label>
                  <Input
                    placeholder="mcp:tools, mcp:resources"
                    value={form.scopes}
                    onChange={(event) => setForm((current) => ({ ...current, scopes: event.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>OAuth Client ID</Label>
                  <Input value={form.oauth_client_id} onChange={(event) => setForm((current) => ({ ...current, oauth_client_id: event.target.value }))} />
                </div>
                <div className="space-y-2">
                  <Label>OAuth Client Secret</Label>
                  <Input
                    type="password"
                    value={form.oauth_client_secret}
                    onChange={(event) => setForm((current) => ({ ...current, oauth_client_secret: event.target.value }))}
                  />
                </div>
              </>
            )}

            <Button className="w-full" onClick={handleCreateServer} disabled={submitting}>
              {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlugZap className="mr-2 h-4 w-4" />}
              Create Server
            </Button>
          </div>
        </div>

        <div className="rounded-xl border border-border/60 bg-background">
          <div className="border-b border-border/50 px-5 py-4">
            <h2 className="text-sm font-semibold">Configured Servers</h2>
          </div>

          {loading ? (
            <div className="flex items-center justify-center px-6 py-16 text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Loading MCP servers...
            </div>
          ) : servers.length === 0 ? (
            <div className="px-6 py-16 text-center text-sm text-muted-foreground">
              No MCP servers configured yet.
            </div>
          ) : (
            <div className="grid gap-0 lg:grid-cols-[280px_minmax(0,1fr)]">
              <div className="border-r border-border/50">
                {servers.map((server) => (
                  <button
                    key={server.id}
                    type="button"
                    onClick={() => {
                      setActiveServerId(server.id);
                      if (!toolsByServer[server.id] && server.tool_snapshot_version > 0) {
                        void loadTools(server.id);
                      }
                    }}
                    className={`flex w-full flex-col items-start gap-2 px-4 py-4 text-left transition-colors ${
                      activeServerId === server.id ? "bg-muted/50" : "hover:bg-muted/30"
                    }`}
                  >
                    <div className="flex w-full items-center justify-between gap-3">
                      <span className="font-medium">{server.name}</span>
                      <Badge variant={server.sync_status === "ready" ? "default" : "outline"}>{server.sync_status}</Badge>
                    </div>
                    <div className="text-xs text-muted-foreground">{server.server_url}</div>
                    <div className="flex gap-2 text-[11px] text-muted-foreground">
                      <span>{server.auth_mode}</span>
                      <span>snapshot {server.tool_snapshot_version}</span>
                    </div>
                  </button>
                ))}
              </div>

              <div className="min-h-[480px] px-5 py-5">
                {activeServer ? (
                  <div className="space-y-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <h3 className="text-lg font-semibold">{activeServer.name}</h3>
                          <Badge variant="outline">{activeServer.auth_mode}</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">{activeServer.server_url}</p>
                        {activeServer.description && <p className="text-sm text-muted-foreground">{activeServer.description}</p>}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button variant="outline" onClick={() => handleTest(activeServer.id)}>
                          <Shield className="mr-2 h-4 w-4" />
                          Test
                        </Button>
                        <Button variant="outline" onClick={() => handleSync(activeServer.id)}>
                          <RefreshCw className="mr-2 h-4 w-4" />
                          Sync Tools
                        </Button>
                        {activeServer.auth_mode === "oauth_user_account" &&
                          (connectionsByServer[activeServer.id] ? (
                            <Button variant="outline" onClick={() => handleDisconnect(activeServer.id)}>
                              <Unplug className="mr-2 h-4 w-4" />
                              Disconnect Account
                            </Button>
                          ) : (
                            <Button onClick={() => handleConnect(activeServer.id)}>
                              <Link2 className="mr-2 h-4 w-4" />
                              Connect Account
                            </Button>
                          ))}
                      </div>
                    </div>

                    {activeServer.auth_mode === "oauth_user_account" && (
                      <div className="rounded-lg border border-border/60 bg-muted/20 px-4 py-3 text-sm">
                        <div className="font-medium">My linked account</div>
                        <div className="mt-1 text-muted-foreground">
                          {connectionsByServer[activeServer.id]
                            ? `Status: ${connectionsByServer[activeServer.id]?.status}`
                            : "No account connected yet."}
                        </div>
                      </div>
                    )}

                    <div className="rounded-lg border border-border/60">
                      <div className="border-b border-border/50 px-4 py-3">
                        <div className="text-sm font-medium">Discovered tools</div>
                        <div className="text-xs text-muted-foreground">
                          Mounted agents stay pinned to the snapshot you explicitly apply.
                        </div>
                      </div>
                      <div className="divide-y divide-border/40">
                        {(toolsByServer[activeServer.id] ?? []).length === 0 ? (
                          <div className="px-4 py-8 text-sm text-muted-foreground">
                            {activeServer.tool_snapshot_version > 0
                              ? "No tools loaded in the UI yet. Sync again if the snapshot changed."
                              : "No synced tool snapshot yet."}
                          </div>
                        ) : (
                          (toolsByServer[activeServer.id] ?? []).map((tool) => (
                            <div key={tool.id} className="px-4 py-3">
                              <div className="font-medium">{tool.title || tool.name}</div>
                              {tool.description && <div className="mt-1 text-sm text-muted-foreground">{tool.description}</div>}
                              <div className="mt-2 text-[11px] text-muted-foreground">name: {tool.name}</div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    Select a server to inspect it.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
