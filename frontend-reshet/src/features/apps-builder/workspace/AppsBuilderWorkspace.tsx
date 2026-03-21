"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Camera,
  Check,
  Copy,
  ExternalLink,
  Globe,
  KeyRound,
  Layers,
  Loader2,
  Lock,
  Monitor,
  Plus,
  PanelRightClose,
  RefreshCw,
  Rocket,
  Save,
  Shield,
  Smartphone,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
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
import {
  isDraftDevFailureStatus,
  isDraftDevServingStatus,
  publishedAppsService,
} from "@/services";
import type {
  BuilderStateResponse,
  DraftDevSessionResponse,
  PublishedAppAuthTemplate,
  PublishedAppDomain,
  PublishedAppRevision,
  PublishedAppUser,
  RevisionConflictResponse,
} from "@/services";
import { filterAppsBuilderFiles, isAppsBuilderBlockedFilePath } from "@/services/apps-builder-file-filter";
import { cn } from "@/lib/utils";
import { sortTemplates } from "@/features/apps-builder/templates";
import { PreviewCanvas } from "@/features/apps-builder/preview/PreviewCanvas";
import { CodeEditorPanel } from "@/features/apps-builder/editor/CodeEditorPanel";
import { FileTree } from "@/features/apps-builder/editor/FileTree";
import { ConfigSidebar } from "@/features/apps-builder/workspace/ConfigSidebar";
import { LogoPickerDialog } from "@/features/apps-builder/workspace/LogoPickerDialog";
import { useAppsBuilderVersions } from "@/features/apps-builder/workspace/versions/useAppsBuilderVersions";
import {
  AppsBuilderWorkspaceBootSkeleton,
  DomainsListSkeleton,
  UsersListSkeleton,
} from "@/features/apps-builder/workspace/WorkspaceLoadingSkeletons";
import { AppsBuilderChatPanel } from "@/features/apps-builder/workspace/chat/AppsBuilderChatPanel";
import { useAppsBuilderChat } from "@/features/apps-builder/workspace/chat/useAppsBuilderChat";
import { useAppsBuilderSandboxLifecycle } from "@/features/apps-builder/workspace/useAppsBuilderSandboxLifecycle";

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

function buildDraftDevSyncFingerprint(entry: string, nextFiles: Record<string, string>): string {
  return JSON.stringify({
    entry,
    files: nextFiles,
  });
}

function buildPreviewFrameUrl(baseUrl: string, route: string, reloadToken: number): string {
  try {
    const parsed = new URL(baseUrl);
    if (route !== "/") {
      const basePath = parsed.pathname.endsWith("/") ? parsed.pathname.slice(0, -1) : parsed.pathname;
      parsed.pathname = `${basePath}${route}`;
    }
    if (reloadToken > 0) {
      parsed.searchParams.set("__reload", String(reloadToken));
    }
    return parsed.toString();
  } catch {
    const normalizedRoute = route === "/" ? "" : route;
    const normalizedBase = route === "/" ? baseUrl : baseUrl.replace(/\/+$/, "");
    const separator = normalizedBase.includes("?") ? "&" : "?";
    const suffix = reloadToken > 0 ? `${separator}__reload=${reloadToken}` : "";
    return `${normalizedBase}${normalizedRoute}${suffix}`;
  }
}

