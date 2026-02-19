"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ExternalLink,
  Layers,
  Loader2,
  Monitor,
  RefreshCw,
  Rocket,
  Save,
  Smartphone,
  X,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSidebar } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { publishedAppsService, publishedRuntimeService } from "@/services";
import type {
  BuilderStateResponse,
  DraftDevSessionResponse,
  DraftDevSessionStatus,
  PublishedAppAuthTemplate,
  PublishedAppDomain,
  PublishedAppRevision,
  PublishedAppUser,
} from "@/services";
import { cn } from "@/lib/utils";
import { sortTemplates } from "@/features/apps-builder/templates";
import { PreviewCanvas } from "@/features/apps-builder/preview/PreviewCanvas";
import { CodeEditorPanel } from "@/features/apps-builder/editor/CodeEditorPanel";
import { ConfigSidebar } from "@/features/apps-builder/workspace/ConfigSidebar";
import { AppsBuilderChatPanel } from "@/features/apps-builder/workspace/chat/AppsBuilderChatPanel";
import { useAppsBuilderChat } from "@/features/apps-builder/workspace/chat/useAppsBuilderChat";

const DRAFT_DEV_SYNC_DEBOUNCE_MS = 800;
const DRAFT_DEV_HEARTBEAT_MS = 45_000;
const PUBLISH_POLL_INTERVAL_MS = 2_000;
const PUBLISH_POLL_TIMEOUT_MS = 15 * 60_000;

type WorkspaceProps = {
  appId: string;
};

type ConfigSection = "overview" | "users" | "domains" | "code";

