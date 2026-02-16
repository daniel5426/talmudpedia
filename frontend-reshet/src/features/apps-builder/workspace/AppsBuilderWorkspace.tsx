"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ExternalLink,
  Loader2,
  PanelRightClose,
  Rocket,
  RotateCcw,
  Save,
  Sparkles,
  X,
} from "lucide-react";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { Loader } from "@/components/ai-elements/loader";
import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input";
import { Tool, ToolContent, ToolHeader, ToolOutput } from "@/components/ai-elements/tool";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { publishedAppsService, publishedRuntimeService } from "@/services";
import type {
  BuilderStateResponse,
  CodingAgentStreamEvent,
  DraftDevSessionResponse,
  DraftDevSessionStatus,
  PublishedAppAuthTemplate,
  PublishedAppDomain,
  PublishedAppRevision,
  PublishedAppUser,
  RevisionConflictResponse,
} from "@/services";
import { cn } from "@/lib/utils";
import { sortTemplates } from "@/features/apps-builder/templates";
import { PreviewCanvas } from "@/features/apps-builder/preview/PreviewCanvas";
import { CodeEditorPanel } from "@/features/apps-builder/editor/CodeEditorPanel";
import { ConfigSidebar } from "@/features/apps-builder/workspace/ConfigSidebar";

const parseSse = (raw: string): CodingAgentStreamEvent | null => {
  const dataLine = raw.split("\n").find((line) => line.startsWith("data: "));
  if (!dataLine) return null;
  try {
    return JSON.parse(dataLine.slice(6)) as CodingAgentStreamEvent;
  } catch {
    return null;
  }
};

const DRAFT_DEV_SYNC_DEBOUNCE_MS = 800;
const DRAFT_DEV_HEARTBEAT_MS = 45_000;
const PUBLISH_POLL_INTERVAL_MS = 2_000;
const PUBLISH_POLL_TIMEOUT_MS = 15 * 60_000;

type WorkspaceProps = {
  appId: string;
};

type ConfigSection = "overview" | "users" | "domains" | "code";

type TimelineTone = "default" | "success" | "error";

type TimelineItem = {
  id: string;
  title: string;
  description?: string;
  tone?: TimelineTone;
  raw?: Record<string, unknown> | string;
};

type TimelineToolState =
  | "input-streaming"
  | "input-available"
  | "approval-requested"
  | "approval-responded"
  | "output-available"
  | "output-error"
  | "output-denied";

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function timelineId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function buildDraftDevSyncFingerprint(entry: string, nextFiles: Record<string, string>): string {
  return JSON.stringify({
    entry,
    files: nextFiles,
  });
}

function isUserTimelineItem(item: TimelineItem): boolean {
  return item.title === "User request";
}

function toTimelineToolType(title: string): `tool-${string}` {
  const normalized = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  return `tool-${normalized || "builder-event"}`;
}

function toTimelineToolState(item: TimelineItem): TimelineToolState {
  if (item.tone === "error") return "output-error";
  if (item.title.toLowerCase().includes("started")) return "input-available";
  if (item.title.toLowerCase().includes("status")) return "input-available";
  return "output-available";
}

function toTimelineToolOutput(item: TimelineItem): Record<string, unknown> | string | undefined {
  if (item.raw !== undefined) return item.raw;
  if (item.tone === "error") return undefined;
  return item.description || item.title;
}

