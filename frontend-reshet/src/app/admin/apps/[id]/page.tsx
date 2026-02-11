"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, Loader2, Save } from "lucide-react";

import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SearchableResourceInput } from "@/components/shared/SearchableResourceInput";
import { agentService, publishedAppsService } from "@/services";
import type { Agent, PublishedApp } from "@/services";

export default function AppDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const appId = params?.id;

  const [app, setApp] = useState<PublishedApp | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runtimeUrl, setRuntimeUrl] = useState<string>("");

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [agentId, setAgentId] = useState("");
  const [authEnabled, setAuthEnabled] = useState(true);
  const [passwordEnabled, setPasswordEnabled] = useState(true);
  const [googleEnabled, setGoogleEnabled] = useState(false);

  async function load() {
    if (!appId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [appData, agentsData, preview] = await Promise.all([
        publishedAppsService.get(appId),
        agentService.listAgents({ limit: 500 }),
        publishedAppsService.runtimePreview(appId),
      ]);
      const publishedAgents = (agentsData.agents || []).filter(
        (agent) => String(agent.status).toLowerCase() === "published"
      );
      setApp(appData);
      setAgents(publishedAgents);
      setRuntimeUrl(preview.runtime_url);
      setName(appData.name);
      setSlug(appData.slug);
      setAgentId(appData.agent_id);
      setAuthEnabled(appData.auth_enabled);
      setPasswordEnabled((appData.auth_providers || []).includes("password"));
      setGoogleEnabled((appData.auth_providers || []).includes("google"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load app");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId]);

  async function handleSave() {
    if (!appId) return;
    const providers: Array<"password" | "google"> = [];
    if (passwordEnabled) providers.push("password");
    if (googleEnabled) providers.push("google");
    if (providers.length === 0) {
      setError("At least one auth provider must be enabled");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      const updated = await publishedAppsService.update(appId, {
        name: name.trim(),
        slug: slug.trim().toLowerCase(),
        agent_id: agentId,
        auth_enabled: authEnabled,
        auth_providers: providers,
      });
      setApp(updated);
      const preview = await publishedAppsService.runtimePreview(appId);
      setRuntimeUrl(preview.runtime_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setIsSaving(false);
    }
  }

  async function handlePublishToggle() {
    if (!appId || !app) return;
    setIsSaving(true);
    setError(null);
    try {
      const updated = app.status === "published"
        ? await publishedAppsService.unpublish(appId)
        : await publishedAppsService.publish(appId);
      setApp(updated);
      const preview = await publishedAppsService.runtimePreview(appId);
      setRuntimeUrl(preview.runtime_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update publish state");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading app...
      </div>
    );
  }

  if (!app) {
    return (
      <div className="p-6 text-destructive">
        App not found.
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-background">
      <header className="h-12 shrink-0 bg-background px-4 flex items-center justify-between">
        <CustomBreadcrumb
          items={[
            { label: "Apps", href: "/admin/apps" },
            { label: app.name, href: `/admin/apps/${app.id}`, active: true },
          ]}
        />
        <Button variant="outline" size="sm" onClick={() => router.push("/admin/apps")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
      </header>

      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{app.name}</CardTitle>
              <Badge variant={app.status === "published" ? "default" : "secondary"}>{app.status}</Badge>
            </div>
            <CardDescription>Manage runtime, auth defaults, and connected agent.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="app-name">App Name</Label>
              <Input id="app-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="app-slug">Slug</Label>
              <Input id="app-slug" value={slug} onChange={(e) => setSlug(e.target.value)} />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label>Published Agent</Label>
              <SearchableResourceInput
                value={agentId}
                onChange={setAgentId}
                placeholder="Select published agent..."
                resources={agents.map((agent) => ({
                  value: agent.id,
                  label: agent.name,
                  info: agent.slug,
                }))}
              />
            </div>
            <div className="space-y-3 md:col-span-2">
              <div className="flex items-center justify-between rounded-md border p-3">
                <span className="text-sm">Auth Enabled (default ON)</span>
                <Checkbox checked={authEnabled} onCheckedChange={(checked) => setAuthEnabled(checked === true)} />
              </div>
              <div className="flex items-center justify-between rounded-md border p-3">
                <span className="text-sm">Password Provider</span>
                <Checkbox checked={passwordEnabled} onCheckedChange={(checked) => setPasswordEnabled(checked === true)} />
              </div>
              <div className="flex items-center justify-between rounded-md border p-3">
                <span className="text-sm">Google Provider</span>
                <Checkbox checked={googleEnabled} onCheckedChange={(checked) => setGoogleEnabled(checked === true)} />
              </div>
            </div>
          </CardContent>
          <CardFooter className="flex flex-wrap gap-2">
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              Save
            </Button>
            <Button onClick={handlePublishToggle} variant={app.status === "published" ? "outline" : "default"} disabled={isSaving}>
              {app.status === "published" ? "Unpublish" : "Publish"}
            </Button>
            <Button asChild variant="outline" disabled={!runtimeUrl}>
              <Link href={`/published/${app.slug}`} target="_blank">
                <ExternalLink className="mr-2 h-4 w-4" />
                Open Preview
              </Link>
            </Button>
            {runtimeUrl ? (
              <span className="text-xs text-muted-foreground break-all">Runtime: {runtimeUrl}</span>
            ) : null}
          </CardFooter>
        </Card>
        {error ? <div className="text-sm text-destructive">{error}</div> : null}
      </main>
    </div>
  );
}
