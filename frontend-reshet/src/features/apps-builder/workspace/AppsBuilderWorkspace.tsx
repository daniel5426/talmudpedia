"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  ArrowLeft,
  Camera,
  Check,
  Copy,
  Download,
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
import { Command, CommandEmpty, CommandGroup, CommandItem, CommandList } from "@/components/ui/command";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useSidebar } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  agentService,
  isDraftDevFailureStatus,
  isDraftDevServingStatus,
  publishedAppsService,
} from "@/services";
import type {
  Agent,
  BuilderStateResponse,
  DraftDevSessionResponse,
  PublishedAppAuthTemplate,
  PublishedAppDomain,
  PublishedAppExportOptions,
  PublishedAppRevision,
  PublishedAppUser,
  RevisionConflictResponse,
} from "@/services";
import { filterAppsBuilderFiles, isAppsBuilderBlockedFilePath } from "@/services/apps-builder-file-filter";
import { cn } from "@/lib/utils";
import { sortTemplates } from "@/features/apps-builder/templates";
import { PreviewCanvas } from "@/features/apps-builder/preview/PreviewCanvas";
import { buildBuilderPreviewLoadingState } from "@/features/apps-builder/preview/previewLoadingState";
import {
  buildBuilderPreviewDocumentUrl,
  logBuilderPreviewDebug,
} from "@/features/apps-builder/preview/previewTransport";
import { useBuilderLivePreviewStatus } from "@/features/apps-builder/preview/useBuilderLivePreviewStatus";
import { useBuilderPreviewTransport } from "@/features/apps-builder/preview/useBuilderPreviewTransport";
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
type WorkspaceSource = "live_session" | "durable_revision" | "materialized_run";

type BuilderWorkspaceState = {
  files: Record<string, string>;
  entryFile: string;
  selectedFile: string | null;
  revisionId: string | null;
  workspaceRevisionToken: string | null;
  workspaceSource: WorkspaceSource;
  dirty: boolean;
  conflict: boolean;
  notice: string | null;
};

type BuilderWorkspaceHydrationPayload = {
  files: Record<string, string>;
  entryFile: string;
  revisionId?: string | null;
  workspaceRevisionToken?: string | null;
  workspaceSource: WorkspaceSource;
  notice?: string | null;
  conflict?: boolean;
  preserveSelection?: boolean;
};

type BuilderWorkspaceAction =
  | { type: "reset" }
  | { type: "hydrate"; payload: BuilderWorkspaceHydrationPayload }
  | { type: "update_file"; path: string; content: string }
  | { type: "delete_file"; path: string }
  | { type: "select_file"; path: string | null }
  | { type: "clear_notice" };

const DEFAULT_ENTRY_FILE = "src/main.tsx";

function firstWorkspaceFile(files: Record<string, string>): string | null {
  return Object.keys(files).sort()[0] || null;
}

function resolveWorkspaceSelection(
  files: Record<string, string>,
  nextSelected: string | null | undefined,
  fallbackSelected: string | null | undefined,
): string | null {
  const primary = String(nextSelected || "").trim();
  if (primary && files[primary] !== undefined) {
    return primary;
  }
  const fallback = String(fallbackSelected || "").trim();
  if (fallback && files[fallback] !== undefined) {
    return fallback;
  }
  return firstWorkspaceFile(files);
}

function createEmptyWorkspaceState(): BuilderWorkspaceState {
  return {
    files: {},
    entryFile: DEFAULT_ENTRY_FILE,
    selectedFile: null,
    revisionId: null,
    workspaceRevisionToken: null,
    workspaceSource: "durable_revision",
    dirty: false,
    conflict: false,
    notice: null,
  };
}

function builderWorkspaceReducer(state: BuilderWorkspaceState, action: BuilderWorkspaceAction): BuilderWorkspaceState {
  switch (action.type) {
    case "reset":
      return createEmptyWorkspaceState();
    case "hydrate": {
      const nextFiles = filterAppsBuilderFiles(action.payload.files || {});
      const nextEntryFile = String(action.payload.entryFile || DEFAULT_ENTRY_FILE).trim() || DEFAULT_ENTRY_FILE;
      return {
        files: nextFiles,
        entryFile: nextEntryFile,
        selectedFile: action.payload.preserveSelection
          ? resolveWorkspaceSelection(nextFiles, state.selectedFile, state.selectedFile)
          : resolveWorkspaceSelection(nextFiles, null, null),
        revisionId: String(action.payload.revisionId || "").trim() || null,
        workspaceRevisionToken: String(action.payload.workspaceRevisionToken || "").trim() || null,
        workspaceSource: action.payload.workspaceSource,
        dirty: false,
        conflict: Boolean(action.payload.conflict),
        notice: action.payload.notice || null,
      };
    }
    case "update_file": {
      const nextFiles = {
        ...state.files,
        [action.path]: action.content,
      };
      return {
        ...state,
        files: nextFiles,
        selectedFile: resolveWorkspaceSelection(nextFiles, action.path, state.selectedFile),
        dirty: true,
        conflict: false,
        notice: null,
      };
    }
    case "delete_file": {
      const nextFiles = { ...state.files };
      delete nextFiles[action.path];
      return {
        ...state,
        files: nextFiles,
        selectedFile: resolveWorkspaceSelection(nextFiles, null, state.selectedFile === action.path ? null : state.selectedFile),
        dirty: true,
        conflict: false,
        notice: null,
      };
    }
    case "select_file":
      return {
        ...state,
        selectedFile: action.path,
      };
    case "clear_notice":
      return {
        ...state,
        notice: null,
        conflict: false,
      };
    default:
      return state;
  }
}

