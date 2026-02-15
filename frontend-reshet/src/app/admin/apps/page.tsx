"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ExternalLink,
  Globe,
  KeyRound,
  Loader2,
  MoreHorizontal,
  Plus,
  Search,
  Trash2,
} from "lucide-react";

import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Skeleton } from "@/components/ui/skeleton";
import { SearchableResourceInput } from "@/components/shared/SearchableResourceInput";
import { agentService, publishedAppsService } from "@/services";
import type { Agent, PublishedApp, PublishedAppAuthProvider, PublishedAppTemplate } from "@/services";

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
    <div className="flex items-center gap-4 px-4 py-3.5 border-b border-border/50">
      <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-4 w-36" />
        <Skeleton className="h-3 w-24" />
      </div>
      <Skeleton className="h-3 w-16 hidden md:block" />
      <Skeleton className="h-3 w-20 hidden lg:block" />
      <Skeleton className="h-3 w-12" />
    </div>
  );
}

export default function AppsPage() {
  const router = useRouter();
  const [apps, setApps] = useState<PublishedApp[]>([]);
  const [templates, setTemplates] = useState<PublishedAppTemplate[]>([]);
  const [publishedAgents, setPublishedAgents] = useState<Agent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const [name, setName] = useState("");
  const [agentId, setAgentId] = useState("");
  const [templateKey, setTemplateKey] = useState("");
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
    publishedAgents.forEach((a) => map.set(a.id, a));
    return map;
  }, [publishedAgents]);

  async function loadData() {
    setIsLoading(true);
    setError(null);
    try {
      const [appsResponse, agentsResponse, templatesResponse] = await Promise.all([
        publishedAppsService.list(),
        agentService.listAgents({ limit: 500 }),
        publishedAppsService.listTemplates(),
      ]);
      const publishedOnly = (agentsResponse.agents || []).filter(
        (agent) => String(agent.status).toLowerCase() === "published"
      );
      setApps(appsResponse);
      setTemplates(templatesResponse);
      setPublishedAgents(publishedOnly);
      if (!agentId && publishedOnly.length > 0) {
        setAgentId(publishedOnly[0].id);
      }
      if (!templateKey && templatesResponse.length > 0) {
        setTemplateKey(templatesResponse[0].key);
      }
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "Failed to load apps");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function resetCreateForm() {
    setName("");
    setTemplateKey((prev) => prev || templates[0]?.key || "");
    setProviderPassword(true);
    setProviderGoogle(false);
    setError(null);
  }

  async function handleCreate() {
    const nextName = name.trim();
    if (!nextName || !agentId || !templateKey) {
      setError("Name, template, and published agent are required");
      return;
    }

    const providers: PublishedAppAuthProvider[] = [];
    if (providerPassword) providers.push("password");
    if (providerGoogle) providers.push("google");
    if (providers.length === 0) {
      setError("Select at least one auth provider");
      return;
    }

    setIsCreating(true);
    setError(null);
    try {
      const created = await publishedAppsService.create({
        name: nextName,
        agent_id: agentId,
        template_key: templateKey,
        auth_enabled: authEnabled,
        auth_providers: providers,
      });
      setApps((prev) => [created, ...prev]);
      resetCreateForm();
      setCreateDialogOpen(false);
      router.push(`/admin/apps/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create app");
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
      setError(err instanceof Error ? err.message : "Failed to delete app");
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
      {/* Header */}
      <header className="h-12 shrink-0 bg-background px-4 flex items-center justify-between border-b border-border/40">
        <CustomBreadcrumb
          items={[{ label: "Apps", href: "/admin/apps", active: true }]}
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
      </header>

      {/* Search bar */}
      <div className="shrink-0 border-b border-border/40 px-4 py-3">
        <div className="relative max-w-md">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 pl-8 bg-muted/30 border-border/50 text-sm placeholder:text-muted-foreground/50"
            placeholder="Search apps..."
          />
        </div>
      </div>

      {/* Content */}
      <main className="flex-1 overflow-y-auto">
        {error && (
          <div className="mx-4 mt-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        {isLoading ? (
          <div>
            {Array.from({ length: 5 }).map((_, i) => (
              <AppRowSkeleton key={i} />
            ))}
          </div>
        ) : filteredApps.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 px-4 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-4">
              <Globe className="h-6 w-6 text-muted-foreground/40" />
            </div>
            <h3 className="text-sm font-medium text-foreground mb-1">
              {search ? "No apps match your search" : "No apps yet"}
            </h3>
            <p className="text-sm text-muted-foreground/70 max-w-[300px] mb-5">
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
                  {/* App icon */}
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/30 text-muted-foreground/70 group-hover:border-border group-hover:bg-muted/50 transition-colors">
                    <Globe className="h-4 w-4" />
                  </div>

                  {/* Name + slug */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground truncate">
                        {app.name}
                      </span>
                      <span className="flex items-center gap-1.5 shrink-0">
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${status.color}`}
                        />
                        <span className="text-xs text-muted-foreground/70">
                          {status.label}
                        </span>
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-muted-foreground/60 font-mono truncate">
                        /{app.slug}
                      </span>
                      {agent && (
                        <>
                          <span className="text-muted-foreground/30">·</span>
                          <span className="text-xs text-muted-foreground/60 truncate">
                            {agent.name}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Auth info */}
                  <div className="hidden md:flex items-center gap-1.5 shrink-0">
                    {app.auth_enabled ? (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground/60">
                        <KeyRound className="h-3 w-3" />
                        {providers.join(", ")}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground/40">
                        No auth
                      </span>
                    )}
                  </div>

                  {/* Updated time */}
                  <span className="hidden lg:block text-xs text-muted-foreground/50 shrink-0 w-16 text-right">
                    {relativeTime(app.updated_at)}
                  </span>

                  {/* Actions */}
                  <div
                    onClick={(e) => e.preventDefault()}
                    className="shrink-0"
                  >
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground"
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

      {/* Create App Dialog */}
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
                  resources={publishedAgents.map((agent) => ({
                    value: agent.id,
                    label: agent.name,
                    info: agent.slug,
                  }))}
                />
              </div>

              <div className="space-y-3">
                <Label className="text-xs font-medium text-muted-foreground">Authentication</Label>
                <div className="rounded-lg border border-border/60 divide-y divide-border/40">
                  <label className="flex items-center justify-between px-3 py-2.5 cursor-pointer hover:bg-muted/30 transition-colors">
                    <span className="text-sm">Require authentication</span>
                    <Checkbox
                      checked={authEnabled}
                      onCheckedChange={(checked) => setAuthEnabled(checked === true)}
                    />
                  </label>
                  <label className="flex items-center justify-between px-3 py-2.5 cursor-pointer hover:bg-muted/30 transition-colors">
                    <span className="text-sm">Password provider</span>
                    <Checkbox
                      checked={providerPassword}
                      onCheckedChange={(checked) => setProviderPassword(checked === true)}
                    />
                  </label>
                  <label className="flex items-center justify-between px-3 py-2.5 cursor-pointer hover:bg-muted/30 transition-colors">
                    <span className="text-sm">Google provider</span>
                    <Checkbox
                      checked={providerGoogle}
                      onCheckedChange={(checked) => setProviderGoogle(checked === true)}
                    />
                  </label>
                </div>
              </div>

              {error && (
                <p className="text-sm text-destructive">{error}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-medium text-muted-foreground">
                Frontend Template
              </Label>
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
              disabled={isCreating || isLoading || publishedAgents.length === 0 || !templateKey}
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