/** Extract route paths from app source files by matching common React Router patterns. */
function extractRoutesFromFiles(files: Record<string, string>): string[] {
  const routes = new Set<string>();
  routes.add("/");

  for (const content of Object.values(files)) {
    // Match <Route path="/something" ... />
    const jsxRouteRe = /path\s*[=:]\s*["'`](\/[^"'`]*)["'`]/g;
    let match: RegExpExecArray | null;
    while ((match = jsxRouteRe.exec(content)) !== null) {
      const route = match[1].split(/[?#]/)[0]; // strip query/hash
      if (route && !route.includes("${") && !route.includes(":")) {
        routes.add(route);
      }
    }

    // Match navigate("/something")
    const navigateRe = /navigate\(\s*["'`](\/[^"'`]*)["'`]/g;
    while ((match = navigateRe.exec(content)) !== null) {
      const route = match[1].split(/[?#]/)[0];
      if (route && !route.includes("${") && !route.includes(":")) {
        routes.add(route);
      }
    }

    // Match to="/something" (Link components)
    const linkToRe = /to\s*=\s*["'`](\/[^"'`]*)["'`]/g;
    while ((match = linkToRe.exec(content)) !== null) {
      const route = match[1].split(/[?#]/)[0];
      if (route && !route.includes("${") && !route.includes(":")) {
        routes.add(route);
      }
    }
  }

  return Array.from(routes).sort((a, b) => {
    if (a === "/") return -1;
    if (b === "/") return 1;
    return a.localeCompare(b);
  });
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function buildDraftDevSyncFingerprint(entry: string, nextFiles: Record<string, string>): string {
  return JSON.stringify({
    entry,
    files: nextFiles,
  });
}

export function AppsBuilderWorkspace({ appId }: WorkspaceProps) {
  const { setOpen } = useSidebar();
  const [state, setState] = useState<BuilderStateResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"preview" | "config">("preview");
  const [configSection, setConfigSection] = useState<ConfigSection>("overview");
  const [lastNonCodeConfigSection, setLastNonCodeConfigSection] = useState<Exclude<ConfigSection, "code">>("overview");
  const [files, setFiles] = useState<Record<string, string>>({});
  const [entryFile, setEntryFile] = useState("src/main.tsx");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [currentRevisionId, setCurrentRevisionId] = useState<string | null>(null);
  const [draftDevSessionId, setDraftDevSessionId] = useState<string | null>(null);
  const [draftDevStatus, setDraftDevStatus] = useState<DraftDevSessionStatus | null>(null);
  const [draftDevError, setDraftDevError] = useState<string | null>(null);
  const [previewAssetUrl, setPreviewAssetUrl] = useState<string | null>(null);
  const [publishStatus, setPublishStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingOverview, setIsSavingOverview] = useState(false);
  const [authTemplates, setAuthTemplates] = useState<PublishedAppAuthTemplate[]>([]);
  const [users, setUsers] = useState<PublishedAppUser[]>([]);
  const [domains, setDomains] = useState<PublishedAppDomain[]>([]);
  const [isUsersLoading, setIsUsersLoading] = useState(false);
  const [isDomainsLoading, setIsDomainsLoading] = useState(false);
  const [isAddingDomain, setIsAddingDomain] = useState(false);
  const [domainHostInput, setDomainHostInput] = useState("");
  const [domainNotesInput, setDomainNotesInput] = useState("");
  const [pendingUserUpdateId, setPendingUserUpdateId] = useState<string | null>(null);
  const [pendingDomainDeleteId, setPendingDomainDeleteId] = useState<string | null>(null);
  const [isPublishing, setIsPublishing] = useState(false);
  const [isOpeningApp, setIsOpeningApp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewRoute, setPreviewRoute] = useState("/");
  const [previewViewport, setPreviewViewport] = useState<"desktop" | "mobile">("desktop");
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const syncFingerprintRef = useRef<string>("");
  const draftDevSnapshotRef = useRef<{
    sessionId: string | null;
    status: DraftDevSessionStatus | null;
    previewUrl: string | null;
  }>({
    sessionId: null,
    status: null,
    previewUrl: null,
  });

  useEffect(() => {
    setOpen(false);
  }, [setOpen]);

  const appRoutes = useMemo(() => extractRoutesFromFiles(files), [files]);
  const orderedTemplates = useMemo(() => sortTemplates(state?.templates || []), [state?.templates]);
  const platformDomain = useMemo(
    () => `${state?.app.slug || "app"}.${process.env.NEXT_PUBLIC_APPS_BASE_DOMAIN || "apps.localhost"}`,
    [state?.app.slug],
  );

  const navigatePreview = useCallback((route: string) => {
    setPreviewRoute(route);
    const iframe = iframeRef.current;
    if (iframe && previewAssetUrl) {
      try {
        const base = new URL(previewAssetUrl);
        base.pathname = route;
        iframe.src = base.toString();
      } catch {
        // Fallback: just set src directly
        iframe.src = previewAssetUrl + (route === "/" ? "" : route);
      }
    }
  }, [previewAssetUrl]);

  const reloadPreview = useCallback(() => {
    const iframe = iframeRef.current;
    if (iframe) {
      // eslint-disable-next-line no-self-assign
      iframe.src = iframe.src;
    }
  }, []);

  const applyDraftDevSession = useCallback((session?: DraftDevSessionResponse | null) => {
    setDraftDevSessionId(session?.session_id || null);
    setDraftDevStatus((session?.status as DraftDevSessionStatus | undefined) || null);
    setDraftDevError(session?.last_error || null);
    setPreviewAssetUrl(session?.preview_url || null);
  }, []);

  const hydrateFromRevision = useCallback((revision?: PublishedAppRevision | null) => {
    const nextFiles = revision?.files || {};
    const nextEntry = revision?.entry_file || "src/main.tsx";
    setFiles(nextFiles);
    setEntryFile(nextEntry);
    setSelectedFile(Object.keys(nextFiles).sort()[0] || null);
    setCurrentRevisionId(revision?.id || null);
    syncFingerprintRef.current = buildDraftDevSyncFingerprint(nextEntry, nextFiles);
  }, []);

  const loadState = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [response, authTemplateList] = await Promise.all([
        publishedAppsService.getBuilderState(appId),
        publishedAppsService.listAuthTemplates(),
      ]);
      setState(response);
      setAuthTemplates(authTemplateList);
      hydrateFromRevision(response.current_draft_revision);
      applyDraftDevSession(response.draft_dev);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load builder state");
    } finally {
      setIsLoading(false);
    }
  }, [appId, applyDraftDevSession, hydrateFromRevision]);

  const refreshStateSilently = useCallback(async () => {
    try {
      const response = await publishedAppsService.getBuilderState(appId);
      setState(response);
      hydrateFromRevision(response.current_draft_revision);
      applyDraftDevSession(response.draft_dev);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh builder state");
    }
  }, [appId, applyDraftDevSession, hydrateFromRevision]);

  useEffect(() => {
    loadState();
  }, [loadState]);

  const updateLocalApp = useCallback((patch: Record<string, unknown>) => {
    setState((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        app: {
          ...prev.app,
          ...patch,
        },
      };
    });
  }, []);

  const ensureDraftDevSession = useCallback(async () => {
    const session = await publishedAppsService.ensureDraftDevSession(appId);
    applyDraftDevSession(session);
    setState((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        draft_dev: session,
      };
    });
  }, [appId, applyDraftDevSession]);

  const syncDraftDevSession = useCallback(async () => {
    if (!currentRevisionId) return;
    const session = await publishedAppsService.syncDraftDevSession(appId, {
      files,
      entry_file: entryFile,
      revision_id: currentRevisionId,
    });
    applyDraftDevSession(session);
    setState((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        draft_dev: session,
      };
    });
  }, [appId, applyDraftDevSession, currentRevisionId, entryFile, files]);

  useEffect(() => {
    draftDevSnapshotRef.current = {
      sessionId: draftDevSessionId,
      status: draftDevStatus,
      previewUrl: previewAssetUrl,
    };
  }, [draftDevSessionId, draftDevStatus, previewAssetUrl]);

  useEffect(() => {
    if (activeTab !== "preview" || !currentRevisionId) {
      return;
    }
    const snapshot = draftDevSnapshotRef.current;
    const hasReusableSession =
      snapshot.status === "running" && Boolean(snapshot.sessionId) && Boolean(snapshot.previewUrl);
    if (hasReusableSession || snapshot.status === "starting") {
      return;
    }
    setDraftDevError(null);
    setDraftDevStatus("starting");
    ensureDraftDevSession().catch((err) => {
      setDraftDevError(err instanceof Error ? err.message : "Failed to start draft preview");
      setDraftDevStatus("error");
      setPreviewAssetUrl(null);
    });
  }, [activeTab, currentRevisionId, ensureDraftDevSession]);

  useEffect(() => {
    if (activeTab !== "preview" || !currentRevisionId) {
      syncFingerprintRef.current = "";
      return;
    }
    if (!draftDevSessionId || draftDevStatus !== "running") {
      return;
    }
    const fingerprint = buildDraftDevSyncFingerprint(entryFile, files);
    if (syncFingerprintRef.current === fingerprint) {
      return;
    }
    const timer = window.setTimeout(() => {
      syncDraftDevSession()
        .then(() => {
          syncFingerprintRef.current = fingerprint;
        })
        .catch((err) => {
          setDraftDevError(err instanceof Error ? err.message : "Failed to sync draft dev session");
          setDraftDevStatus("error");
        });
    }, DRAFT_DEV_SYNC_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [activeTab, currentRevisionId, draftDevSessionId, draftDevStatus, entryFile, files, syncDraftDevSession]);

  useEffect(() => {
    if (activeTab !== "preview" || !draftDevSessionId) {
      return;
    }
    const interval = window.setInterval(() => {
      publishedAppsService
        .heartbeatDraftDevSession(appId)
        .then((session) => {
          applyDraftDevSession(session);
        })
        .catch(() => {
          // Heartbeat failure should not hard-break editing.
        });
    }, DRAFT_DEV_HEARTBEAT_MS);
    return () => {
      window.clearInterval(interval);
    };
  }, [activeTab, appId, applyDraftDevSession, draftDevSessionId]);

  const loadUsers = useCallback(async () => {
    setIsUsersLoading(true);
    try {
      const items = await publishedAppsService.listUsers(appId);
      setUsers(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load app users");
    } finally {
      setIsUsersLoading(false);
    }
  }, [appId]);

  const loadDomains = useCallback(async () => {
    setIsDomainsLoading(true);
    try {
      const items = await publishedAppsService.listDomains(appId);
      setDomains(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load app domains");
    } finally {
      setIsDomainsLoading(false);
    }
  }, [appId]);

  useEffect(() => {
    if (activeTab !== "config") return;
    if (configSection === "users") {
      void loadUsers();
      return;
    }
    if (configSection === "domains") {
      void loadDomains();
    }
  }, [activeTab, configSection, loadDomains, loadUsers]);

  const saveOverview = useCallback(async () => {
    if (!state) return;
    setIsSavingOverview(true);
    setError(null);
    try {
      const app = state.app;
      const updated = await publishedAppsService.update(appId, {
        name: app.name,
        description: app.description || "",
        logo_url: app.logo_url || "",
        visibility: app.visibility,
        auth_enabled: app.auth_enabled,
        auth_providers: app.auth_providers,
        auth_template_key: app.auth_template_key,
      });
      setState((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          app: {
            ...prev.app,
            ...updated,
          },
        };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save app settings");
    } finally {
      setIsSavingOverview(false);
    }
  }, [appId, state]);

  const toggleUserBlocked = useCallback(async (user: PublishedAppUser) => {
    setPendingUserUpdateId(user.user_id);
    setError(null);
    try {
      const nextStatus = user.membership_status === "blocked" ? "active" : "blocked";
      const updated = await publishedAppsService.updateUser(appId, user.user_id, {
        membership_status: nextStatus,
      });
      setUsers((prev) => prev.map((item) => (item.user_id === updated.user_id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update user membership");
    } finally {
      setPendingUserUpdateId(null);
    }
  }, [appId]);

  const addDomain = useCallback(async () => {
    const host = domainHostInput.trim();
    if (!host) return;
    setIsAddingDomain(true);
    setError(null);
    try {
      const created = await publishedAppsService.createDomain(appId, {
        host,
        notes: domainNotesInput.trim() || undefined,
      });
      setDomains((prev) => [created, ...prev]);
      setDomainHostInput("");
      setDomainNotesInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to request custom domain");
    } finally {
      setIsAddingDomain(false);
    }
  }, [appId, domainHostInput, domainNotesInput]);

  const removeDomain = useCallback(async (domainId: string) => {
    setPendingDomainDeleteId(domainId);
    setError(null);
    try {
      await publishedAppsService.deleteDomain(appId, domainId);
      setDomains((prev) => prev.filter((item) => item.id !== domainId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove custom domain");
    } finally {
      setPendingDomainDeleteId(null);
    }
  }, [appId]);

  const saveDraft = useCallback(async () => {
    if (!currentRevisionId && Object.keys(files).length === 0) return;

    setIsSaving(true);
    setError(null);
    try {
      const revision = await publishedAppsService.createRevision(appId, {
        base_revision_id: currentRevisionId || undefined,
        files,
        entry_file: entryFile,
      });
      syncFingerprintRef.current = JSON.stringify({
        entry: entryFile,
        files,
      });
      setCurrentRevisionId(revision.id);
      setState((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          current_draft_revision: revision,
          app: {
            ...prev.app,
            current_draft_revision_id: revision.id,
          },
        };
      });
      if (activeTab === "preview") {
        await ensureDraftDevSession();
      }
    } catch (err: any) {
      const detail = err?.message || "Failed to save draft";
      try {
        const parsed = JSON.parse(detail) as RevisionConflictResponse;
        if (parsed.code === "REVISION_CONFLICT") {
          setError(`Revision conflict. Latest revision is ${parsed.latest_revision_id}. Reloading state...`);
          await loadState();
          return;
        }
      } catch {
        // ignore
      }
      setError(err instanceof Error ? err.message : "Failed to save draft");
    } finally {
      setIsSaving(false);
    }
  }, [activeTab, appId, currentRevisionId, ensureDraftDevSession, entryFile, files, loadState]);

  const publish = useCallback(async () => {
    setIsPublishing(true);
    setError(null);
    setPublishStatus("queued");
    try {
      const job = await publishedAppsService.publish(appId, {
        base_revision_id: currentRevisionId || undefined,
        files,
        entry_file: entryFile,
      });

      setPublishStatus(job.status);
      const startedAt = Date.now();
      let status = job.status;
      if (status === "failed") {
        const diagnostic = job.diagnostics?.[0];
        const message = (diagnostic?.message as string | undefined) || job.error || "Publish failed";
        throw new Error(message);
      }
      while (status === "queued" || status === "running") {
        if (Date.now() - startedAt > PUBLISH_POLL_TIMEOUT_MS) {
          throw new Error("Publish timed out while waiting for build completion");
        }
        await wait(PUBLISH_POLL_INTERVAL_MS);
        const current = await publishedAppsService.getPublishJobStatus(appId, job.job_id);
        status = current.status;
        setPublishStatus(status);
        if (status === "failed") {
          const diagnostic = current.diagnostics?.[0];
          const message = (diagnostic?.message as string | undefined) || current.error || "Publish failed";
          throw new Error(message);
        }
      }
      if (status !== "succeeded") {
        throw new Error("Publish ended in an unexpected state");
      }

      await loadState();
      setPublishStatus("succeeded");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to publish app");
      setPublishStatus("failed");
    } finally {
      setIsPublishing(false);
    }
  }, [appId, currentRevisionId, entryFile, files, loadState]);

  const resetTemplate = useCallback(
    async (templateKey: string) => {
      if (!window.confirm("Switch template and overwrite current draft?")) {
        return;
      }
      try {
        const revision = await publishedAppsService.resetTemplate(appId, templateKey);
        setState((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            app: {
              ...prev.app,
              template_key: templateKey,
              current_draft_revision_id: revision.id,
            },
            current_draft_revision: revision,
          };
        });
        hydrateFromRevision(revision);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to switch template");
      }
    },
    [appId, hydrateFromRevision],
  );

  const applyRestoredRevision = useCallback((revision: PublishedAppRevision) => {
    hydrateFromRevision(revision);
    setState((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        current_draft_revision: revision,
        app: { ...prev.app, current_draft_revision_id: revision.id },
      };
    });
  }, [hydrateFromRevision]);

  const {
    isAgentPanelOpen,
    setIsAgentPanelOpen,
    isSending,
    isUndoing,
    timeline,
    activeThinkingSummary,
    chatSessions,
    chatModels,
    setSelectedRunModelId,
    isModelSelectorOpen,
    setIsModelSelectorOpen,
    selectedRunModelLabel,
    sendBuilderChat,
    stopCurrentRun,
    startNewChat,
    revertToCheckpoint,
    loadChatSession,
  } = useAppsBuilderChat({
    appId,
    currentRevisionId,
    activeTab,
    ensureDraftDevSession,
    refreshStateSilently,
    onApplyRestoredRevision: applyRestoredRevision,
    onSetCurrentRevisionId: setCurrentRevisionId,
    onError: setError,
  });

  const openApp = useCallback(async () => {
    setError(null);
    if (state?.app.status === "published") {
      const publishedUrl = state.app.published_url || null;
      const localBaseDomain = (process.env.NEXT_PUBLIC_APPS_BASE_DOMAIN || "apps.localhost").toLowerCase();
      const shouldUsePublishedPreviewProxy = (() => {
        if (!publishedUrl) return false;
        try {
          const parsed = new URL(publishedUrl);
          return parsed.hostname.toLowerCase().endsWith(`.${localBaseDomain}`);
        } catch {
          return false;
        }
      })();

      if (
        shouldUsePublishedPreviewProxy &&
        state.app.current_published_revision_id
      ) {
        setIsOpeningApp(true);
        try {
          const tokenResponse = await publishedAppsService.createRevisionPreviewToken(
            appId,
            state.app.current_published_revision_id,
          );
          const runtime = await publishedRuntimeService.getPreviewRuntime(
            state.app.current_published_revision_id,
            tokenResponse.preview_token,
          );
          if (!runtime.preview_url) {
            throw new Error("Published preview URL is unavailable");
          }
          window.open(runtime.preview_url, "_blank", "noopener,noreferrer");
          return;
        } catch (err) {
          setError(err instanceof Error ? err.message : "Failed to open app");
          return;
        } finally {
          setIsOpeningApp(false);
        }
      }

      if (publishedUrl) {
        window.open(publishedUrl, "_blank", "noopener,noreferrer");
        return;
      }
    }

    setIsOpeningApp(true);
    try {
      const session = await publishedAppsService.ensureDraftDevSession(appId);
      applyDraftDevSession(session);
      setState((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          draft_dev: session,
        };
      });
      if (!session.preview_url) {
        throw new Error("Draft preview URL is unavailable");
      }
      window.open(session.preview_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open app");
    } finally {
      setIsOpeningApp(false);
    }
  }, [
    appId,
    applyDraftDevSession,
    state?.app.current_published_revision_id,
    state?.app.published_url,
    state?.app.status,
  ]);

  const deleteFile = (path: string) => {
    setFiles((prev) => {
      const next = { ...prev };
      delete next[path];
      return next;
    });
    if (selectedFile === path) {
      const rest = Object.keys(files).filter((item) => item !== path).sort();
      setSelectedFile(rest[0] || null);
    }
  };

  const handleConfigSectionChange = useCallback((section: ConfigSection) => {
    setConfigSection(section);
    if (section !== "code") {
      setLastNonCodeConfigSection(section);
    }
  }, []);

  const handleBackFromCode = useCallback(() => {
    setConfigSection(lastNonCodeConfigSection);
  }, [lastNonCodeConfigSection]);

  if (isLoading) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading builder...
      </div>
    );
  }

  if (!state) {
    return <div className="p-6 text-sm text-destructive">Builder state unavailable.</div>;
  }

  return (
    <Tabs
      value={activeTab}
      onValueChange={(value) => setActiveTab(value as "preview" | "config")}
      className="flex h-dvh min-h-0 w-full overflow-hidden gap-0 bg-background"
    >
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-11 shrink-0 items-center gap-3 border-b border-border/50 px-3">
          {/* Left: back + app name + status dot */}
          <div className="flex min-w-0 items-center gap-3">
            <Link
              href="/admin/apps"
              className="flex items-center gap-1 text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
            </Link>
            <div className="flex items-center gap-1.5 truncate text-sm font-medium">
              <span className="truncate">{state.app.name}</span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    className={cn(
                      "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
                      state.app.status === "published"
                        ? "bg-emerald-500"
                        : draftDevStatus === "running"
                          ? "bg-blue-500"
                          : draftDevStatus === "error"
                            ? "bg-destructive"
                            : "bg-muted-foreground/40",
                    )}
                  />
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {state.app.status === "published" ? "Published" : `Draft — ${draftDevStatus || "idle"}`}
                  {publishStatus ? ` · publish: ${publishStatus}` : ""}
                </TooltipContent>
              </Tooltip>
            </div>
          </div>

          {/* Center: tabs stay fixed; preview controls are out of flow */}
          <div className="relative flex min-w-0 flex-1 items-center justify-center">
            <div className="relative flex items-center">
              <TabsList className="h-7 rounded-md p-0.5">
                <TabsTrigger value="preview" className="h-6 rounded-[5px] px-2.5 text-xs">Preview</TabsTrigger>
                <TabsTrigger value="config" className="h-6 rounded-[5px] px-2.5 text-xs">Config</TabsTrigger>
              </TabsList>

              {activeTab === "preview" && (
                <div className="absolute top-1/2 left-full ml-2 flex -translate-y-1/2 items-center gap-1">
                  <Select value={previewRoute} onValueChange={navigatePreview}>
                    <SelectTrigger className="data-[size=default]:h-7 h-7 w-36 gap-1 rounded-md border-border/50 bg-transparent px-2 py-0 text-xs font-medium shadow-none">
                      <SelectValue placeholder="/" />
                    </SelectTrigger>
                    <SelectContent>
                      {appRoutes.map((route) => (
                        <SelectItem key={route} value={route}>
                          {route}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 text-muted-foreground hover:text-foreground"
                        onClick={() => setPreviewViewport(previewViewport === "desktop" ? "mobile" : "desktop")}
                      >
                        {previewViewport === "desktop" ? <Smartphone className="h-3.5 w-3.5" /> : <Monitor className="h-3.5 w-3.5" />}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">{previewViewport === "desktop" ? "Mobile view" : "Desktop view"}</TooltipContent>
                  </Tooltip>

                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 text-muted-foreground hover:text-foreground"
                        onClick={reloadPreview}
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">Reload preview</TooltipContent>
                  </Tooltip>
                </div>
              )}
            </div>
          </div>

          {/* Right: actions */}
          <div className="ml-auto flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7 text-muted-foreground hover:text-foreground"
                  onClick={openApp}
                  disabled={isOpeningApp}
                  aria-label={state.app.status === "published" ? "Open App" : "Open Preview"}
                >
                  {isOpeningApp ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ExternalLink className="h-3.5 w-3.5" />}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">{state.app.status === "published" ? "Open App" : "Open Preview"}</TooltipContent>
            </Tooltip>

            <DropdownMenu>
              <Tooltip>
                <TooltipTrigger asChild>
                  <DropdownMenuTrigger asChild>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 text-muted-foreground hover:text-foreground"
                      aria-label="Template"
                    >
                      <Layers className="h-3.5 w-3.5" />
                    </Button>
                  </DropdownMenuTrigger>
                </TooltipTrigger>
                <TooltipContent side="bottom">Template</TooltipContent>
              </Tooltip>
              <DropdownMenuContent align="end">
                {orderedTemplates.map((template) => (
                  <DropdownMenuItem
                    key={template.key}
                    onClick={() => resetTemplate(template.key)}
                    className={cn(template.key === state.app.template_key && "font-medium")}
                  >
                    {template.name}
                    {template.key === state.app.template_key && (
                      <span className="ml-auto text-xs text-muted-foreground">current</span>
                    )}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            <div className="mx-0.5 h-4 w-px bg-border/60" />

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
                  onClick={saveDraft}
                  disabled={isSaving}
                  aria-label="Save Draft"
                >
                  {isSaving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                  Save
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">Save Draft</TooltipContent>
            </Tooltip>

            <Button
              size="sm"
              className="h-7 gap-1.5 px-2.5 text-xs"
              onClick={publish}
              disabled={isPublishing}
            >
              {isPublishing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Rocket className="h-3 w-3" />}
              Publish
            </Button>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <main className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1">
              {activeTab === "preview" ? (
                <div className={cn(
                  "flex h-full w-full items-start justify-center",
                  previewViewport === "mobile" ? "bg-muted/30 p-4" : "",
                )}>
                  <div className={cn(
                    "h-full",
                    previewViewport === "mobile"
                      ? "w-[390px] overflow-hidden rounded-xl border border-border/60 shadow-sm"
                      : "w-full",
                  )}>
                    <PreviewCanvas
                      ref={iframeRef}
                      previewUrl={previewAssetUrl}
                      devStatus={draftDevStatus}
                      devError={draftDevError}
                    />
                  </div>
                </div>
              ) : (
                <div className="flex h-full min-h-0">
                  <ConfigSidebar
                    configSection={configSection}
                    onChangeSection={handleConfigSectionChange}
                    onBackFromCode={handleBackFromCode}
                    files={files}
                    selectedFile={selectedFile}
                    onSelectFile={setSelectedFile}
                    onDeleteFile={deleteFile}
                  />

                  <section className={cn("min-w-0 flex-1", configSection === "code" ? "overflow-hidden" : "overflow-auto")}>
                    {configSection === "overview" && (
                      <div className="mx-auto max-w-3xl space-y-4 p-4">
                        <h3 className="text-lg font-semibold">Overview</h3>
                        <div className="grid gap-4 md:grid-cols-2">
                          <div className="space-y-2">
                            <Label>App Name</Label>
                            <Input
                              value={state.app.name}
                              onChange={(event) => updateLocalApp({ name: event.target.value })}
                            />
                          </div>
                          <div className="space-y-2">
                            <Label>App Logo URL</Label>
                            <Input
                              value={state.app.logo_url || ""}
                              onChange={(event) => updateLocalApp({ logo_url: event.target.value })}
                              placeholder="https://..."
                            />
                          </div>
                          <div className="space-y-2 md:col-span-2">
                            <Label>Description</Label>
                            <textarea
                              className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                              value={state.app.description || ""}
                              onChange={(event) => updateLocalApp({ description: event.target.value })}
                            />
                          </div>
                          <div className="space-y-2">
                            <Label>Visibility</Label>
                            <Select
                              value={state.app.visibility}
                              onValueChange={(value) => updateLocalApp({ visibility: value })}
                            >
                              <SelectTrigger>
                                <SelectValue placeholder="Visibility" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="public">Public</SelectItem>
                                <SelectItem value="private">Private</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-2">
                            <Label>Auth Template</Label>
                            <Select
                              value={state.app.auth_template_key}
                              onValueChange={(value) => updateLocalApp({ auth_template_key: value })}
                            >
                              <SelectTrigger>
                                <SelectValue placeholder="Auth template" />
                              </SelectTrigger>
                              <SelectContent>
                                {authTemplates.map((item) => (
                                  <SelectItem key={item.key} value={item.key}>
                                    {item.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        </div>

                        <div className="rounded-md border border-border/60 p-3">
                          <label className="flex items-center justify-between gap-3">
                            <span className="text-sm">Require login for public app</span>
                            <Checkbox
                              checked={state.app.auth_enabled}
                              onCheckedChange={(checked) => updateLocalApp({ auth_enabled: checked === true })}
                            />
                          </label>
                          <div className="mt-3 grid gap-2 sm:grid-cols-2">
                            <label className="flex items-center justify-between rounded border border-border/60 px-3 py-2 text-sm">
                              Password provider
                              <Checkbox
                                checked={(state.app.auth_providers || []).includes("password")}
                                onCheckedChange={(checked) => {
                                  const current = new Set(state.app.auth_providers || []);
                                  if (checked) current.add("password");
                                  else current.delete("password");
                                  updateLocalApp({ auth_providers: Array.from(current) });
                                }}
                              />
                            </label>
                            <label className="flex items-center justify-between rounded border border-border/60 px-3 py-2 text-sm">
                              Google provider
                              <Checkbox
                                checked={(state.app.auth_providers || []).includes("google")}
                                onCheckedChange={(checked) => {
                                  const current = new Set(state.app.auth_providers || []);
                                  if (checked) current.add("google");
                                  else current.delete("google");
                                  updateLocalApp({ auth_providers: Array.from(current) });
                                }}
                              />
                            </label>
                          </div>
                        </div>

                        <Button onClick={saveOverview} disabled={isSavingOverview}>
                          {isSavingOverview ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                          Save Overview
                        </Button>
                      </div>
                    )}

                    {configSection === "users" && (
                      <div className="space-y-3 p-4">
                        <h3 className="text-lg font-semibold">Users</h3>
                        {isUsersLoading ? <div className="text-sm text-muted-foreground">Loading users...</div> : null}
                        <div className="space-y-2">
                          {users.map((user) => (
                            <div key={user.user_id} className="flex items-center justify-between rounded-md border border-border/60 p-3">
                              <div>
                                <div className="text-sm font-medium">{user.full_name || user.email}</div>
                                <div className="text-xs text-muted-foreground">
                                  {user.email} · sessions:{user.active_sessions} · status:{user.membership_status}
                                </div>
                              </div>
                              <Button
                                size="sm"
                                variant={user.membership_status === "blocked" ? "default" : "outline"}
                                onClick={() => toggleUserBlocked(user)}
                                disabled={pendingUserUpdateId === user.user_id}
                              >
                                {pendingUserUpdateId === user.user_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                                {user.membership_status === "blocked" ? "Unblock" : "Block"}
                              </Button>
                            </div>
                          ))}
                          {!isUsersLoading && users.length === 0 ? (
                            <div className="text-sm text-muted-foreground">No app users yet.</div>
                          ) : null}
                        </div>
                      </div>
                    )}

                    {configSection === "domains" && (
                      <div className="space-y-3 p-4">
                        <h3 className="text-lg font-semibold">Domains</h3>
                        <div className="rounded-md border border-border/60 p-3 text-sm">
                          Platform Domain
                          <div className="font-mono text-xs text-muted-foreground">{platformDomain}</div>
                        </div>
                        <div className="rounded-md border border-border/60 p-3">
                          <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
                            <Input
                              value={domainHostInput}
                              onChange={(event) => setDomainHostInput(event.target.value)}
                              placeholder="app.example.com"
                            />
                            <Input
                              value={domainNotesInput}
                              onChange={(event) => setDomainNotesInput(event.target.value)}
                              placeholder="Notes (optional)"
                            />
                            <Button onClick={addDomain} disabled={isAddingDomain || !domainHostInput.trim()}>
                              {isAddingDomain ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Add Domain"}
                            </Button>
                          </div>
                        </div>

                        {isDomainsLoading ? <div className="text-sm text-muted-foreground">Loading domains...</div> : null}
                        <div className="space-y-2">
                          {domains.map((domain) => (
                            <div key={domain.id} className="flex items-center justify-between rounded-md border border-border/60 p-3">
                              <div>
                                <div className="text-sm font-medium">{domain.host}</div>
                                <div className="text-xs text-muted-foreground">
                                  status:{domain.status}{domain.notes ? ` · ${domain.notes}` : ""}
                                </div>
                              </div>
                              {domain.status === "pending" ? (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => removeDomain(domain.id)}
                                  disabled={pendingDomainDeleteId === domain.id}
                                >
                                  {pendingDomainDeleteId === domain.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Remove"}
                                </Button>
                              ) : null}
                            </div>
                          ))}
                          {!isDomainsLoading && domains.length === 0 ? (
                            <div className="text-sm text-muted-foreground">No custom domains requested.</div>
                          ) : null}
                        </div>
                      </div>
                    )}

                    {configSection === "code" && (
                      <CodeEditorPanel
                        files={files}
                        selectedFile={selectedFile}
                        onUpdateFile={(path, content) => setFiles((prev) => ({ ...prev, [path]: content }))}
                      />
                    )}
                  </section>
                </div>
              )}
            </div>
          </main>

          <AppsBuilderChatPanel
            isOpen={isAgentPanelOpen}
            onOpenChange={setIsAgentPanelOpen}
            isSending={isSending}
            isUndoing={isUndoing}
            timeline={timeline}
            activeThinkingSummary={activeThinkingSummary}
            chatSessions={chatSessions}
            onStartNewChat={startNewChat}
            onLoadChatSession={loadChatSession}
            onSendMessage={sendBuilderChat}
            onStopRun={stopCurrentRun}
            onRevertToCheckpoint={revertToCheckpoint}
            chatModels={chatModels}
            selectedRunModelLabel={selectedRunModelLabel}
            isModelSelectorOpen={isModelSelectorOpen}
            onModelSelectorOpenChange={setIsModelSelectorOpen}
            onSelectModelId={setSelectedRunModelId}
          />
        </div>
      </div>

      {error ? (
        <div className="pointer-events-none fixed bottom-4 right-4 z-50 w-full max-w-md px-4 sm:px-0">
          <Alert variant="destructive" className="pointer-events-auto pr-10 shadow-lg">
            <button
              type="button"
              onClick={() => setError(null)}
              className="absolute right-2 top-2 rounded-sm p-1 text-destructive-foreground/80 transition-colors hover:text-destructive-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Dismiss error"
            >
              <X className="h-3.5 w-3.5" />
            </button>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </div>
      ) : null}
    </Tabs>
  );
}