function normalizeRoutePath(route: string): string | null {
  const trimmed = String(route || "").trim();
  if (!trimmed || trimmed.includes("${")) return null;
  const [pathname] = trimmed.split(/[?#]/);
  if (!pathname) return null;
  const normalized = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const compact = normalized.replace(/\/{2,}/g, "/");
  if (compact !== "/" && compact.endsWith("/")) {
    return compact.slice(0, -1);
  }
  return compact || "/";
}

function isAssetLikeRoute(route: string): boolean {
  if (!route || route === "/") return false;
  const lastSegment = route.split("/").filter(Boolean).pop() || "";
  return /\.[a-z0-9]{2,8}$/i.test(lastSegment);
}

function routeFromFilePath(filePath: string): string | null {
  const normalized = filePath.replace(/\\/g, "/");
  const appMatch = normalized.match(/(?:^|\/)(?:src\/)?app\/(.+)\/page\.(?:tsx|ts|jsx|js|mdx)$/);
  if (appMatch) {
    const segments = appMatch[1]
      .split("/")
      .filter(Boolean)
      .filter((segment) => !segment.startsWith("(") && !segment.startsWith("@"));
    if (segments.some((segment) => segment.startsWith("[") || segment.startsWith(":"))) {
      return null;
    }
    return normalizeRoutePath(`/${segments.join("/")}`);
  }

  const pagesMatch = normalized.match(/(?:^|\/)(?:src\/)?pages\/(.+)\.(?:tsx|ts|jsx|js|mdx)$/);
  if (pagesMatch) {
    const relativePath = pagesMatch[1].replace(/\/index$/, "");
    if (!relativePath || relativePath === "index") {
      return "/";
    }
    if (relativePath.startsWith("api/")) {
      return null;
    }
    if (relativePath.split("/").some((segment) => segment.startsWith("[") || segment.startsWith(":"))) {
      return null;
    }
    return normalizeRoutePath(`/${relativePath}`);
  }

  return null;
}

/** Extract route paths from app source files by matching router usage and file-based routes. */
function extractRoutesFromFiles(files: Record<string, string>): string[] {
  const routes = new Set<string>();
  routes.add("/");

  for (const [filePath, content] of Object.entries(files)) {
    const fileRoute = routeFromFilePath(filePath);
    if (fileRoute && !isAssetLikeRoute(fileRoute)) {
      routes.add(fileRoute);
    }

    // Match <Route path="/something" ... />
    const jsxRouteRe = /path\s*[=:]\s*["'`](\/[^"'`]*)["'`]/g;
    let match: RegExpExecArray | null;
    while ((match = jsxRouteRe.exec(content)) !== null) {
      const route = normalizeRoutePath(match[1]);
      if (route && !route.includes(":") && !isAssetLikeRoute(route)) {
        routes.add(route);
      }
    }

    // Match navigate("/something")
    const navigateRe = /navigate\(\s*["'`](\/[^"'`]*)["'`]/g;
    while ((match = navigateRe.exec(content)) !== null) {
      const route = normalizeRoutePath(match[1]);
      if (route && !route.includes(":") && !isAssetLikeRoute(route)) {
        routes.add(route);
      }
    }

    // Match href="/something", to="/something", pathname: "/something"
    const linkToRe = /(?:href|to|pathname)\s*[:=]\s*["'`](\/[^"'`]*)["'`]/g;
    while ((match = linkToRe.exec(content)) !== null) {
      const route = normalizeRoutePath(match[1]);
      if (route && !route.includes(":") && !isAssetLikeRoute(route)) {
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

const POST_RUN_PREVIEW_POLL_WINDOW_MS = 90_000;

function logBuilderWorkspaceDebug(event: string, fields: Record<string, unknown> = {}): void {
  if (typeof console === "undefined" || typeof console.info !== "function") {
    return;
  }
  console.info("[apps-builder][workspace-state]", {
    event,
    ...fields,
  });
}

function extractLiveWorkspaceSnapshot(session?: DraftDevSessionResponse | null): PublishedAppRevision | null {
  const snapshot = session?.live_workspace_snapshot;
  if (!snapshot || !snapshot.files || typeof snapshot.files !== "object") {
    return null;
  }
  return {
    id: String(snapshot.revision_id || session?.revision_id || ""),
    published_app_id: String(session?.app_id || ""),
    kind: "draft",
    template_key: "classic-chat",
    entry_file: String(snapshot.entry_file || "src/main.tsx"),
    files: Object.fromEntries(
      Object.entries(snapshot.files).map(([path, content]) => [String(path), String(content ?? "")]),
    ),
    created_at: String(snapshot.updated_at || new Date().toISOString()),
  };
}

export function AppsBuilderWorkspace({ appId }: WorkspaceProps) {
  const { setOpen } = useSidebar();
  const [state, setState] = useState<BuilderStateResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"preview" | "config">("preview");
  const [configSection, setConfigSection] = useState<ConfigSection>("overview");
  const [lastNonCodeConfigSection, setLastNonCodeConfigSection] = useState<Exclude<ConfigSection, "code">>("overview");
  const [workspaceState, dispatchWorkspace] = useReducer(builderWorkspaceReducer, undefined, createEmptyWorkspaceState);
  const {
    files,
    entryFile,
    selectedFile,
    revisionId: currentRevisionId,
    workspaceRevisionToken,
    workspaceSource,
    dirty: hasUnsavedManualCodeChanges,
    conflict: workspaceConflict,
    notice: workspaceNotice,
  } = workspaceState;
  const [selectedVersionCodeFile, setSelectedVersionCodeFile] = useState<string | null>(null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isAuthTemplatesLoading, setIsAuthTemplatesLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingOverview, setIsSavingOverview] = useState(false);
  const [isAgentsLoading, setIsAgentsLoading] = useState(true);
  const [authTemplates, setAuthTemplates] = useState<PublishedAppAuthTemplate[]>([]);
  const [availableAgents, setAvailableAgents] = useState<Agent[]>([]);
  const [users, setUsers] = useState<PublishedAppUser[]>([]);
  const [domains, setDomains] = useState<PublishedAppDomain[]>([]);
  const draftDevSession = state?.draft_dev ?? null;
  const [hasLoadedUsers, setHasLoadedUsers] = useState(false);
  const [hasLoadedDomains, setHasLoadedDomains] = useState(false);
  const [isUsersLoading, setIsUsersLoading] = useState(false);
  const [isDomainsLoading, setIsDomainsLoading] = useState(false);
  const [isAddingDomain, setIsAddingDomain] = useState(false);
  const [domainHostInput, setDomainHostInput] = useState("");
  const [domainNotesInput, setDomainNotesInput] = useState("");
  const [pendingUserUpdateId, setPendingUserUpdateId] = useState<string | null>(null);
  const [pendingDomainDeleteId, setPendingDomainDeleteId] = useState<string | null>(null);
  const hasActiveCodingRunLock = Boolean(draftDevSession?.has_active_coding_runs);
  const [postRunHydrationPending, setPostRunHydrationPending] = useState(false);
  const [postRunPreviewPollState, setPostRunPreviewPollState] = useState<{
    until: number;
    baselineBuildId: string | null;
  } | null>(null);
  const saveBlockedByBackendLock = hasActiveCodingRunLock || postRunHydrationPending;
  const [isOpeningApp, setIsOpeningApp] = useState(false);
  const [isExportingArchive, setIsExportingArchive] = useState(false);
  const [exportOptions, setExportOptions] = useState<PublishedAppExportOptions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewRoute, setPreviewRoute] = useState("/");
  const [previewRouteInput, setPreviewRouteInput] = useState("/");
  const [isPreviewRoutePickerOpen, setIsPreviewRoutePickerOpen] = useState(false);
  const [previewReloadToken, setPreviewReloadToken] = useState(0);
  const [previewMode, setPreviewMode] = useState<"preview" | "version_code">("preview");
  const [previewViewport, setPreviewViewport] = useState<"desktop" | "mobile">("desktop");
  const [isLogoDialogOpen, setIsLogoDialogOpen] = useState(false);
  const [domainCopied, setDomainCopied] = useState(false);
  const lastSavedCodeFingerprintRef = useRef<string>("");
  const initializedAppIdRef = useRef<string | null>(null);

  useEffect(() => {
    setOpen(false);
  }, [setOpen]);

  useEffect(() => {
    setUsers([]);
    setDomains([]);
    setHasLoadedUsers(false);
    setHasLoadedDomains(false);
    setPreviewRoute("/");
    setPreviewRouteInput("/");
    setPreviewReloadToken(0);
    setPostRunHydrationPending(false);
    dispatchWorkspace({ type: "reset" });
  }, [appId]);

  const syncCurrentRevisionFromDraftDevSession = useCallback((revisionId: string) => {
    if (currentRevisionId) {
      return;
    }
    const normalizedRevisionId = revisionId.trim();
    if (!normalizedRevisionId) return;
    dispatchWorkspace({
      type: "hydrate",
      payload: {
        files,
        entryFile,
        revisionId: normalizedRevisionId,
        workspaceRevisionToken,
        workspaceSource,
        preserveSelection: true,
      },
    });
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
  }, [currentRevisionId, entryFile, files, workspaceRevisionToken, workspaceSource]);

  const hydrateWorkspaceFromRevision = useCallback((revision?: PublishedAppRevision | null) => {
    dispatchWorkspace({
      type: "hydrate",
      payload: {
        files: filterAppsBuilderFiles(revision?.files || {}),
        entryFile: revision?.entry_file || DEFAULT_ENTRY_FILE,
        revisionId: revision?.id || null,
        workspaceSource: "durable_revision",
      },
    });
  }, []);

  const applyDraftDevSessionToBuilderState = useCallback((session: DraftDevSessionResponse | null) => {
    setState((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        draft_dev: session,
      };
    });
    const liveSnapshotRevision = extractLiveWorkspaceSnapshot(session);
    logBuilderWorkspaceDebug("draft_dev_session_applied", {
      sessionId: session?.session_id || null,
      draftDevStatus: session?.status || null,
      livePreviewStatus: session?.live_preview?.status || null,
      livePreviewCurrentBuildId: session?.live_preview?.current_build_id || null,
      livePreviewLastSuccessfulBuildId: session?.live_preview?.last_successful_build_id || null,
      livePreviewUpdatedAt: session?.live_preview?.updated_at || null,
      liveSnapshotRevisionToken: session?.live_workspace_snapshot?.revision_token || null,
      liveSnapshotUpdatedAt: session?.live_workspace_snapshot?.updated_at || null,
      liveSnapshotFileCount: session?.live_workspace_snapshot?.files ? Object.keys(session.live_workspace_snapshot.files).length : 0,
    });
    if (!liveSnapshotRevision) {
      return;
    }
    const nextFiles = filterAppsBuilderFiles(liveSnapshotRevision.files || {});
    const nextEntry = liveSnapshotRevision.entry_file || DEFAULT_ENTRY_FILE;
    const nextFingerprint = buildDraftDevSyncFingerprint(nextEntry, nextFiles);
    const currentFingerprint = buildDraftDevSyncFingerprint(entryFile, files);
    const replacedDirtyLocalState = workspaceState.dirty && nextFingerprint !== currentFingerprint;
    dispatchWorkspace({
      type: "hydrate",
      payload: {
        files: nextFiles,
        entryFile: nextEntry,
        revisionId: liveSnapshotRevision.id || null,
        workspaceRevisionToken: session?.workspace_revision_token || session?.live_workspace_snapshot?.revision_token || null,
        workspaceSource: postRunHydrationPending ? "materialized_run" : "live_session",
        preserveSelection: true,
        notice: replacedDirtyLocalState ? "Workspace refreshed from live sandbox changes." : null,
        conflict: replacedDirtyLocalState,
      },
    });
    lastSavedCodeFingerprintRef.current = nextFingerprint;
  }, [entryFile, files, postRunHydrationPending, workspaceState.dirty]);

  const {
    phase: sandboxPhase,
    draftDevStatus,
    draftDevError,
    previewAssetUrl,
    previewTransportGeneration,
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
  const currentLastSuccessfulBuildId = draftDevSession?.live_preview?.last_successful_build_id || null;
  const postRunPreviewPollingActive = Boolean(
    postRunPreviewPollState && postRunPreviewPollState.until > Date.now(),
  );
  const livePreviewState = useBuilderLivePreviewStatus({
    previewBaseUrl: previewAssetUrl,
    previewAuthToken,
    sessionLivePreview: draftDevSession?.live_preview,
    enabled: hasActiveCodingRunLock || postRunPreviewPollingActive || (
      activeTab === "preview"
      && draftDevSession?.live_preview?.status !== "ready"
      && draftDevSession?.live_preview?.status !== "failed_keep_last_good"
    ),
  });

  useEffect(() => {
    if (!postRunPreviewPollState) {
      return;
    }
    const timeoutMs = Math.max(0, postRunPreviewPollState.until - Date.now());
    const timer = window.setTimeout(() => {
      setPostRunPreviewPollState((current) => {
        if (!current) {
          return current;
        }
        return current.until <= Date.now() ? null : current;
      });
    }, timeoutMs + 50);
    return () => {
      window.clearTimeout(timer);
    };
  }, [postRunPreviewPollState]);

  useEffect(() => {
    if (!postRunPreviewPollState) {
      return;
    }
    if (!currentLastSuccessfulBuildId) {
      return;
    }
    if (currentLastSuccessfulBuildId === postRunPreviewPollState.baselineBuildId) {
      return;
    }
    logBuilderWorkspaceDebug("post_run_preview_poll.completed", {
      baselineBuildId: postRunPreviewPollState.baselineBuildId,
      nextBuildId: currentLastSuccessfulBuildId,
    });
    setPostRunPreviewPollState(null);
  }, [currentLastSuccessfulBuildId, postRunPreviewPollState]);

  const appRoutes = useMemo(() => extractRoutesFromFiles(files), [files]);
  const filteredAppRoutes = useMemo(() => {
    const query = previewRouteInput.trim().toLowerCase();
    if (!query) {
      return appRoutes;
    }
    return appRoutes.filter((route) => route.toLowerCase().includes(query));
  }, [appRoutes, previewRouteInput]);
  const orderedTemplates = useMemo(() => sortTemplates(state?.templates || []), [state?.templates]);
  const platformDomain = useMemo(
    () => `${state?.app.slug || "app"}.${process.env.NEXT_PUBLIC_APPS_BASE_DOMAIN || "apps.localhost"}`,
    [state?.app.slug],
  );
  const livePreviewTransport = useBuilderPreviewTransport({
    sessionId: draftDevSession?.session_id || null,
    previewBaseUrl: previewAssetUrl,
    previewAuthToken,
    previewRoute,
    previewTransportGeneration,
    livePreviewStatus: livePreviewState?.status || null,
    livePreviewLastSuccessfulBuildId: livePreviewState?.last_successful_build_id || null,
    livePreviewError: livePreviewState?.error || null,
    hardReloadToken: previewReloadToken,
    draftDevStatus,
    lifecyclePhase: sandboxPhase,
    lastError: draftDevError,
  });
  const navigatePreview = useCallback((route: string) => {
    const normalizedRoute = normalizeRoutePath(route) || "/";
    setPreviewRoute(normalizedRoute);
    setPreviewRouteInput(normalizedRoute);
    setIsPreviewRoutePickerOpen(false);
  }, []);

  const reloadPreview = useCallback(() => {
    setPreviewReloadToken((current) => current + 1);
  }, []);

  useEffect(() => {
    setPreviewRouteInput(previewRoute);
  }, [previewRoute]);

  const loadState = useCallback(async ({ showInitialSkeleton = false }: { showInitialSkeleton?: boolean } = {}) => {
    if (showInitialSkeleton) {
      setIsInitialLoading(true);
    }
    setError(null);
    try {
      const [response, exportState] = await Promise.all([
        publishedAppsService.getBuilderState(appId),
        publishedAppsService.getExportOptions(appId),
      ]);
      logBuilderWorkspaceDebug("load_state.received", {
        appId,
        currentRevisionId: response.current_draft_revision?.id || null,
        draftDevSessionId: response.draft_dev?.session_id || null,
        draftDevStatus: response.draft_dev?.status || null,
        livePreviewStatus: response.draft_dev?.live_preview?.status || null,
        livePreviewCurrentBuildId: response.draft_dev?.live_preview?.current_build_id || null,
        livePreviewLastSuccessfulBuildId: response.draft_dev?.live_preview?.last_successful_build_id || null,
        livePreviewUpdatedAt: response.draft_dev?.live_preview?.updated_at || null,
        liveSnapshotRevisionToken: response.draft_dev?.live_workspace_snapshot?.revision_token || null,
        liveSnapshotUpdatedAt: response.draft_dev?.live_workspace_snapshot?.updated_at || null,
        liveSnapshotFileCount: response.draft_dev?.live_workspace_snapshot?.files
          ? Object.keys(response.draft_dev.live_workspace_snapshot.files).length
          : 0,
      });
      setState(response);
      setExportOptions(exportState);
      if (response.draft_dev?.live_workspace_snapshot?.files) {
        hydrateFromBuilderSession(response.draft_dev);
      } else {
        hydrateWorkspaceFromRevision(response.current_draft_revision);
        hydrateFromBuilderSession(response.draft_dev);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load builder state");
    } finally {
      if (showInitialSkeleton) {
        setIsInitialLoading(false);
      }
    }
  }, [appId, hydrateFromBuilderSession, hydrateWorkspaceFromRevision]);

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

  const loadAgents = useCallback(async () => {
    setIsAgentsLoading(true);
    try {
      const response = await agentService.listAgents({ limit: 100, view: "summary", status: "published" });
      setAvailableAgents(response.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setIsAgentsLoading(false);
    }
  }, []);

  const refreshStateSilently = useCallback(async () => {
    try {
      const [response, exportState] = await Promise.all([
        publishedAppsService.getBuilderState(appId),
        publishedAppsService.getExportOptions(appId),
      ]);
      logBuilderWorkspaceDebug("refresh_state_silently.received", {
        appId,
        currentRevisionId: response.current_draft_revision?.id || null,
        draftDevSessionId: response.draft_dev?.session_id || null,
        draftDevStatus: response.draft_dev?.status || null,
        livePreviewStatus: response.draft_dev?.live_preview?.status || null,
        livePreviewCurrentBuildId: response.draft_dev?.live_preview?.current_build_id || null,
        livePreviewLastSuccessfulBuildId: response.draft_dev?.live_preview?.last_successful_build_id || null,
        livePreviewUpdatedAt: response.draft_dev?.live_preview?.updated_at || null,
        liveSnapshotRevisionToken: response.draft_dev?.live_workspace_snapshot?.revision_token || null,
        liveSnapshotUpdatedAt: response.draft_dev?.live_workspace_snapshot?.updated_at || null,
        liveSnapshotFileCount: response.draft_dev?.live_workspace_snapshot?.files
          ? Object.keys(response.draft_dev.live_workspace_snapshot.files).length
          : 0,
      });
      setState(response);
      setExportOptions(exportState);
      if (response.draft_dev?.live_workspace_snapshot?.files) {
        hydrateFromBuilderSession(response.draft_dev);
      } else {
        hydrateWorkspaceFromRevision(response.current_draft_revision);
        hydrateFromBuilderSession(response.draft_dev);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh builder state");
    }
  }, [appId, hydrateFromBuilderSession, hydrateWorkspaceFromRevision]);

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
      if (!draftDevSession?.live_workspace_snapshot?.files) {
        hydrateWorkspaceFromRevision(revision);
      }
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
  const exportDisabledReason = isExportingArchive
    ? "Export in progress..."
    : exportOptions && !exportOptions.supported
      ? exportOptions.reason || "Export is not supported for this app."
      : exportOptions && !exportOptions.ready
        ? exportOptions.reason || "Export is not ready yet."
        : null;
  const isExportDisabled = Boolean(exportDisabledReason);
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
  const inspectedPreviewTransportStatus = useMemo(() => {
    if (inspectedPreviewNotice) {
      return "failed" as const;
    }
    if (isLoadingVersionPreview) {
      return "booting" as const;
    }
    if (inspectedPreviewFrameUrl) {
      return "ready" as const;
    }
    return "idle" as const;
  }, [inspectedPreviewFrameUrl, inspectedPreviewNotice, isLoadingVersionPreview]);
  const effectivePreviewUrl = isInspectingVersion ? inspectedPreviewFrameUrl : livePreviewTransport.documentUrl;
  const effectivePreviewToken = isInspectingVersion ? inspectedRuntimeToken : previewAuthToken;
  const livePreviewError = (
    livePreviewState?.status === "failed_keep_last_good"
    || livePreviewState?.status === "failed_no_build"
  ) ? (livePreviewState.error || null) : null;
  const effectivePreviewError = isInspectingVersion
    ? inspectedPreviewNotice
    : (draftDevError || livePreviewError || null);
  const effectivePreviewTransportKey = isInspectingVersion
    ? (inspectedPreviewFrameUrl ? `version:${inspectedVersionId || "preview"}:${previewReloadToken}` : null)
    : livePreviewTransport.transportKey;
  const effectivePreviewTransportStatus = isInspectingVersion ? inspectedPreviewTransportStatus : livePreviewTransport.status;
  const effectivePreviewHasUsableFrame = isInspectingVersion
    ? Boolean(inspectedPreviewFrameUrl) && inspectedPreviewTransportStatus === "ready"
    : livePreviewTransport.hasUsableFrame;
  const effectivePreviewLoadingMessage = isInspectingVersion
    ? (isLoadingVersionPreview ? "Loading selected version preview..." : null)
    : previewLoadingMessage;
  const effectivePreviewLoadingState = useMemo(() => {
    if (isInspectingVersion) {
      if (!isLoadingVersionPreview) {
        return null;
      }
      return {
        title: "Loading selected version",
        detail: "Preparing the published snapshot preview...",
        steps: [
          { label: "Load version snapshot", status: "complete" as const },
          { label: "Start preview frame", status: "current" as const },
        ],
      };
    }
      return buildBuilderPreviewLoadingState({
        lifecyclePhase: sandboxPhase,
        draftDevStatus,
        transportStatus: effectivePreviewTransportStatus,
        loadingMessage: effectivePreviewLoadingMessage,
        errorMessage: effectivePreviewError,
        livePreviewStatus: livePreviewState?.status || null,
      });
  }, [
    draftDevStatus,
    effectivePreviewError,
    effectivePreviewLoadingMessage,
    effectivePreviewTransportStatus,
    isInspectingVersion,
    isLoadingVersionPreview,
    livePreviewState?.status,
    sandboxPhase,
  ]);

  useEffect(() => {
    logBuilderPreviewDebug("workspace-preview", "effective_state", {
      activeTab,
      previewMode,
      previewRoute,
      previewRouteInput,
      isInspectingVersion,
      sandboxPhase,
      draftDevStatus,
      draftDevSessionId: draftDevSession?.session_id || null,
      previewTransportGeneration,
      effectivePreviewTransportKey,
      effectivePreviewTransportStatus,
      effectivePreviewHasUsableFrame,
      effectivePreviewUrl,
      effectivePreviewError: effectivePreviewError || null,
      effectivePreviewLoadingMessage: effectivePreviewLoadingMessage || null,
      effectivePreviewLoadingTitle: effectivePreviewLoadingState?.title || null,
    });
  }, [
    activeTab,
    draftDevSession,
    draftDevStatus,
    effectivePreviewError,
    effectivePreviewHasUsableFrame,
    effectivePreviewLoadingMessage,
    effectivePreviewLoadingState,
    effectivePreviewTransportKey,
    effectivePreviewTransportStatus,
    effectivePreviewUrl,
    isInspectingVersion,
    previewMode,
    previewRoute,
    previewRouteInput,
    previewTransportGeneration,
    sandboxPhase,
  ]);

  useEffect(() => {
    if (initializedAppIdRef.current === appId) {
      return;
    }
    initializedAppIdRef.current = appId;
    void loadState({ showInitialSkeleton: true });
    void loadAuthTemplates();
    void loadAgents();
  }, [appId, loadAgents, loadAuthTemplates, loadState]);

  useEffect(() => {
    if (!workspaceNotice) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      dispatchWorkspace({ type: "clear_notice" });
    }, 3200);
    return () => window.clearTimeout(timeoutId);
  }, [workspaceNotice]);

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

  const downloadExportArchive = useCallback(async () => {
    setIsExportingArchive(true);
    setError(null);
    try {
      const { blob, filename } = await publishedAppsService.downloadExportArchive(appId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename || `${state?.app.slug || "app"}-standalone-export.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      const nextOptions = await publishedAppsService.getExportOptions(appId);
      setExportOptions(nextOptions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to export app archive");
    } finally {
      setIsExportingArchive(false);
    }
  }, [appId, state?.app.slug]);

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
        agent_id: app.agent_id,
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
      dispatchWorkspace({
        type: "hydrate",
        payload: {
          files,
          entryFile,
          revisionId: revision.id,
          workspaceRevisionToken,
          workspaceSource: "durable_revision",
          preserveSelection: true,
        },
      });
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
  }, [appId, currentRevisionId, ensureDraftDevSession, entryFile, files, loadState, saveBlockedByBackendLock, workspaceRevisionToken]);

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
        hydrateWorkspaceFromRevision(revision);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to switch template");
      }
    },
    [appId, hydrateWorkspaceFromRevision],
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
    activeContextStatus,
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
    onPostRunHydrationStateChange: (inProgress) => {
      setPostRunHydrationPending(inProgress);
      if (inProgress) {
        const baselineBuildId =
          livePreviewState?.last_successful_build_id
          || draftDevSession?.live_preview?.last_successful_build_id
          || null;
        logBuilderWorkspaceDebug("post_run_preview_poll.begin", {
          baselineBuildId,
          livePreviewStatus: livePreviewState?.status || draftDevSession?.live_preview?.status || null,
        });
        setPostRunPreviewPollState({
          until: Date.now() + POST_RUN_PREVIEW_POLL_WINDOW_MS,
          baselineBuildId,
        });
      }
    },
    onSetCurrentRevisionId: (revisionId) => {
      dispatchWorkspace({
        type: "hydrate",
        payload: {
          files,
          entryFile,
          revisionId,
          workspaceRevisionToken,
          workspaceSource,
          preserveSelection: true,
        },
      });
    },
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
      isDraftDevServingStatus(draftDevStatus)
        ? (
            livePreviewTransport.documentUrl
            || (
              draftDevSession?.preview_url
                ? buildBuilderPreviewDocumentUrl({
                    baseUrl: draftDevSession.preview_url,
                    route: previewRoute,
                    runtimeToken: previewAuthToken || draftDevSession?.preview_auth_token || null,
                    buildId: livePreviewState?.last_successful_build_id || null,
                  })
                : null
            )
          )
        : null;
    if (inMemoryPreviewUrl) {
      window.open(
        inMemoryPreviewUrl,
        "_blank",
        "noopener,noreferrer",
      );
      return;
    }

    setIsOpeningApp(true);
    try {
      const ensuredSession = await ensureDraftDevSession({ force: true });
      const session = ensuredSession || draftDevSession;
      if (!session?.preview_url) {
        throw new Error("Draft preview URL is unavailable");
      }
      window.open(
        buildBuilderPreviewDocumentUrl({
          baseUrl: session.preview_url,
          route: previewRoute,
          runtimeToken: session.preview_auth_token || previewAuthToken,
          buildId: livePreviewState?.last_successful_build_id || null,
        }),
        "_blank",
        "noopener,noreferrer",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open app");
    } finally {
      setIsOpeningApp(false);
    }
  }, [
    draftDevSession,
    ensureDraftDevSession,
    state?.app.published_url,
    state?.app.status,
    previewAuthToken,
    draftDevStatus,
    livePreviewTransport.documentUrl,
    livePreviewState?.last_successful_build_id,
    previewRoute,
  ]);

  const deleteFile = (path: string) => {
    dispatchWorkspace({ type: "delete_file", path });
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
      className="flex h-dvh min-h-0 w-full gap-0 overflow-visible bg-background"
    >
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="relative z-10 flex h-11 shrink-0 items-center gap-3 overflow-visible border-b px-3">
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
          <div className="relative flex min-w-0 flex-1 items-center justify-center overflow-visible">
            <div className="relative flex items-center overflow-visible">
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
                    <div className="relative w-56">
                      <Input
                        value={previewRouteInput}
                        onChange={(event) => {
                          setPreviewRouteInput(event.target.value);
                          setIsPreviewRoutePickerOpen(true);
                        }}
                        onFocus={() => setIsPreviewRoutePickerOpen(true)}
                        onBlur={() => {
                          window.setTimeout(() => {
                            setIsPreviewRoutePickerOpen(false);
                          }, 120);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            navigatePreview(previewRouteInput);
                          }
                          if (event.key === "Escape") {
                            setPreviewRouteInput(previewRoute);
                            setIsPreviewRoutePickerOpen(false);
                          }
                        }}
                        placeholder="/"
                        className="h-7 border-border/50 bg-transparent px-2 py-0 text-xs font-medium shadow-none"
                      />
                      {isPreviewRoutePickerOpen ? (
                        <div className="absolute top-full left-0 z-20 mt-1 w-full overflow-hidden rounded-md border border-border/60 bg-popover shadow-md">
                          <Command shouldFilter={false}>
                            <CommandList className="max-h-56">
                              <CommandEmpty className="py-3 text-center text-xs text-muted-foreground">
                                No routes found
                              </CommandEmpty>
                              <CommandGroup>
                                {filteredAppRoutes.map((route) => (
                                  <CommandItem
                                    key={route}
                                    value={route}
                                    onSelect={() => navigatePreview(route)}
                                    className="flex items-center justify-between text-xs"
                                  >
                                    <span>{route}</span>
                                    {route === previewRoute ? <Check className="h-3.5 w-3.5 text-muted-foreground" /> : null}
                                  </CommandItem>
                                ))}
                                {normalizeRoutePath(previewRouteInput)
                                  && !filteredAppRoutes.includes(normalizeRoutePath(previewRouteInput) as string) ? (
                                    <CommandItem
                                      value={previewRouteInput}
                                      onSelect={() => navigatePreview(previewRouteInput)}
                                      className="flex items-center justify-between text-xs"
                                    >
                                      <span>{normalizeRoutePath(previewRouteInput)}</span>
                                      <span className="text-[10px] text-muted-foreground">go</span>
                                    </CommandItem>
                                  ) : null}
                              </CommandGroup>
                            </CommandList>
                          </Command>
                        </div>
                      ) : null}
                    </div>
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
                    variant="outline"
                    className="h-7 gap-1.5 px-2.5 text-xs"
                    onClick={() => void downloadExportArchive()}
                    disabled={isExportDisabled}
                  >
                    {isExportingArchive ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                    Export
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                {exportDisabledReason || "Download standalone export archive"}
              </TooltipContent>
            </Tooltip>

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
              <div
                className={cn(
                  "h-full",
                  activeTab === "preview" ? "block" : "hidden",
                )}
              >
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
                        transportKey={effectivePreviewTransportKey}
                        transportStatus={effectivePreviewTransportStatus}
                        hasUsableFrame={effectivePreviewHasUsableFrame}
                        errorMessage={effectivePreviewError}
                        loadingMessage={effectivePreviewLoadingMessage}
                        loadingState={effectivePreviewLoadingState}
                        canRetry={!isInspectingVersion && canRetrySandboxLifecycle}
                        onFrameReady={isInspectingVersion ? null : livePreviewTransport.markFrameUsable}
                        onFrameCleared={isInspectingVersion ? null : livePreviewTransport.clearUsableFrame}
                        onRetry={isInspectingVersion ? null : () => {
                          void retryEnsureDraftDevSession();
                        }}
                      />
                    )}
                  </div>
                </div>
              </div>

              <div
                className={cn(
                  "h-full min-h-0",
                  activeTab === "config" ? "block" : "hidden",
                )}
              >
                <div className="flex h-full min-h-0">
                  <ConfigSidebar
                    configSection={configSection}
                    onChangeSection={handleConfigSectionChange}
                    onBackFromCode={handleBackFromCode}
                    files={files}
                    selectedFile={selectedFile}
                    onSelectFile={(path) => dispatchWorkspace({ type: "select_file", path })}
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
                          <Label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Agent</Label>
                          {isAgentsLoading ? (
                            <Skeleton className="h-10 w-full rounded-lg" />
                          ) : (
                            <Select
                              value={state.app.agent_id}
                              onValueChange={(value) => updateLocalApp({ agent_id: value })}
                            >
                              <SelectTrigger className="rounded-md">
                                <SelectValue placeholder="Select agent..." />
                              </SelectTrigger>
                              <SelectContent>
                                {availableAgents.map((agent) => (
                                  <SelectItem key={agent.id} value={agent.id}>
                                    {agent.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          )}
                        </div>

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
                          dispatchWorkspace({ type: "update_file", path, content });
                        }}
                        readOnly={codeEditingLocked}
                      />
                    )}
                  </section>
                </div>
              </div>
            </div>
          </main>

          <AppsBuilderChatPanel
            isOpen={isAgentPanelOpen}
            isSending={isSending}
            isStopping={isStopping}
            timeline={timeline}
            activeThinkingSummary={activeThinkingSummary}
            activeContextStatus={activeContextStatus}
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
      {workspaceNotice ? (
        <div className="pointer-events-none fixed bottom-4 left-4 z-50 w-full max-w-sm px-4 sm:px-0">
          <Alert className="pointer-events-auto border-border/70 bg-background shadow-lg">
            <AlertDescription>
              {workspaceNotice}
              {workspaceConflict ? ` Source: ${workspaceSource === "materialized_run" ? "materialized run" : "live workspace"}.` : ""}
            </AlertDescription>
          </Alert>
        </div>
      ) : null}
    </Tabs>
  );
}