function appendRuntimeTokenToUrl(url: string, token?: string | null): string {
  const trimmedToken = String(token || "").trim();
  if (!trimmedToken) return url;
  try {
    const parsed = new URL(url);
    parsed.searchParams.set("runtime_token", trimmedToken);
    return parsed.toString();
  } catch {
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}runtime_token=${encodeURIComponent(trimmedToken)}`;
  }
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
  const [selectedVersionCodeFile, setSelectedVersionCodeFile] = useState<string | null>(null);
  const [currentRevisionId, setCurrentRevisionId] = useState<string | null>(null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isAuthTemplatesLoading, setIsAuthTemplatesLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingOverview, setIsSavingOverview] = useState(false);
  const [authTemplates, setAuthTemplates] = useState<PublishedAppAuthTemplate[]>([]);
  const [users, setUsers] = useState<PublishedAppUser[]>([]);
  const [domains, setDomains] = useState<PublishedAppDomain[]>([]);
  const [hasLoadedUsers, setHasLoadedUsers] = useState(false);
  const [hasLoadedDomains, setHasLoadedDomains] = useState(false);
  const [isUsersLoading, setIsUsersLoading] = useState(false);
  const [isDomainsLoading, setIsDomainsLoading] = useState(false);
  const [isAddingDomain, setIsAddingDomain] = useState(false);
  const [domainHostInput, setDomainHostInput] = useState("");
  const [domainNotesInput, setDomainNotesInput] = useState("");
  const [pendingUserUpdateId, setPendingUserUpdateId] = useState<string | null>(null);
  const [pendingDomainDeleteId, setPendingDomainDeleteId] = useState<string | null>(null);
  const [hasUnsavedManualCodeChanges, setHasUnsavedManualCodeChanges] = useState(false);
  const hasActiveCodingRunLock = Boolean(state?.draft_dev?.has_active_coding_runs);
  const [postRunHydrationPending, setPostRunHydrationPending] = useState(false);
  const saveBlockedByBackendLock = hasActiveCodingRunLock || postRunHydrationPending;
  const [isOpeningApp, setIsOpeningApp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewRoute, setPreviewRoute] = useState("/");
  const [previewReloadToken, setPreviewReloadToken] = useState(0);
  const [previewMode, setPreviewMode] = useState<"preview" | "version_code">("preview");
  const [previewViewport, setPreviewViewport] = useState<"desktop" | "mobile">("desktop");
  const [isLogoDialogOpen, setIsLogoDialogOpen] = useState(false);
  const [domainCopied, setDomainCopied] = useState(false);
  const lastSavedCodeFingerprintRef = useRef<string>("");

  useEffect(() => {
    setOpen(false);
  }, [setOpen]);

  useEffect(() => {
    setUsers([]);
    setDomains([]);
    setHasLoadedUsers(false);
    setHasLoadedDomains(false);
    setPreviewRoute("/");
    setPreviewReloadToken(0);
    setPostRunHydrationPending(false);
  }, [appId]);

  const syncCurrentRevisionFromDraftDevSession = useCallback((revisionId: string) => {
    if (currentRevisionId) {
      return;
    }
    const normalizedRevisionId = revisionId.trim();
    if (!normalizedRevisionId) return;
    setCurrentRevisionId(normalizedRevisionId);
    setState((prev) => {
      if (!prev) return prev;
      if (prev.app.current_draft_revision_id === normalizedRevisionId) {
        return prev;
      }
      return {
        ...prev,
        app: {
          ...prev.app,
          current_draft_revision_id: normalizedRevisionId,
        },
      };
    });
  }, [currentRevisionId]);

  const applyDraftDevSessionToBuilderState = useCallback((session: DraftDevSessionResponse | null) => {
    setState((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        draft_dev: session,
      };
    });
  }, []);

  const {
    phase: sandboxPhase,
    draftDevStatus,
    draftDevError,
    previewAssetUrl,
    previewAuthToken,
    previewLoadingMessage,
    publishLockMessage,
    isReady: isSandboxReady,
    isBusy: isSandboxBusy,
    canRetry: canRetrySandboxLifecycle,
    actionDisabledReason: sandboxActionDisabledReason,
    hydrateFromBuilderSession,
    ensureDraftDevSession,
    retryEnsureDraftDevSession,
  } = useAppsBuilderSandboxLifecycle({
    appId,
    currentRevisionId,
    entryFile,
    files,
    hasActiveCodingRunLock,
    onSessionChange: applyDraftDevSessionToBuilderState,
    onRevisionFromSession: syncCurrentRevisionFromDraftDevSession,
  });
  const sandboxActionsBlocked = !isSandboxReady || isSandboxBusy;
  const sendBlockedReason = sandboxActionDisabledReason || "Waiting for preview sandbox...";

  const appRoutes = useMemo(() => extractRoutesFromFiles(files), [files]);
  const orderedTemplates = useMemo(() => sortTemplates(state?.templates || []), [state?.templates]);
  const platformDomain = useMemo(
    () => `${state?.app.slug || "app"}.${process.env.NEXT_PUBLIC_APPS_BASE_DOMAIN || "apps.localhost"}`,
    [state?.app.slug],
  );
  const previewFrameUrl = useMemo(() => {
    if (!previewAssetUrl) {
      return null;
    }
    return buildPreviewFrameUrl(previewAssetUrl, previewRoute, previewReloadToken);
  }, [previewAssetUrl, previewReloadToken, previewRoute]);
  const navigatePreview = useCallback((route: string) => {
    setPreviewRoute(route);
  }, []);

  const reloadPreview = useCallback(() => {
    setPreviewReloadToken((current) => current + 1);
  }, []);

  const hydrateFromRevision = useCallback((revision?: PublishedAppRevision | null) => {
    const nextFiles = filterAppsBuilderFiles(revision?.files || {});
    const nextEntry = revision?.entry_file || "src/main.tsx";
    setFiles(nextFiles);
    setEntryFile(nextEntry);
    setSelectedFile(Object.keys(nextFiles).sort()[0] || null);
    setCurrentRevisionId(revision?.id || null);
    lastSavedCodeFingerprintRef.current = buildDraftDevSyncFingerprint(nextEntry, nextFiles);
    setHasUnsavedManualCodeChanges(false);
  }, []);

  const loadState = useCallback(async ({ showInitialSkeleton = false }: { showInitialSkeleton?: boolean } = {}) => {
    if (showInitialSkeleton) {
      setIsInitialLoading(true);
    }
    setError(null);
    try {
      const response = await publishedAppsService.getBuilderState(appId);
      setState(response);
      hydrateFromRevision(response.current_draft_revision);
      hydrateFromBuilderSession(response.draft_dev);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load builder state");
    } finally {
      if (showInitialSkeleton) {
        setIsInitialLoading(false);
      }
    }
  }, [appId, hydrateFromBuilderSession, hydrateFromRevision]);

  const loadAuthTemplates = useCallback(async () => {
    setIsAuthTemplatesLoading(true);
    try {
      const authTemplateList = await publishedAppsService.listAuthTemplates();
      setAuthTemplates(authTemplateList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load auth templates");
    } finally {
      setIsAuthTemplatesLoading(false);
    }
  }, []);

  const refreshStateSilently = useCallback(async () => {
    try {
      const response = await publishedAppsService.getBuilderState(appId);
      setState(response);
      setCurrentRevisionId(response.current_draft_revision?.id || null);
      hydrateFromBuilderSession(response.draft_dev);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh builder state");
    }
  }, [appId, hydrateFromBuilderSession]);

  const {
    versions,
    selectedVersion,
    selectedVersionId,
    isLoadingVersions,
    isLoadingVersionPreview,
    isRestoringVersion,
    isPublishingVersion,
    publishStatus: versionPublishStatus,
    inspectedVersionId,
    inspectedPreviewUrl,
    inspectedRuntimeToken,
    inspectedPreviewNotice,
    refreshVersions,
    selectVersion,
    clearInspectedVersion,
    restoreSelectedVersion,
    publishSelectedVersion,
  } = useAppsBuilderVersions({
    appId,
    currentRevisionId,
    onApplyRevision: (revision) => {
      hydrateFromRevision(revision);
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
    },
    onRefreshState: async () => {
      await loadState();
    },
    onError: setError,
  });
  const publishStatus = versionPublishStatus;
  const isPublishing = isPublishingVersion;
  const isInspectingVersion = Boolean(inspectedVersionId);
  const publishDisabledReason = isPublishing
    ? "Publish in progress..."
    : postRunHydrationPending
      ? "Finalizing latest coding-agent changes..."
      : sandboxActionsBlocked
        ? sendBlockedReason
        : null;
  const isPublishDisabled = Boolean(publishDisabledReason);
  const inspectedPreviewFrameUrl = useMemo(() => {
    if (!inspectedPreviewUrl) {
      return null;
    }
    if (previewReloadToken <= 0) {
      return inspectedPreviewUrl;
    }
    try {
      const parsed = new URL(inspectedPreviewUrl);
      parsed.searchParams.set("__reload", String(previewReloadToken));
      return parsed.toString();
    } catch {
      const separator = inspectedPreviewUrl.includes("?") ? "&" : "?";
      return `${inspectedPreviewUrl}${separator}__reload=${previewReloadToken}`;
    }
  }, [inspectedPreviewUrl, previewReloadToken]);
  const effectivePreviewUrl = isInspectingVersion ? inspectedPreviewFrameUrl : previewFrameUrl;
  const effectivePreviewToken = isInspectingVersion ? inspectedRuntimeToken : previewAuthToken;
  const effectivePreviewStatus = isInspectingVersion ? "running" : draftDevStatus;
  const effectivePreviewError = isInspectingVersion ? inspectedPreviewNotice : draftDevError;
  const effectivePreviewPhase = isInspectingVersion ? null : sandboxPhase;
  const effectivePreviewLoadingMessage = isInspectingVersion
    ? (isLoadingVersionPreview ? "Loading selected version preview..." : null)
    : previewLoadingMessage;

  useEffect(() => {
    void loadState({ showInitialSkeleton: true });
    void loadAuthTemplates();
  }, [loadAuthTemplates, loadState]);

  useEffect(() => {
    if (!isInspectingVersion) {
      setPreviewMode("preview");
      return;
    }
    if (previewMode === "version_code") {
      return;
    }
    setPreviewMode("preview");
  }, [isInspectingVersion, previewMode]);

  useEffect(() => {
    if (!selectedVersion) {
      setSelectedVersionCodeFile(null);
      return;
    }
    const nextPaths = Object.keys(selectedVersion.files || {}).sort();
    setSelectedVersionCodeFile(nextPaths[0] || null);
  }, [selectedVersion]);

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

  const loadUsers = useCallback(async () => {
    setIsUsersLoading(true);
    try {
      const items = await publishedAppsService.listUsers(appId);
      setUsers(items);
      setHasLoadedUsers(true);
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
      setHasLoadedDomains(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load app domains");
    } finally {
      setIsDomainsLoading(false);
    }
  }, [appId]);

  useEffect(() => {
    if (activeTab !== "config") return;
    if (configSection === "users" && !hasLoadedUsers && !isUsersLoading) {
      void loadUsers();
      return;
    }
    if (configSection === "domains" && !hasLoadedDomains && !isDomainsLoading) {
      void loadDomains();
    }
  }, [activeTab, configSection, hasLoadedDomains, hasLoadedUsers, isDomainsLoading, isUsersLoading, loadDomains, loadUsers]);

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
    setPendingUserUpdateId(user.app_account_id);
    setError(null);
    try {
      const nextStatus = user.account_status === "blocked" ? "active" : "blocked";
      const updated = await publishedAppsService.updateUser(appId, user.app_account_id, {
        membership_status: nextStatus,
      });
      setUsers((prev) => prev.map((item) => (item.app_account_id === updated.app_account_id ? updated : item)));
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
    if (saveBlockedByBackendLock) {
      setError("Save is temporarily locked while a coding-agent run is active or finalizing latest changes.");
      return;
    }
    if (!currentRevisionId && Object.keys(files).length === 0) return;

    setIsSaving(true);
    setError(null);
    try {
      const revision = await publishedAppsService.createDraftVersion(appId, {
        base_revision_id: currentRevisionId || undefined,
        files: filterAppsBuilderFiles(files),
        entry_file: entryFile,
      });
      lastSavedCodeFingerprintRef.current = buildDraftDevSyncFingerprint(entryFile, files);
      setHasUnsavedManualCodeChanges(false);
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
      await ensureDraftDevSession();
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
  }, [appId, currentRevisionId, ensureDraftDevSession, entryFile, files, loadState, saveBlockedByBackendLock]);

  const publish = useCallback(async () => {
    if (sandboxActionsBlocked) {
      setError(sendBlockedReason);
      return;
    }
    setError(null);
    const publishVersionId = String(
      inspectedVersionId || currentRevisionId || selectedVersionId || "",
    ).trim();
    if (!publishVersionId) {
      setError("No version selected to publish.");
      return;
    }
    await publishSelectedVersion(publishVersionId);
  }, [
    currentRevisionId,
    inspectedVersionId,
    publishSelectedVersion,
    sandboxActionsBlocked,
    selectedVersionId,
    sendBlockedReason,
  ]);

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

  const ensureDraftDevSessionForChat = useCallback(async () => {
    await ensureDraftDevSession();
  }, [ensureDraftDevSession]);

  const {
    isAgentPanelOpen,
    setIsAgentPanelOpen,
    isSending,
    isStopping,
    timeline,
    activeThinkingSummary,
    chatSessions,
    activeChatSessionId,
    activateDraftChat,
    chatModels,
    setSelectedRunModelId,
    isModelSelectorOpen,
    setIsModelSelectorOpen,
    selectedRunModelLabel,
    queuedPrompts,
    pendingQuestion,
    isAnsweringQuestion,
    runningSessionIds,
    sendingSessionIds,
    sessionTitleHintsBySessionId,
    hasOlderHistory,
    isLoadingOlderHistory,
    loadOlderHistory,
    removeQueuedPrompt,
    answerPendingQuestion,
    refreshChatSessionRunActivity,
    sendBuilderChat,
    stopCurrentRun,
    startNewChat,
    loadChatSession,
  } = useAppsBuilderChat({
    appId,
    activeTab,
    ensureDraftDevSession: ensureDraftDevSessionForChat,
    refreshStateSilently,
    onPostRunHydrationStateChange: setPostRunHydrationPending,
    onSetCurrentRevisionId: setCurrentRevisionId,
    onError: setError,
    initialActiveRunId: null,
  });
  const codeEditingLocked = isSending || hasActiveCodingRunLock;
  const hasSessionRunActivity = runningSessionIds.length > 0 || sendingSessionIds.length > 0;
  const saveBlockedByRunState = saveBlockedByBackendLock || hasSessionRunActivity;

  const openApp = useCallback(async () => {
    setError(null);
    if (state?.app.status === "published") {
      const publishedUrl = state.app.published_url || null;
      if (publishedUrl) {
        window.open(publishedUrl, "_blank", "noopener,noreferrer");
        return;
      }
    }

    const inMemoryPreviewUrl =
      isDraftDevServingStatus(draftDevStatus) ? previewFrameUrl || state?.draft_dev?.preview_url || null : null;
    if (inMemoryPreviewUrl) {
      window.open(
        appendRuntimeTokenToUrl(inMemoryPreviewUrl, previewAuthToken || state?.draft_dev?.preview_auth_token || null),
        "_blank",
        "noopener,noreferrer",
      );
      return;
    }

    setIsOpeningApp(true);
    try {
      const ensuredSession = await ensureDraftDevSession({ force: true });
      const session = ensuredSession || state?.draft_dev || null;
      if (!session?.preview_url) {
        throw new Error("Draft preview URL is unavailable");
      }
      window.open(
        appendRuntimeTokenToUrl(session.preview_url, session.preview_auth_token || previewAuthToken),
        "_blank",
        "noopener,noreferrer",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open app");
    } finally {
      setIsOpeningApp(false);
    }
  }, [
    ensureDraftDevSession,
    state?.app.published_url,
    state?.app.status,
    state?.draft_dev?.preview_auth_token,
    state?.draft_dev?.preview_url,
    previewAuthToken,
    previewFrameUrl,
    draftDevStatus,
  ]);

  const deleteFile = (path: string) => {
    setFiles((prev) => {
      const next = { ...prev };
      delete next[path];
      const fingerprint = buildDraftDevSyncFingerprint(entryFile, next);
      setHasUnsavedManualCodeChanges(fingerprint !== lastSavedCodeFingerprintRef.current);
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

  if (isInitialLoading && !state) {
    return <AppsBuilderWorkspaceBootSkeleton previewViewport={previewViewport} />;
  }

  if (!state) {
    return (
      <div className="flex h-full w-full min-h-0 flex-col items-center justify-center gap-3 p-6 text-center">
        <div className="text-sm text-destructive">Builder state unavailable.</div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            void loadState({ showInitialSkeleton: true });
            void loadAuthTemplates();
          }}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <Tabs
      value={activeTab}
      onValueChange={(value) => setActiveTab(value as "preview" | "config")}
      className="flex h-dvh min-h-0 w-full overflow-hidden gap-0 bg-background"
    >
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-11 border-b shrink-0  items-center gap-3 px-3">
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
                        : isDraftDevServingStatus(draftDevStatus)
                          ? "bg-blue-500"
                          : isDraftDevFailureStatus(draftDevStatus)
                            ? "bg-destructive"
                            : "bg-muted-foreground/40",
                    )}
                  />
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {state.app.status === "published" ? "Published" : `Draft — ${draftDevStatus || "idle"}`}
                  {publishStatus ? ` · publish: ${publishStatus}` : ""}
                  {publishLockMessage ? ` · ${publishLockMessage}` : ""}
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
                  {isInspectingVersion ? (
                    <div className="flex h-7 items-center gap-1 rounded-md border border-border/60 bg-background px-1">
                      <Button
                        size="sm"
                        variant={previewMode === "preview" ? "secondary" : "ghost"}
                        className="h-5 px-2 text-[11px]"
                        onClick={() => setPreviewMode("preview")}
                      >
                        Preview
                      </Button>
                      <Button
                        size="sm"
                        variant={previewMode === "version_code" ? "secondary" : "ghost"}
                        className="h-5 px-2 text-[11px]"
                        onClick={() => setPreviewMode("version_code")}
                        disabled={!selectedVersion}
                      >
                        Version Code
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-5 w-5 text-muted-foreground hover:text-foreground"
                        onClick={() => {
                          clearInspectedVersion();
                          setPreviewMode("preview");
                        }}
                        aria-label="Exit version inspect mode"
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ) : (
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
                  )}

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

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7 text-muted-foreground hover:text-foreground"
                  onClick={() => setIsAgentPanelOpen(!isAgentPanelOpen)}
                  aria-label={isAgentPanelOpen ? "Close coding agent panel" : "Open coding agent panel"}
                >
                  {isAgentPanelOpen ? <PanelRightClose className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                {isAgentPanelOpen ? "Close coding agent panel" : "Open coding agent panel"}
              </TooltipContent>
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
                <span className="inline-flex">
                  <Button
                    size="sm"
                    className="h-7 gap-1.5 px-2.5 text-xs"
                    onClick={publish}
                    disabled={isPublishDisabled}
                  >
                    {isPublishing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Rocket className="h-3 w-3" />}
                    Publish
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                {publishDisabledReason || "Publish"}
              </TooltipContent>
            </Tooltip>
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
                      ? "w-[390px] overflow-hidden rounded-md border border-border/60 shadow-sm"
                      : "w-full",
                  )}>
                    {isInspectingVersion && previewMode === "version_code" ? (
                      <div className="flex h-full min-h-0">
                        <aside className="h-full w-72 shrink-0 border-r border-border/60 bg-background/95">
                          <FileTree
                            files={selectedVersion?.files || {}}
                            selectedFile={selectedVersionCodeFile}
                            onSelectFile={setSelectedVersionCodeFile}
                            onDeleteFile={() => {}}
                            readOnly
                          />
                        </aside>
                        <CodeEditorPanel
                          files={selectedVersion?.files || {}}
                          selectedFile={selectedVersionCodeFile}
                          onUpdateFile={() => {}}
                          readOnly
                        />
                      </div>
                    ) : (
                      <PreviewCanvas
                        previewUrl={effectivePreviewUrl}
                        previewAuthToken={effectivePreviewToken}
                        forceReady={isInspectingVersion}
                        devStatus={effectivePreviewStatus}
                        devError={effectivePreviewError}
                        lifecyclePhase={effectivePreviewPhase}
                        loadingMessage={effectivePreviewLoadingMessage}
                        canRetry={!isInspectingVersion && canRetrySandboxLifecycle}
                        onRetry={isInspectingVersion ? null : () => {
                          void retryEnsureDraftDevSession();
                        }}
                      />
                    )}
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
                    showCodeSaveButton={hasUnsavedManualCodeChanges}
                    onSaveCodeDraft={() => {
                      void saveDraft();
                    }}
                    isSavingCodeDraft={isSaving}
                    disableCodeSave={saveBlockedByRunState}
                  />

                  <section className={cn("min-w-0 flex-1", configSection === "code" ? "overflow-hidden" : "overflow-auto")}>
                    {configSection === "overview" && (
                      <div className="mx-auto max-w-2xl p-6 pb-10">
                        {/* ── App Identity Hero ── */}
                        <div className="flex items-start gap-5">
                          <button
                            type="button"
                            onClick={() => setIsLogoDialogOpen(true)}
                            className="group relative h-16 w-16 shrink-0 overflow-hidden rounded-lg border border-border/60 bg-muted/40 shadow-sm transition-all hover:shadow-md"
                          >
                            {state.app.logo_url ? (
                              <img src={state.app.logo_url} alt="" className="h-full w-full object-cover" />
                            ) : (
                              <span className="flex h-full w-full items-center justify-center text-xl font-bold text-primary/60">
                                {state.app.name?.charAt(0)?.toUpperCase() || "A"}
                              </span>
                            )}
                            <div className="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/40">
                              <Camera className="h-4 w-4 text-white opacity-0 transition-opacity group-hover:opacity-100" />
                            </div>
                          </button>
                          <div className="min-w-0 flex-1 space-y-2 pt-0.5">
                            <Input
                              value={state.app.name}
                              onChange={(event) => updateLocalApp({ name: event.target.value })}
                              className="h-auto border-0 bg-transparent p-0 text-lg font-semibold shadow-none focus-visible:ring-0"
                              placeholder="App name..."
                            />
                            <Textarea
                              value={state.app.description || ""}
                              onChange={(event) => updateLocalApp({ description: event.target.value })}
                              placeholder="What does your app do?"
                              className="min-h-0 resize-none border-0 bg-transparent p-0 text-sm text-muted-foreground shadow-none focus-visible:ring-0"
                              rows={2}
                            />
                          </div>
                        </div>

                        <LogoPickerDialog
                          open={isLogoDialogOpen}
                          onOpenChange={setIsLogoDialogOpen}
                          currentUrl={state.app.logo_url || ""}
                          onSave={(url) => updateLocalApp({ logo_url: url })}
                        />

                        {/* ── Visibility ── */}
                        <div className="mt-8 space-y-3">
                          <Label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Visibility</Label>
                          <div className="grid grid-cols-2 gap-2">
                            <button
                              type="button"
                              onClick={() => updateLocalApp({ visibility: "public" })}
                              className={cn(
                                "flex items-center gap-3 rounded-md border px-4 py-3.5 text-left transition-all",
                                state.app.visibility === "public"
                                  ? "border-primary/30 bg-primary/5 shadow-sm ring-1 ring-primary/20"
                                  : "border-border/60 hover:border-border hover:bg-muted/50",
                              )}
                            >
                              <div className={cn(
                                "flex h-9 w-9 items-center justify-center rounded-lg",
                                state.app.visibility === "public" ? "bg-primary/10" : "bg-muted",
                              )}>
                                <Globe className={cn("h-4 w-4", state.app.visibility === "public" ? "text-primary" : "text-muted-foreground")} />
                              </div>
                              <div>
                                <div className="text-sm font-medium">Public</div>
                                <div className="text-xs text-muted-foreground">Anyone with the link</div>
                              </div>
                            </button>
                            <button
                              type="button"
                              onClick={() => updateLocalApp({ visibility: "private" })}
                              className={cn(
                                "flex items-center gap-3 rounded-md border px-4 py-3.5 text-left transition-all",
                                state.app.visibility === "private"
                                  ? "border-primary/30 bg-primary/5 shadow-sm ring-1 ring-primary/20"
                                  : "border-border/60 hover:border-border hover:bg-muted/50",
                              )}
                            >
                              <div className={cn(
                                "flex h-9 w-9 items-center justify-center rounded-lg",
                                state.app.visibility === "private" ? "bg-primary/10" : "bg-muted",
                              )}>
                                <Lock className={cn("h-4 w-4", state.app.visibility === "private" ? "text-primary" : "text-muted-foreground")} />
                              </div>
                              <div>
                                <div className="text-sm font-medium">Private</div>
                                <div className="text-xs text-muted-foreground">Only invited users</div>
                              </div>
                            </button>
                          </div>
                        </div>

                        {/* ── Auth Template ── */}
                        <div className="mt-6 space-y-3">
                          <Label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Auth Template</Label>
                          {isAuthTemplatesLoading && authTemplates.length === 0 ? (
                            <Skeleton className="h-10 w-full rounded-lg" />
                          ) : (
                            <Select
                              value={state.app.auth_template_key}
                              onValueChange={(value) => updateLocalApp({ auth_template_key: value })}
                            >
                              <SelectTrigger className="rounded-md">
                                <SelectValue placeholder="Select template..." />
                              </SelectTrigger>
                              <SelectContent>
                                {authTemplates.map((item) => (
                                  <SelectItem key={item.key} value={item.key}>
                                    {item.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          )}
                        </div>

                        {/* ── Authentication ── */}
                        <div className="mt-8 space-y-4">
                          <div className="flex items-center gap-2">
                            <Shield className="h-4 w-4 text-muted-foreground" />
                            <Label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Authentication</Label>
                          </div>

                          <label className={cn(
                            "flex cursor-pointer items-center justify-between rounded-md border px-4 py-4 transition-all",
                            state.app.auth_enabled
                              ? "border-primary/30 bg-primary/5 ring-1 ring-primary/20"
                              : "border-border/60 hover:bg-muted/30",
                          )}>
                            <div className="flex items-center gap-3">
                              <div className={cn(
                                "flex h-9 w-9 items-center justify-center rounded-lg",
                                state.app.auth_enabled ? "bg-primary/10" : "bg-muted",
                              )}>
                                <Shield className={cn("h-4 w-4", state.app.auth_enabled ? "text-primary" : "text-muted-foreground")} />
                              </div>
                              <div>
                                <div className="text-sm font-medium">Require login</div>
                                <div className="text-xs text-muted-foreground">Users must sign in to access this app</div>
                              </div>
                            </div>
                            <Checkbox
                              checked={state.app.auth_enabled}
                              onCheckedChange={(checked) => updateLocalApp({ auth_enabled: checked === true })}
                            />
                          </label>

                          <div className="grid grid-cols-2 gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                const current = new Set(state.app.auth_providers || []);
                                if (current.has("password")) current.delete("password");
                                else current.add("password");
                                updateLocalApp({ auth_providers: Array.from(current) });
                              }}
                              className={cn(
                                "flex items-center gap-3 rounded-md border px-4 py-3 text-left transition-all",
                                (state.app.auth_providers || []).includes("password")
                                  ? "border-primary/30 bg-primary/5 ring-1 ring-primary/20"
                                  : "border-border/60 hover:border-border hover:bg-muted/50",
                              )}
                            >
                              <KeyRound className={cn(
                                "h-4 w-4",
                                (state.app.auth_providers || []).includes("password") ? "text-primary" : "text-muted-foreground",
                              )} />
                              <div>
                                <div className="text-sm font-medium">Password</div>
                                <div className="text-xs text-muted-foreground">Email & password</div>
                              </div>
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                const current = new Set(state.app.auth_providers || []);
                                if (current.has("google")) current.delete("google");
                                else current.add("google");
                                updateLocalApp({ auth_providers: Array.from(current) });
                              }}
                              className={cn(
                                "flex items-center gap-3 rounded-md border px-4 py-3 text-left transition-all",
                                (state.app.auth_providers || []).includes("google")
                                  ? "border-primary/30 bg-primary/5 ring-1 ring-primary/20"
                                  : "border-border/60 hover:border-border hover:bg-muted/50",
                              )}
                            >
                              <svg className={cn(
                                "h-4 w-4",
                                (state.app.auth_providers || []).includes("google") ? "text-primary" : "text-muted-foreground",
                              )} viewBox="0 0 24 24" fill="currentColor">
                                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                              </svg>
                              <div>
                                <div className="text-sm font-medium">Google</div>
                                <div className="text-xs text-muted-foreground">Sign in with Google</div>
                              </div>
                            </button>
                          </div>
                        </div>

                        {/* ── Save ── */}
                        <div className="mt-8">
                          <Button className="w-full rounded-md" size="lg" onClick={saveOverview} disabled={isSavingOverview}>
                            {isSavingOverview ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                            Save Changes
                          </Button>
                        </div>
                      </div>
                    )}

                    {configSection === "users" && (
                      <div className="mx-auto max-w-2xl p-6">
                        <div className="mb-5">
                          <h3 className="text-lg font-semibold tracking-tight">Users</h3>
                          <p className="text-sm text-muted-foreground">Manage who has access to your app.</p>
                        </div>
                        {isUsersLoading && users.length === 0 ? <UsersListSkeleton /> : null}
                        <div className={cn("space-y-2", isUsersLoading && users.length === 0 ? "hidden" : "")}>
                          {users.map((user) => (
                            <div key={user.app_account_id} className="flex items-center gap-3 rounded-md border border-border/60 px-4 py-3 transition-colors hover:bg-muted/30">
                              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-xs font-semibold text-primary">
                                {(user.full_name || user.email).charAt(0).toUpperCase()}
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="truncate text-sm font-medium">{user.full_name || user.email}</div>
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                  <span className="truncate">{user.email}</span>
                                  <span className="shrink-0">·</span>
                                  <span className="shrink-0">{user.active_sessions} sessions</span>
                                  <Badge
                                    variant="secondary"
                                    className={cn(
                                      "text-[10px]",
                                      user.account_status === "active" && "bg-emerald-500/15 text-emerald-600 border-emerald-500/20",
                                      user.account_status === "blocked" && "bg-red-500/15 text-red-600 border-red-500/20",
                                    )}
                                  >
                                    {user.account_status}
                                  </Badge>
                                </div>
                              </div>
                              <Button
                                size="sm"
                                variant={user.account_status === "blocked" ? "default" : "outline"}
                                className="shrink-0 rounded-lg"
                                onClick={() => toggleUserBlocked(user)}
                                disabled={pendingUserUpdateId === user.app_account_id}
                              >
                                {pendingUserUpdateId === user.app_account_id ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : null}
                                {user.account_status === "blocked" ? "Unblock" : "Block"}
                              </Button>
                            </div>
                          ))}
                          {!isUsersLoading && users.length === 0 ? (
                            <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border/60 py-12 text-center">
                              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
                                <Globe className="h-5 w-5 text-muted-foreground" />
                              </div>
                              <p className="text-sm text-muted-foreground">No users yet</p>
                              <p className="text-xs text-muted-foreground/60">Users will appear here once they access your app.</p>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )}

                    {configSection === "domains" && (
                      <div className="mx-auto max-w-2xl p-6 pb-10">
                        <div className="mb-6">
                          <h3 className="text-lg font-semibold tracking-tight">Domains</h3>
                          <p className="text-sm text-muted-foreground">Manage your app&apos;s domain configuration.</p>
                        </div>

                        {/* ── Platform Domain ── */}
                        <div className="rounded-md border border-border/60 bg-muted/30 p-5">
                          <div className="flex items-center justify-between">
                            <Label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Platform Domain</Label>
                            <Badge variant="secondary" className="text-[10px]">Default</Badge>
                          </div>
                          <div className="mt-3 flex items-center gap-2">
                            <code className="flex-1 truncate text-base font-medium tracking-tight">{platformDomain}</code>
                            <Button
                              variant="outline"
                              size="icon"
                              className="h-8 w-8 shrink-0 rounded-lg"
                              onClick={() => {
                                navigator.clipboard.writeText(platformDomain);
                                setDomainCopied(true);
                                setTimeout(() => setDomainCopied(false), 2000);
                              }}
                            >
                              {domainCopied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                            </Button>
                          </div>
                        </div>

                        {/* ── Add Domain Form ── */}
                        <div className="mt-6 rounded-md border border-border/60 p-5">
                          <div className="flex items-center gap-2">
                            <Plus className="h-4 w-4 text-muted-foreground" />
                            <Label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Add Custom Domain</Label>
                          </div>
                          <div className="mt-3 flex gap-2">
                            <Input
                              value={domainHostInput}
                              onChange={(event) => setDomainHostInput(event.target.value)}
                              placeholder="app.example.com"
                              className="flex-1 rounded-md"
                            />
                            <Input
                              value={domainNotesInput}
                              onChange={(event) => setDomainNotesInput(event.target.value)}
                              placeholder="Notes (optional)"
                              className="w-40 rounded-md"
                            />
                            <Button className="shrink-0 rounded-md" onClick={addDomain} disabled={isAddingDomain || !domainHostInput.trim()}>
                              {isAddingDomain ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
                              Add
                            </Button>
                          </div>
                        </div>

                        {/* ── Domains List ── */}
                        <div className="mt-6">
                          {isDomainsLoading && domains.length === 0 ? <DomainsListSkeleton /> : null}
                          {!isDomainsLoading && domains.length === 0 ? (
                            <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border/60 py-12 text-center">
                              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
                                <Globe className="h-5 w-5 text-muted-foreground" />
                              </div>
                              <p className="text-sm text-muted-foreground">No custom domains</p>
                              <p className="text-xs text-muted-foreground/60">Add a custom domain to use your own branding.</p>
                            </div>
                          ) : null}
                          {domains.length > 0 && (
                            <div className="space-y-2">
                              {domains.map((domain) => (
                                <div key={domain.id} className="group flex items-center gap-3 rounded-md border border-border/60 px-4 py-3 transition-colors hover:bg-muted/30">
                                  <div className={cn(
                                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                                    domain.status === "approved" ? "bg-emerald-500/10" : "bg-amber-500/10",
                                  )}>
                                    <Globe className={cn(
                                      "h-4 w-4",
                                      domain.status === "approved" ? "text-emerald-500" : "text-amber-500",
                                    )} />
                                  </div>
                                  <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2">
                                      <span className="truncate text-sm font-medium">{domain.host}</span>
                                      <Badge
                                        variant="secondary"
                                        className={cn(
                                          "text-[10px]",
                                          domain.status === "approved" && "bg-emerald-500/15 text-emerald-600 border-emerald-500/20",
                                          domain.status === "pending" && "bg-amber-500/15 text-amber-600 border-amber-500/20",
                                          domain.status === "rejected" && "bg-red-500/15 text-red-600 border-red-500/20",
                                        )}
                                      >
                                        {domain.status}
                                      </Badge>
                                    </div>
                                    {domain.notes && (
                                      <p className="mt-0.5 truncate text-xs text-muted-foreground">{domain.notes}</p>
                                    )}
                                  </div>
                                  {domain.status === "pending" && (
                                    <Button
                                      size="icon"
                                      variant="ghost"
                                      className="h-8 w-8 shrink-0 rounded-lg text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                                      onClick={() => removeDomain(domain.id)}
                                      disabled={pendingDomainDeleteId === domain.id}
                                    >
                                      {pendingDomainDeleteId === domain.id ? (
                                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                      ) : (
                                        <Trash2 className="h-3.5 w-3.5" />
                                      )}
                                    </Button>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {configSection === "code" && (
                      <CodeEditorPanel
                        files={files}
                        selectedFile={selectedFile}
                        onUpdateFile={(path, content) => {
                          if (codeEditingLocked) return;
                          if (isAppsBuilderBlockedFilePath(path)) return;
                          setFiles((prev) => {
                            const next = { ...prev, [path]: content };
                            const fingerprint = buildDraftDevSyncFingerprint(entryFile, next);
                            setHasUnsavedManualCodeChanges(fingerprint !== lastSavedCodeFingerprintRef.current);
                            return next;
                          });
                        }}
                        readOnly={codeEditingLocked}
                      />
                    )}
                  </section>
                </div>
              )}
            </div>
          </main>

          <AppsBuilderChatPanel
            isOpen={isAgentPanelOpen}
            isSending={isSending}
            isStopping={isStopping}
            timeline={timeline}
            activeThinkingSummary={activeThinkingSummary}
            chatSessions={chatSessions}
            activeChatSessionId={activeChatSessionId}
            onActivateDraftChat={activateDraftChat}
            onStartNewChat={() => {
              clearInspectedVersion();
              setPreviewMode("preview");
              startNewChat();
            }}
            onOpenHistory={() => {
              void refreshChatSessionRunActivity();
            }}
            onLoadChatSession={loadChatSession}
            onSendMessage={async (text) => {
              clearInspectedVersion();
              setPreviewMode("preview");
              await sendBuilderChat(text);
            }}
            onStopRun={stopCurrentRun}
            chatModels={chatModels}
            selectedRunModelLabel={selectedRunModelLabel}
            isModelSelectorOpen={isModelSelectorOpen}
            onModelSelectorOpenChange={setIsModelSelectorOpen}
            onSelectModelId={setSelectedRunModelId}
            queuedPrompts={queuedPrompts}
            pendingQuestion={pendingQuestion}
            isAnsweringQuestion={isAnsweringQuestion}
            isSendBlockedBySandbox={sandboxActionsBlocked}
            sendBlockedReason={sendBlockedReason}
            runningSessionIds={runningSessionIds}
            sendingSessionIds={sendingSessionIds}
            sessionTitleHintsBySessionId={sessionTitleHintsBySessionId}
            hasOlderHistory={hasOlderHistory}
            isLoadingOlderHistory={isLoadingOlderHistory}
            onLoadOlderHistory={loadOlderHistory}
            onRemoveQueuedPrompt={removeQueuedPrompt}
            onAnswerQuestion={answerPendingQuestion}
            versions={versions}
            selectedVersionId={selectedVersionId}
            selectedVersion={selectedVersion}
            isLoadingVersions={isLoadingVersions}
            isRestoringVersion={isRestoringVersion}
            isPublishingVersion={isPublishingVersion}
            publishStatus={versionPublishStatus}
            onRefreshVersions={() => {
              void refreshVersions();
            }}
            onSelectVersion={(versionId) => {
              void selectVersion(versionId).then(() => {
                setPreviewMode("preview");
                setActiveTab("preview");
              });
            }}
            onRestoreVersion={(versionId) => {
              void restoreSelectedVersion(versionId);
            }}
            onPublishVersion={(versionId) => {
              void publishSelectedVersion(versionId);
            }}
            onViewCodeVersion={(versionId) => {
              void selectVersion(versionId).then(() => {
                setPreviewMode("version_code");
                setActiveTab("preview");
              });
            }}
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
