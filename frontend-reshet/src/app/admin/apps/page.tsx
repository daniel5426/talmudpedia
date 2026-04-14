"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ExternalLink,
  Globe,
  KeyRound,
  Loader2,
  MoreHorizontal,
  Plus,
  Trash2,
} from "lucide-react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import {
  AppRowStats,
  AppRowStatsEmpty,
  AppRowStatsSkeleton,
} from "@/components/admin/apps/AppRowStats";
import { SearchableResourceInput } from "@/components/shared/SearchableResourceInput";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SearchInput } from "@/components/ui/search-input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { agentService, publishedAppsService } from "@/services";
import type {
  Agent,
  PublishedApp,
  PublishedAppAuthProvider,
  PublishedAppAuthTemplate,
  PublishedAppStatsSummary,
  PublishedAppTemplate,
} from "@/services";

const DEFAULT_PROVIDERS: PublishedAppAuthProvider[] = ["password"];

const STATUS_CONFIG: Record<
  PublishedApp["status"],
  { color: string; label: string }
> = {
  published: { color: "bg-emerald-500", label: "Published" },
  draft: { color: "bg-zinc-400", label: "Draft" },
  paused: { color: "bg-amber-500", label: "Paused" },
  archived: { color: "bg-red-500", label: "Archived" },
};

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 30) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

function AppRowSkeleton() {
  return (
    <div className="flex items-center gap-4 border-b border-border/50 px-4 py-3.5">
      <Skeleton className="h-9 w-9 shrink-0 rounded-lg" />
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-4 w-36" />
        <Skeleton className="h-3 w-24" />
      </div>
      <Skeleton className="hidden h-3 w-16 md:block" />
      <Skeleton className="hidden h-3 w-20 lg:block" />
      <Skeleton className="h-3 w-12" />
    </div>
  );
}