export function AppsBuilderWorkspace({ appId }: WorkspaceProps) {
  const { setOpen } = useSidebar();
  const [state, setState] = useState<BuilderStateResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"preview" | "config">("preview");
  const [configSection, setConfigSection] = useState<ConfigSection>("overview");
  const [lastNonCodeConfigSection, setLastNonCodeConfigSection] = useState<Exclude<ConfigSection, "code">>("overview");
  const [isAgentPanelOpen, setIsAgentPanelOpen] = useState(true);
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
  const [isSending, setIsSending] = useState(false);
  const [isUndoing, setIsUndoing] = useState(false);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [error, setError] = useState<string | null>(null);
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

  const orderedTemplates = useMemo(() => sortTemplates(state?.templates || []), [state?.templates]);
  const platformDomain = useMemo(
    () => `${state?.app.slug || "app"}.${process.env.NEXT_PUBLIC_APPS_BASE_DOMAIN || "apps.localhost"}`,
    [state?.app.slug],
  );

  const pushTimeline = useCallback((item: Omit<TimelineItem, "id">) => {
    setTimeline((prev) => [...prev, { ...item, id: timelineId("timeline") }]);
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
      pushTimeline({
        title: "Overview saved",
        description: "App settings updated.",
        tone: "success",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save app settings");
    } finally {
      setIsSavingOverview(false);
    }
  }, [appId, pushTimeline, state]);

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
      pushTimeline({
        title: "Manual draft saved",
        description: `Revision ${revision.id.slice(0, 8)} created.`,
        tone: "success",
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
  }, [activeTab, appId, currentRevisionId, ensureDraftDevSession, entryFile, files, loadState, pushTimeline]);

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
      pushTimeline({
        title: "Publish succeeded",
        description: "Static app revision is now live.",
        tone: "success",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to publish app");
      setPublishStatus("failed");
    } finally {
      setIsPublishing(false);
    }
  }, [appId, currentRevisionId, entryFile, files, loadState, pushTimeline]);

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
        pushTimeline({
          title: "Template reset",
          description: `Draft replaced with ${templateKey}.`,
          tone: "default",
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to switch template");
      }
    },
    [appId, hydrateFromRevision, pushTimeline],
  );

  const sendBuilderChat = useCallback(async (rawInput: string) => {
    const input = rawInput.trim();
    if (!input) return;

    setIsSending(true);
    setError(null);
    pushTimeline({ title: "User request", description: input });

    try {
      const run = await publishedAppsService.createCodingAgentRun(appId, {
        input,
        base_revision_id: currentRevisionId || undefined,
      });

      pushTimeline({
        title: "Run accepted",
        description: `Run ${run.run_id.slice(0, 8)} queued`,
      });

      const response = await publishedAppsService.streamCodingAgentRun(appId, run.run_id);
      if (!response.ok) {
        let message = `Failed to stream coding-agent run (${response.status})`;
        try {
          const payload = await response.json();
          const detail = payload?.detail;
          if (typeof detail === "string") {
            message = detail;
          } else if (detail && typeof detail === "object") {
            message = JSON.stringify(detail);
          }
        } catch {
          // Keep fallback message.
        }
        throw new Error(message);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Streaming reader unavailable");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let assistantText = "";
      let latestSummary = "";
      let latestResultRevisionId = "";
      let streamRunId = run.run_id;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let splitIndex = buffer.indexOf("\n\n");
        while (splitIndex >= 0) {
          const raw = buffer.slice(0, splitIndex).trim();
          buffer = buffer.slice(splitIndex + 2);
          const parsed = parseSse(raw);
          if (!parsed) {
            splitIndex = buffer.indexOf("\n\n");
            continue;
          }

          const payload = (parsed.payload || {}) as Record<string, unknown>;
          if (parsed.run_id) {
            streamRunId = parsed.run_id;
          }

          if (parsed.event === "assistant.delta" && payload.content) {
            assistantText += String(payload.content);
          }

          if (parsed.event === "run.accepted") {
            pushTimeline({
              title: "Run status",
              description: String(payload.status || "Coding-agent run started"),
            });
          }

          if (parsed.event === "plan.updated") {
            latestSummary = String(payload.summary || latestSummary || "");
            pushTimeline({
              title: "Plan updated",
              description: String(payload.summary || payload.node || "Planning next step"),
            });
          }

          if (parsed.event === "tool.started") {
            pushTimeline({
              title: `Tool started: ${String(payload.tool || "unknown")}`,
              description: String(payload.span_id || ""),
            });
          }

          if (parsed.event === "tool.completed") {
            const result = payload.output;
            pushTimeline({
              title: `Tool completed: ${String(payload.tool || "unknown")}`,
              description:
                typeof result === "object" && result && "message" in result
                  ? String((result as Record<string, unknown>).message || "ok")
                  : "ok",
              tone: "success",
              raw: (result as Record<string, unknown>) || {},
            });
          }

          if (parsed.event === "tool.failed") {
            const result = payload.output;
            pushTimeline({
              title: `Tool failed: ${String(payload.tool || "unknown")}`,
              description:
                typeof result === "object" && result && "message" in result
                  ? String((result as Record<string, unknown>).message || "failed")
                  : "failed",
              tone: "error",
              raw: (result as Record<string, unknown>) || {},
            });
          }

          if (parsed.event === "revision.created") {
            const revisionId = String(payload.revision_id || "");
            latestResultRevisionId = revisionId || latestResultRevisionId;
            if (revisionId) {
              setCurrentRevisionId(revisionId);
            }
            pushTimeline({
              title: "Revision created",
              description: revisionId
                ? `Revision ${revisionId.slice(0, 8)} (${String(payload.file_count || 0)} files)`
                : "Draft revision created",
              tone: "success",
              raw: payload,
            });
          }

          if (parsed.event === "checkpoint.created") {
            const revisionId = String(payload.revision_id || "");
            const checkpointId = String(payload.checkpoint_id || "");
            if (revisionId) {
              setCurrentRevisionId(revisionId);
            }
            pushTimeline({
              title: "Checkpoint created",
              description: checkpointId
                ? `Checkpoint ${checkpointId.slice(0, 8)}${revisionId ? ` (rev ${revisionId.slice(0, 8)})` : ""}`
                : "Checkpoint created",
              tone: "success",
              raw: payload,
            });
          }

          if (parsed.event === "run.failed") {
            const failureMessage = String(
              parsed.diagnostics?.[0]?.message || payload.error || "Coding-agent run failed",
            );
            pushTimeline({
              title: "Run error",
              description: failureMessage,
              tone: "error",
              raw: payload,
            });
          }

          if (Array.isArray(parsed.diagnostics) && parsed.diagnostics.length > 0) {
            pushTimeline({
              title: "Diagnostic",
              description: String(parsed.diagnostics[0]?.message || "diagnostic"),
              tone: "error",
              raw: { diagnostics: parsed.diagnostics },
            });
          }

          splitIndex = buffer.indexOf("\n\n");
        }
      }

      const finalAssistantText = assistantText.trim() || latestSummary;
      if (finalAssistantText) {
        pushTimeline({
          title: "Assistant",
          description: finalAssistantText,
          tone: "default",
        });
      }

      await loadState();
      if (activeTab === "preview") {
        await ensureDraftDevSession();
      }
      if (latestResultRevisionId) {
        setCurrentRevisionId(latestResultRevisionId);
      }
      if (streamRunId) {
        pushTimeline({
          title: "Run complete",
          description: `Run ${streamRunId.slice(0, 8)} finished`,
          tone: "success",
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run coding agent");
    } finally {
      setIsSending(false);
    }
  }, [
    activeTab,
    appId,
    currentRevisionId,
    ensureDraftDevSession,
    loadState,
    pushTimeline,
  ]);

  const restoreLatestCheckpoint = useCallback(async () => {
    setIsUndoing(true);
    setError(null);
    try {
      const checkpoints = await publishedAppsService.listCodingAgentCheckpoints(appId, 1);
      const latest = checkpoints[0];
      if (!latest) {
        throw new Error("No coding-agent checkpoints found");
      }
      const response = await publishedAppsService.restoreCodingAgentCheckpoint(appId, latest.checkpoint_id, {
        run_id: latest.run_id || undefined,
      });
      const revision = response.revision;
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
      pushTimeline({
        title: "Checkpoint restored",
        description: `Restored checkpoint ${response.checkpoint_id.slice(0, 8)} to revision ${revision.id.slice(0, 8)}.`,
        tone: "success",
      });
      if (activeTab === "preview") {
        await ensureDraftDevSession();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to restore latest checkpoint");
    } finally {
      setIsUndoing(false);
    }
  }, [activeTab, appId, ensureDraftDevSession, hydrateFromRevision, pushTimeline]);

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
      <div className="flex h-screen items-center justify-center text-muted-foreground">
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
      className="flex h-screen w-full overflow-hidden gap-0 bg-background"
    >
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="grid h-14 shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-border/60 px-4">
          <div className="flex min-w-0 items-center gap-2">
            <Link
              href="/admin/apps"
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Apps
            </Link>
            <div className="text-sm font-semibold">{state.app.name}</div>
            <Badge variant="outline" className="font-mono text-[10px]">
              /{state.app.slug}
            </Badge>
            <Badge variant={state.app.status === "published" ? "default" : "secondary"}>{state.app.status}</Badge>
            <Badge variant="outline">{state.app.visibility}</Badge>
            {draftDevStatus && (
              <Badge
                variant={
                  draftDevStatus === "running"
                    ? "default"
                    : draftDevStatus === "error"
                      ? "destructive"
                      : "secondary"
                }
              >
                draft:{draftDevStatus}
              </Badge>
            )}
            {publishStatus && (
              <Badge
                variant={
                  publishStatus === "succeeded"
                    ? "default"
                    : publishStatus === "failed"
                      ? "destructive"
                      : "secondary"
                }
              >
                publish:{publishStatus}
              </Badge>
            )}
          </div>

          <div className="justify-self-center">
            <TabsList>
              <TabsTrigger value="preview">Preview</TabsTrigger>
              <TabsTrigger value="config">Config</TabsTrigger>
            </TabsList>
          </div>

          <div className="flex items-center justify-self-end gap-2">
            <Button size="sm" variant="outline" onClick={openApp} disabled={isOpeningApp}>
              {isOpeningApp ? (
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
              ) : (
                <ExternalLink className="mr-2 h-3.5 w-3.5" />
              )}
              {state.app.status === "published" ? "Open App" : "Open Preview"}
            </Button>

            <Select value={state.app.template_key} onValueChange={resetTemplate}>
              <SelectTrigger className="h-8 w-52">
                <SelectValue placeholder="Template" />
              </SelectTrigger>
              <SelectContent>
                {orderedTemplates.map((template) => (
                  <SelectItem key={template.key} value={template.key}>
                    {template.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button size="sm" variant="outline" onClick={saveDraft} disabled={isSaving}>
              {isSaving ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-2 h-3.5 w-3.5" />}
              Save Draft
            </Button>
            <Button size="sm" onClick={publish} disabled={isPublishing}>
              {isPublishing ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Rocket className="mr-2 h-3.5 w-3.5" />}
              Publish
            </Button>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <main className="flex min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1">
              {activeTab === "preview" ? (
                <PreviewCanvas
                  previewUrl={previewAssetUrl}
                  devStatus={draftDevStatus}
                  devError={draftDevError}
                />
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

          {isAgentPanelOpen ? (
            <aside className="flex h-full w-[430px] shrink-0 flex-col border-l border-border/60 bg-gradient-to-b from-muted/20 via-background to-background">
              <div className="flex items-center justify-between border-b border-border/60 px-3 py-3">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <Sparkles className="h-4 w-4" />
                  Coding Agent
                </div>
                <div className="flex items-center gap-1">
                  <Button size="sm" variant="outline" onClick={restoreLatestCheckpoint} disabled={isUndoing}>
                    {isUndoing ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="mr-2 h-3.5 w-3.5" />}
                    Restore Last Checkpoint
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setIsAgentPanelOpen(false)}
                    aria-label="Close agent panel"
                  >
                    <PanelRightClose className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-hidden px-3 py-3">
                <Conversation className="h-full rounded-xl border border-border/50 bg-background/80">
                  <ConversationContent className="gap-3 p-3">
                    {timeline.length === 0 ? (
                      <Message from="assistant" className="max-w-full">
                        <MessageContent>
                          <MessageResponse>
                            Ask for a code change to start a live run. You will see tool steps, edits, and checkpoint creation here.
                          </MessageResponse>
                        </MessageContent>
                      </Message>
                    ) : (
                      timeline.map((item) => {
                        if (isUserTimelineItem(item)) {
                          return (
                            <Message key={item.id} from="user" className="max-w-full">
                              <MessageContent>
                                <MessageResponse>{item.description || "Request submitted."}</MessageResponse>
                              </MessageContent>
                            </Message>
                          );
                        }

                        return (
                          <Message key={item.id} from="assistant" className="max-w-full">
                            <MessageContent>
                              <Tool defaultOpen={item.tone === "error"} className="mb-0 w-full">
                                <ToolHeader
                                  title={item.title}
                                  type={toTimelineToolType(item.title)}
                                  state={toTimelineToolState(item)}
                                />
                                {(item.raw !== undefined || item.description) && (
                                  <ToolContent>
                                    <ToolOutput
                                      output={toTimelineToolOutput(item)}
                                      errorText={item.tone === "error" ? item.description : undefined}
                                    />
                                  </ToolContent>
                                )}
                              </Tool>
                            </MessageContent>
                          </Message>
                        );
                      })
                    )}
                    {isSending ? (
                      <Message from="assistant" className="max-w-full">
                        <MessageContent className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Loader size={14} />
                          <span>Running coding agent...</span>
                        </MessageContent>
                      </Message>
                    ) : null}
                  </ConversationContent>
                  <ConversationScrollButton />
                </Conversation>
              </div>

              <div className="border-t border-border/60 p-3">
                <PromptInput
                  onSubmit={async (message) => {
                    await sendBuilderChat(message.text);
                  }}
                  className="rounded-lg border border-border/60 bg-background"
                >
                  <PromptInputBody>
                    <PromptInputTextarea
                      placeholder="Refactor the header and align spacing with the hero..."
                      disabled={isSending}
                      className="min-h-12 max-h-40"
                    />
                  </PromptInputBody>
                  <PromptInputFooter className="pb-2">
                    <PromptInputTools />
                    <PromptInputSubmit size="sm" disabled={isSending} aria-label="Send">
                      {isSending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Send"}
                    </PromptInputSubmit>
                  </PromptInputFooter>
                </PromptInput>
              </div>
            </aside>
          ) : (
            <div className="flex h-full w-10 shrink-0 flex-col items-center border-l border-border/60 bg-muted/20 pt-3">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setIsAgentPanelOpen(true)}
                aria-label="Open agent panel"
              >
                <Sparkles className="h-4 w-4" />
              </Button>
            </div>
          )}
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
