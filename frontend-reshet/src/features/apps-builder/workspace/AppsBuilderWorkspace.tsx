"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  FileCog,
  History,
  Loader2,
  Rocket,
  RotateCcw,
  Save,
  Sparkles,
  Terminal,
  Wrench,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSidebar } from "@/components/ui/sidebar";
import { publishedAppsService } from "@/services";
import type {
  BuilderChatEvent,
  BuilderCheckpoint,
  BuilderPatchOp,
  BuilderStateResponse,
  DraftDevSessionResponse,
  DraftDevSessionStatus,
  PublishedAppRevision,
  RevisionConflictResponse,
} from "@/services";
import { sortTemplates } from "@/features/apps-builder/templates";
import { PreviewCanvas } from "@/features/apps-builder/preview/PreviewCanvas";
import { VirtualFileExplorer } from "@/features/apps-builder/editor/VirtualFileExplorer";

const parseSse = (raw: string): BuilderChatEvent | null => {
  const dataLine = raw.split("\n").find((line) => line.startsWith("data: "));
  if (!dataLine) return null;
  try {
    return JSON.parse(dataLine.slice(6)) as BuilderChatEvent;
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

type TimelineTone = "default" | "success" | "error";

type TimelineItem = {
  id: string;
  title: string;
  description?: string;
  tone?: TimelineTone;
  raw?: Record<string, unknown> | string;
};

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function timelineId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function AppsBuilderWorkspace({ appId }: WorkspaceProps) {
  const { setOpen } = useSidebar();
  const [state, setState] = useState<BuilderStateResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"preview" | "code">("preview");
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
  const [isPublishing, setIsPublishing] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isUndoing, setIsUndoing] = useState(false);
  const [isRevertingFile, setIsRevertingFile] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [checkpoints, setCheckpoints] = useState<BuilderCheckpoint[]>([]);
  const [revertRevisionId, setRevertRevisionId] = useState<string>("latest");
  const [error, setError] = useState<string | null>(null);
  const syncFingerprintRef = useRef<string>("");

  useEffect(() => {
    setOpen(false);
  }, [setOpen]);

  const orderedTemplates = useMemo(() => sortTemplates(state?.templates || []), [state?.templates]);

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
    setFiles(nextFiles);
    setEntryFile(revision?.entry_file || "src/main.tsx");
    setSelectedFile(Object.keys(nextFiles).sort()[0] || null);
    setCurrentRevisionId(revision?.id || null);
  }, []);

  const loadCheckpoints = useCallback(async () => {
    try {
      const rows = await publishedAppsService.getBuilderCheckpoints(appId, 25);
      setCheckpoints(rows);
    } catch {
      // Keep UI responsive if checkpoint list fails.
    }
  }, [appId]);

  const loadState = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await publishedAppsService.getBuilderState(appId);
      setState(response);
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
    loadCheckpoints();
  }, [loadState, loadCheckpoints]);

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
    if (activeTab !== "preview" || !currentRevisionId) {
      return;
    }
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
    const fingerprint = JSON.stringify({
      revision: currentRevisionId,
      entry: entryFile,
      files,
    });
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
  }, [activeTab, currentRevisionId, entryFile, files, syncDraftDevSession]);

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
      await loadCheckpoints();
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
  }, [activeTab, appId, currentRevisionId, ensureDraftDevSession, entryFile, files, loadCheckpoints, loadState, pushTimeline]);

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

      const startedAt = Date.now();
      let status = job.status;
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

  const sendBuilderChat = useCallback(async () => {
    const input = chatInput.trim();
    if (!input) return;

    setIsSending(true);
    setError(null);
    setChatInput("");
    pushTimeline({ title: "User request", description: input });

    try {
      const response = await publishedAppsService.streamBuilderChat(appId, {
        input,
        base_revision_id: currentRevisionId || undefined,
      });
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Streaming reader unavailable");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let assistantText = "";
      let latestSummary = "";
      let streamRequestId = "";
      let latestResultRevisionId = "";

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
          if (parsed.request_id && !streamRequestId) {
            streamRequestId = parsed.request_id;
          }

          if (parsed.event === "token" && parsed.data?.content) {
            assistantText += String(parsed.data.content);
          }

          if (parsed.event === "status") {
            pushTimeline({
              title: "Run status",
              description: String(parsed.data?.content || "Builder run started"),
            });
          }

          if (parsed.event === "tool_started") {
            pushTimeline({
              title: `Tool started: ${parsed.data?.tool || "unknown"}`,
              description: parsed.data?.iteration ? `Iteration ${parsed.data.iteration}` : undefined,
            });
          }

          if (parsed.event === "tool_completed") {
            const result = parsed.data?.result || {};
            pushTimeline({
              title: `Tool completed: ${parsed.data?.tool || "unknown"}`,
              description: String((result as Record<string, unknown>).message || "ok"),
              tone: "success",
              raw: result,
            });
          }

          if (parsed.event === "tool_failed") {
            const result = parsed.data?.result || {};
            pushTimeline({
              title: `Tool failed: ${parsed.data?.tool || "unknown"}`,
              description: String((result as Record<string, unknown>).message || "failed"),
              tone: "error",
              raw: result,
            });
          }

          if (parsed.event === "file_changes") {
            latestSummary = String(parsed.data?.summary || latestSummary || "Applied code changes");
            latestResultRevisionId = String(parsed.data?.result_revision_id || latestResultRevisionId || "");
            const changedPaths = Array.isArray(parsed.data?.changed_paths)
              ? parsed.data?.changed_paths?.join(", ")
              : "";
            pushTimeline({
              title: "Files changed",
              description: changedPaths || "Code updated",
              raw: {
                operations: parsed.data?.operations as BuilderPatchOp[] | undefined,
                summary: parsed.data?.summary,
                rationale: parsed.data?.rationale,
              },
            });
          }

          if (parsed.event === "checkpoint_created") {
            const revisionId = String(parsed.data?.revision_id || "");
            if (revisionId) {
              setCurrentRevisionId(revisionId);
            }
            pushTimeline({
              title: "Checkpoint created",
              description: `${parsed.data?.checkpoint_label || "Automatic checkpoint"}${revisionId ? ` (${revisionId.slice(0, 8)})` : ""}`,
              tone: "success",
              raw: parsed.data,
            });
          }

          if (parsed.event === "error") {
            pushTimeline({
              title: "Run error",
              description: String(parsed.data?.message || "Builder run failed"),
              tone: "error",
              raw: parsed.data,
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
      await loadCheckpoints();
      if (activeTab === "preview") {
        await ensureDraftDevSession();
      }
      if (latestResultRevisionId) {
        setCurrentRevisionId(latestResultRevisionId);
      }
      if (streamRequestId) {
        pushTimeline({
          title: "Run complete",
          description: `Request ${streamRequestId.slice(0, 8)} finished`,
          tone: "success",
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run builder agent");
    } finally {
      setIsSending(false);
    }
  }, [
    activeTab,
    appId,
    chatInput,
    currentRevisionId,
    ensureDraftDevSession,
    loadCheckpoints,
    loadState,
    pushTimeline,
  ]);

  const undoLastRun = useCallback(async () => {
    if (!currentRevisionId) {
      setError("No draft revision to undo");
      return;
    }
    setIsUndoing(true);
    setError(null);
    try {
      const response = await publishedAppsService.undoLastBuilderRun(appId, {
        base_revision_id: currentRevisionId,
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
        title: "Undo completed",
        description: `Restored from revision ${response.restored_from_revision_id.slice(0, 8)}.`,
        tone: "success",
      });
      await loadCheckpoints();
      if (activeTab === "preview") {
        await ensureDraftDevSession();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to undo last run");
    } finally {
      setIsUndoing(false);
    }
  }, [activeTab, appId, currentRevisionId, ensureDraftDevSession, hydrateFromRevision, loadCheckpoints, pushTimeline]);

  const revertSelectedFile = useCallback(async () => {
    const targetPath = selectedFile;
    if (!targetPath) {
      setError("Select a file first");
      return;
    }
    const fromRevisionId =
      revertRevisionId === "latest"
        ? checkpoints[0]?.revision_id
        : revertRevisionId;
    if (!fromRevisionId) {
      setError("No checkpoint revision available for file revert");
      return;
    }
    setIsRevertingFile(true);
    setError(null);
    try {
      const response = await publishedAppsService.revertBuilderFile(appId, {
        path: targetPath,
        from_revision_id: fromRevisionId,
        base_revision_id: currentRevisionId || undefined,
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
        title: "File reverted",
        description: `${response.reverted_path} restored from ${response.from_revision_id.slice(0, 8)}.`,
        tone: "success",
      });
      await loadCheckpoints();
      if (activeTab === "preview") {
        await ensureDraftDevSession();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revert selected file");
    } finally {
      setIsRevertingFile(false);
    }
  }, [
    activeTab,
    appId,
    checkpoints,
    currentRevisionId,
    ensureDraftDevSession,
    hydrateFromRevision,
    loadCheckpoints,
    pushTimeline,
    revertRevisionId,
    selectedFile,
  ]);

  const createFile = (path: string) => {
    const normalized = path.replace(/\\/g, "/").replace(/^\/+/, "");
    if (!normalized) return;
    if (files[normalized] !== undefined) return;
    setFiles((prev) => ({ ...prev, [normalized]: "" }));
    setSelectedFile(normalized);
  };

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

  const runtimeHref = state.app.published_url || `/published/${state.app.slug}`;

  return (
    <Tabs
      value={activeTab}
      onValueChange={(value) => setActiveTab(value as "preview" | "code")}
      className="flex h-screen w-full overflow-hidden gap-0 bg-background"
    >
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="grid h-14 shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-border/60 px-4">
          <div className="flex min-w-0 items-center gap-2">
            <Button size="sm" variant="ghost" asChild>
              <Link href="/admin/apps">
                <ArrowLeft className="mr-1 h-3.5 w-3.5" />
                Back
              </Link>
            </Button>
            <div className="text-sm font-semibold">{state.app.name}</div>
            <Badge variant="outline" className="font-mono text-[10px]">
              /{state.app.slug}
            </Badge>
            <Badge variant={state.app.status === "published" ? "default" : "secondary"}>{state.app.status}</Badge>
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
              <TabsTrigger value="code">Code</TabsTrigger>
            </TabsList>
          </div>

          <div className="flex items-center justify-self-end gap-2">
            <Button size="sm" variant="outline" asChild>
              <a href={runtimeHref} target="_blank" rel="noreferrer">
                <ExternalLink className="mr-2 h-3.5 w-3.5" />
                Open App
              </a>
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
                <VirtualFileExplorer
                  files={files}
                  selectedFile={selectedFile}
                  onSelectFile={setSelectedFile}
                  onUpdateFile={(path, content) => setFiles((prev) => ({ ...prev, [path]: content }))}
                  onDeleteFile={deleteFile}
                  onCreateFile={createFile}
                />
              )}
            </div>
            {error && (
              <Alert variant="destructive" className="mt-3">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </main>

          <aside className="flex h-full w-[430px] shrink-0 flex-col border-l border-border/60 bg-gradient-to-b from-muted/20 via-background to-background">
            <div className="border-b border-border/60 px-3 py-3">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Sparkles className="h-4 w-4" />
                ChatBuilder Agent
              </div>
              <div className="mt-2 grid grid-cols-1 gap-2">
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={undoLastRun} disabled={isUndoing || !currentRevisionId} className="flex-1">
                    {isUndoing ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="mr-2 h-3.5 w-3.5" />}
                    Undo Last Run
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={revertSelectedFile}
                    disabled={isRevertingFile || !selectedFile || checkpoints.length === 0}
                    className="flex-1"
                  >
                    {isRevertingFile ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <FileCog className="mr-2 h-3.5 w-3.5" />}
                    Revert File
                  </Button>
                </div>
                <div className="flex items-center gap-2">
                  <History className="h-3.5 w-3.5 text-muted-foreground" />
                  <Select value={revertRevisionId} onValueChange={setRevertRevisionId}>
                    <SelectTrigger className="h-8">
                      <SelectValue placeholder="Choose checkpoint for file revert" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="latest">Latest checkpoint</SelectItem>
                      {checkpoints.map((cp) => (
                        <SelectItem key={cp.turn_id} value={cp.revision_id}>
                          {(cp.checkpoint_label || cp.assistant_summary || cp.revision_id).slice(0, 56)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            <div className="min-h-0 flex-1 space-y-2 overflow-auto px-3 py-3">
              {timeline.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Ask for a code change to start a live run. You will see tool steps, edits, and checkpoint creation here.
                </p>
              ) : (
                timeline.map((item) => (
                  <div
                    key={item.id}
                    className={`rounded-xl border p-2 text-xs ${
                      item.tone === "error"
                        ? "border-destructive/40 bg-destructive/5"
                        : item.tone === "success"
                          ? "border-emerald-500/30 bg-emerald-500/5"
                          : "border-border/50 bg-background"
                    }`}
                  >
                    <div className="mb-1 flex items-center gap-1.5 font-medium">
                      {item.tone === "error" ? (
                        <AlertCircle className="h-3.5 w-3.5" />
                      ) : item.tone === "success" ? (
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      ) : item.title.toLowerCase().includes("tool") ? (
                        <Wrench className="h-3.5 w-3.5" />
                      ) : item.title.toLowerCase().includes("assistant") ? (
                        <Terminal className="h-3.5 w-3.5" />
                      ) : (
                        <Sparkles className="h-3.5 w-3.5" />
                      )}
                      <span>{item.title}</span>
                    </div>
                    {item.description ? <p className="text-[11px] text-muted-foreground">{item.description}</p> : null}
                    {item.raw ? (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-[10px] text-muted-foreground">raw</summary>
                        <pre className="mt-1 max-h-36 overflow-auto rounded-md bg-muted/40 p-2 text-[10px] leading-tight">
                          {typeof item.raw === "string" ? item.raw : JSON.stringify(item.raw, null, 2)}
                        </pre>
                      </details>
                    ) : null}
                  </div>
                ))
              )}
            </div>

            <div className="border-t border-border/60 p-3">
              <div className="mb-1 text-[10px] text-muted-foreground">
                {selectedFile ? `Selected file: ${selectedFile}` : "No file selected"}
              </div>
              <div className="flex gap-2">
                <Input
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  placeholder="Refactor the header and align spacing with the hero..."
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      sendBuilderChat();
                    }
                  }}
                />
                <Button size="sm" onClick={sendBuilderChat} disabled={isSending || !chatInput.trim()}>
                  {isSending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Send"}
                </Button>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </Tabs>
  );
}