export default function AppsPage() {
  const router = useRouter();
  const [apps, setApps] = useState<PublishedApp[]>([]);
  const [templates, setTemplates] = useState<PublishedAppTemplate[]>([]);
  const [authTemplates, setAuthTemplates] = useState<PublishedAppAuthTemplate[]>([]);
  const [publishedAgents, setPublishedAgents] = useState<Agent[]>([]);
  const [isAppsLoading, setIsAppsLoading] = useState(true);
  const [isCreateResourcesLoading, setIsCreateResourcesLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [appsError, setAppsError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const [statsDays, setStatsDays] = useState(7);
  const [statsMap, setStatsMap] = useState<Map<string, PublishedAppStatsSummary>>(new Map());
  const [isStatsLoading, setIsStatsLoading] = useState(false);
  const [statsApproximate, setStatsApproximate] = useState(false);
  const statsFetchRef = useRef(0);

  const [name, setName] = useState("");
  const [agentId, setAgentId] = useState("");
  const [templateKey, setTemplateKey] = useState("");
  const [authTemplateKey, setAuthTemplateKey] = useState("");
  const [authEnabled, setAuthEnabled] = useState(true);
  const [providerPassword, setProviderPassword] = useState(true);
  const [providerGoogle, setProviderGoogle] = useState(false);

  const filteredApps = useMemo(() => {
    const query = search.toLowerCase().trim();
    if (!query) return apps;
    return apps.filter(
      (app) =>
        app.name.toLowerCase().includes(query) ||
        app.slug.toLowerCase().includes(query)
    );
  }, [apps, search]);

  const agentMap = useMemo(() => {
    const map = new Map<string, Agent>();
    publishedAgents.forEach((agent) => map.set(agent.id, agent));
    return map;
  }, [publishedAgents]);

  async function loadApps() {
    setIsAppsLoading(true);
    setAppsError(null);
    try {
      setApps(await publishedAppsService.list());
    } catch (err) {
      console.error(err);
      setAppsError(err instanceof Error ? err.message : "Failed to load apps");
    } finally {
      setIsAppsLoading(false);
    }
  }

  async function loadCreateResources() {
    setIsCreateResourcesLoading(true);
    setCreateError(null);
    try {
      const [agentsResponse, templatesResponse, authTemplatesResponse] = await Promise.all([
        agentService.listAgents({ limit: 100, view: "summary" }),
        publishedAppsService.listTemplates(),
        publishedAppsService.listAuthTemplates(),
      ]);
      const publishedOnly = agentsResponse.items.filter(
        (agent) => String(agent.status).toLowerCase() === "published"
      );
      setPublishedAgents(publishedOnly);
      setTemplates(templatesResponse);
      setAuthTemplates(authTemplatesResponse);
      setAgentId((prev) => prev || publishedOnly[0]?.id || "");
      setTemplateKey((prev) => prev || templatesResponse[0]?.key || "");
      setAuthTemplateKey((prev) => prev || authTemplatesResponse[0]?.key || "");
    } catch (err) {
      console.error(err);
      setCreateError(err instanceof Error ? err.message : "Failed to load app creation options");
    } finally {
      setIsCreateResourcesLoading(false);
    }
  }

  const loadStats = useCallback(async (days: number) => {
    const fetchId = ++statsFetchRef.current;
    setIsStatsLoading(true);
    try {
      const response = await publishedAppsService.listStats({ days });
      if (fetchId !== statsFetchRef.current) return;
      const next = new Map<string, PublishedAppStatsSummary>();
      for (const item of response.items) {
        next.set(item.app_id, item);
      }
      setStatsMap(next);
      setStatsApproximate(response.items.some((i) => i.approximate));
    } catch {
      if (fetchId !== statsFetchRef.current) return;
      setStatsMap(new Map());
    } finally {
      if (fetchId === statsFetchRef.current) {
        setIsStatsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadApps();
    void loadCreateResources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadStats(statsDays);
  }, [statsDays, loadStats]);

  function resetCreateForm() {
    setName("");
    setTemplateKey((prev) => prev || templates[0]?.key || "");
    setAuthTemplateKey((prev) => prev || authTemplates[0]?.key || "auth-classic");
    setProviderPassword(true);
    setProviderGoogle(false);
    setCreateError(null);
  }

  async function handleCreate() {
    const nextName = name.trim();
    if (!nextName || !agentId || !templateKey || !authTemplateKey) {
      setCreateError("Name, template, auth template, and published agent are required");
      return;
    }

    const providers: PublishedAppAuthProvider[] = [];
    if (providerPassword) providers.push("password");
    if (providerGoogle) providers.push("google");
    if (providers.length === 0) {
      setCreateError("Select at least one auth provider");
      return;
    }

    setIsCreating(true);
    setCreateError(null);
    try {
      const created = await publishedAppsService.create({
        name: nextName,
        agent_id: agentId,
        template_key: templateKey,
        auth_template_key: authTemplateKey,
        auth_enabled: authEnabled,
        auth_providers: providers,
      });
      setApps((prev) => [created, ...prev]);
      resetCreateForm();
      setCreateDialogOpen(false);
      router.push(`/admin/apps/${created.id}`);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create app");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleDelete(appId: string) {
    if (!window.confirm("Delete this app? This action cannot be undone.")) return;
    try {
      await publishedAppsService.remove(appId);
      setApps((prev) => prev.filter((item) => item.id !== appId));
    } catch (err) {
      setAppsError(err instanceof Error ? err.message : "Failed to delete app");
    }
  }

  function appRuntimeHref(app: PublishedApp): string {
    if (app.status === "published" && app.published_url) {
      return app.published_url;
    }
    return `/admin/apps/${app.id}`;
  }

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-background">
      <AdminPageHeader>
        <CustomBreadcrumb
          items={[{ label: "Apps", href: "/admin/apps", active: true }]}
        />
        <div className="flex items-center gap-2">
          <div className="hidden overflow-hidden rounded-md border md:flex">
            {[7, 14, 30].map((d) => (
              <button
                key={d}
                onClick={() => setStatsDays(d)}
                className={cn(
                  "px-2.5 py-1 text-[11px] transition-colors",
                  statsDays === d
                    ? "bg-muted font-medium text-foreground"
                    : "text-muted-foreground hover:bg-muted/50"
                )}
              >
                {d}d
              </button>
            ))}
          </div>
          <SearchInput
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            wrapperClassName="w-64"
            placeholder="Search apps..."
            disabled={isAppsLoading}
          />
          <Button
            size="sm"
            className="h-8 gap-1.5"
            onClick={() => {
              resetCreateForm();
              setCreateDialogOpen(true);
            }}
          >
            <Plus className="h-3.5 w-3.5" />
            Add New
          </Button>
        </div>
      </AdminPageHeader>

      <main className="flex-1 overflow-y-auto" data-admin-page-scroll>
        {appsError && (
          <div className="mx-4 mt-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {appsError}
          </div>
        )}

        {isAppsLoading ? (
          <div>
            {Array.from({ length: 5 }).map((_, index) => (
              <AppRowSkeleton key={index} />
            ))}
          </div>
        ) : filteredApps.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-24 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60">
              <Globe className="h-6 w-6 text-muted-foreground/40" />
            </div>
            <h3 className="mb-1 text-sm font-medium text-foreground">
              {search ? "No apps match your search" : "No apps yet"}
            </h3>
            <p className="mb-5 max-w-[300px] text-sm text-muted-foreground/70">
              {search
                ? "Try a different search term."
                : "Deploy your first app from a published agent to get started."}
            </p>
            {!search && (
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={() => {
                  resetCreateForm();
                  setCreateDialogOpen(true);
                }}
              >
                <Plus className="h-3.5 w-3.5" />
                Create App
              </Button>
            )}
          </div>
        ) : (
          <div className="divide-y divide-border/40">
            {filteredApps.map((app) => {
              const status = STATUS_CONFIG[app.status] || STATUS_CONFIG.draft;
              const agent = agentMap.get(app.agent_id);
              const providers = app.auth_providers || DEFAULT_PROVIDERS;

              return (
                <Link
                  key={app.id}
                  href={`/admin/apps/${app.id}`}
                  className="group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-muted/40"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/30 text-muted-foreground/70 transition-colors group-hover:border-border group-hover:bg-muted/50">
                    <Globe className="h-4 w-4" />
                  </div>

                  <div className="min-w-0 shrink-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-foreground">
                        {app.name}
                      </span>
                      <span className="flex shrink-0 items-center gap-1.5">
                        <span className={`h-1.5 w-1.5 rounded-full ${status.color}`} />
                        <span className="text-xs text-muted-foreground/70">{status.label}</span>
                      </span>
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2">
                      {agent ? (
                        <span className="truncate text-xs text-muted-foreground/60">
                          {agent.name}
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <div className="min-w-0 flex-1 flex justify-center">
                    {isStatsLoading && statsMap.size === 0 ? (
                      <AppRowStatsSkeleton />
                    ) : statsMap.has(app.id) ? (
                      <AppRowStats
                        stats={statsMap.get(app.id)!}
                        approximate={statsApproximate}
                      />
                    ) : (
                      <AppRowStatsEmpty />
                    )}
                  </div>

                  {app.auth_enabled ? (
                    <div className="hidden items-center gap-1.5 text-xs text-muted-foreground/60 md:flex">
                      <KeyRound className="h-3 w-3" />
                      <span>{providers.join(", ")}</span>
                    </div>
                  ) : (
                    <div className="hidden text-xs text-muted-foreground/40 md:block">
                      No auth
                    </div>
                  )}

                  <div className="hidden text-xs text-muted-foreground/50 lg:block">
                    Updated {relativeTime(app.updated_at)}
                  </div>

                  <div onClick={(e) => e.preventDefault()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-40">
                        <DropdownMenuItem
                          onClick={() => {
                            window.open(appRuntimeHref(app), "_blank", "noopener,noreferrer");
                          }}
                        >
                          <ExternalLink className="mr-2 h-3.5 w-3.5" />
                          {app.status === "published" ? "Open App" : "Open Builder"}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => handleDelete(app.id)}
                        >
                          <Trash2 className="mr-2 h-3.5 w-3.5" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </main>

      <Dialog
        open={createDialogOpen}
        onOpenChange={(open) => {
          setCreateDialogOpen(open);
          if (!open) resetCreateForm();
        }}
      >
        <DialogContent className="sm:max-w-[980px]">
          <DialogHeader>
            <DialogTitle>Create App</DialogTitle>
            <DialogDescription>
              Deploy a published agent as a standalone application.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-5 py-2 md:grid-cols-[1.1fr_1fr]">
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="create-app-name" className="text-xs font-medium text-muted-foreground">
                  App Name
                </Label>
                <Input
                  id="create-app-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Support Assistant"
                  className="h-9"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-medium text-muted-foreground">Published Agent</Label>
                <SearchableResourceInput
                  value={agentId}
                  onChange={setAgentId}
                  placeholder="Select published agent..."
                  disabled={isCreateResourcesLoading || publishedAgents.length === 0}
                  resources={publishedAgents.map((agent) => ({
                    value: agent.id,
                    label: agent.name,
                    info: agent.slug,
                  }))}
                />
                {isCreateResourcesLoading && (
                  <p className="text-xs text-muted-foreground">Loading published agents...</p>
                )}
              </div>

              <div className="space-y-3">
                <Label className="text-xs font-medium text-muted-foreground">Authentication</Label>
                <div className="divide-y divide-border/40 rounded-lg border border-border/60">
                  <label className="flex cursor-pointer items-center justify-between px-3 py-2.5 transition-colors hover:bg-muted/30">
                    <span className="text-sm">Require authentication</span>
                    <Checkbox
                      checked={authEnabled}
                      onCheckedChange={(checked) => setAuthEnabled(checked === true)}
                    />
                  </label>
                  <label className="flex cursor-pointer items-center justify-between px-3 py-2.5 transition-colors hover:bg-muted/30">
                    <span className="text-sm">Password provider</span>
                    <Checkbox
                      checked={providerPassword}
                      onCheckedChange={(checked) => setProviderPassword(checked === true)}
                    />
                  </label>
                  <label className="flex cursor-pointer items-center justify-between px-3 py-2.5 transition-colors hover:bg-muted/30">
                    <span className="text-sm">Google provider</span>
                    <Checkbox
                      checked={providerGoogle}
                      onCheckedChange={(checked) => setProviderGoogle(checked === true)}
                    />
                  </label>
                </div>
              </div>

              {createError && <p className="text-sm text-destructive">{createError}</p>}
            </div>

            <div className="space-y-3">
              <div className="space-y-2">
                <Label className="text-xs font-medium text-muted-foreground">
                  Frontend Template
                </Label>
                {isCreateResourcesLoading && templates.length === 0 ? (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {Array.from({ length: 2 }).map((_, index) => (
                      <Skeleton key={index} className="h-20 rounded-lg" />
                    ))}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {templates.map((template) => {
                      const active = template.key === templateKey;
                      return (
                        <button
                          key={template.key}
                          type="button"
                          onClick={() => setTemplateKey(template.key)}
                          className={`rounded-lg border p-3 text-left transition-colors ${
                            active ? "border-primary bg-primary/5" : "border-border/70 hover:border-border"
                          }`}
                        >
                          <div className="mb-1.5 text-sm font-semibold">{template.name}</div>
                          <div className="text-xs text-muted-foreground">{template.description}</div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-medium text-muted-foreground">
                  Auth Template
                </Label>
                {isCreateResourcesLoading && authTemplates.length === 0 ? (
                  <div className="grid grid-cols-1 gap-2">
                    {Array.from({ length: 2 }).map((_, index) => (
                      <Skeleton key={index} className="h-16 rounded-lg" />
                    ))}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-2">
                    {authTemplates.map((template) => {
                      const active = template.key === authTemplateKey;
                      return (
                        <button
                          key={template.key}
                          type="button"
                          onClick={() => setAuthTemplateKey(template.key)}
                          className={`rounded-lg border p-2.5 text-left transition-colors ${
                            active ? "border-primary bg-primary/5" : "border-border/70 hover:border-border"
                          }`}
                        >
                          <div className="text-sm font-semibold">{template.name}</div>
                          <div className="text-xs text-muted-foreground">{template.description}</div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateDialogOpen(false)}
              disabled={isCreating}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={
                isCreating ||
                isCreateResourcesLoading ||
                publishedAgents.length === 0 ||
                !templateKey ||
                !authTemplateKey
              }
            >
              {isCreating && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
              Create App
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
