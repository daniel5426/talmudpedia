"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, Loader2, Rocket, Save, Sparkles } from "lucide-react";

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
import { publishedAppsService, publishedRuntimeService } from "@/services";
import type {
  BuilderChatEvent,
  BuilderPatchOp,
  BuilderStateResponse,
  PublishedAppRevision,
  RevisionConflictResponse,
} from "@/services";
import { applyBuilderPatchOperations } from "@/features/apps-builder/state/useBuilderDraft";
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

type WorkspaceProps = {
  appId: string;
};

type RevisionBuildStatus = "queued" | "running" | "succeeded" | "failed";

export function AppsBuilderWorkspace({ appId }: WorkspaceProps) {
  const { setOpen } = useSidebar();
  const [state, setState] = useState<BuilderStateResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"preview" | "code">("preview");
  const [files, setFiles] = useState<Record<string, string>>({});
  const [entryFile, setEntryFile] = useState("src/main.tsx");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [currentRevisionId, setCurrentRevisionId] = useState<string | null>(null);
  const [buildStatus, setBuildStatus] = useState<RevisionBuildStatus | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [previewAssetUrl, setPreviewAssetUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatLog, setChatLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOpen(false);
  }, [setOpen]);

  const orderedTemplates = useMemo(() => sortTemplates(state?.templates || []), [state?.templates]);

  const hydrateFromRevision = useCallback((revision?: PublishedAppRevision | null) => {
    const nextFiles = revision?.files || {};
    setFiles(nextFiles);
    setEntryFile(revision?.entry_file || "src/main.tsx");
    setSelectedFile(Object.keys(nextFiles).sort()[0] || null);
    setCurrentRevisionId(revision?.id || null);
    setBuildStatus((revision?.build_status as RevisionBuildStatus | undefined) || null);
    setBuildError(revision?.build_error || null);
  }, []);

  const loadState = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await publishedAppsService.getBuilderState(appId);
      setState(response);
      hydrateFromRevision(response.current_draft_revision);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load builder state");
    } finally {
      setIsLoading(false);
    }
  }, [appId, hydrateFromRevision]);

  useEffect(() => {
    loadState();
  }, [loadState]);

  const loadPreviewRuntime = useCallback(
    async (revisionId: string, previewToken: string) => {
      try {
        const runtime = await publishedRuntimeService.getPreviewRuntime(revisionId, previewToken);
        const nextUrl = runtime.asset_base_url || runtime.preview_url;
        setPreviewAssetUrl(nextUrl || null);
      } catch {
        setPreviewAssetUrl(null);
      }
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;

    const pollBuildStatus = async () => {
      if (!currentRevisionId) return;
      try {
        const status = await publishedAppsService.getRevisionBuildStatus(appId, currentRevisionId);
        if (cancelled) return;

        const nextStatus = status.build_status as RevisionBuildStatus;
        setBuildStatus(nextStatus);
        setBuildError(status.build_error || null);

        if (nextStatus === "succeeded") {
          const previewToken = state?.preview_token;
          if (previewToken) {
            await loadPreviewRuntime(currentRevisionId, previewToken);
          }
          return;
        }

        setPreviewAssetUrl(null);
        if (nextStatus === "queued" || nextStatus === "running") {
          timer = window.setTimeout(pollBuildStatus, 2000);
        }
      } catch (err) {
        if (cancelled) return;
        setBuildError(err instanceof Error ? err.message : "Failed to load build status");
      }
    };

    if (currentRevisionId) {
      pollBuildStatus();
    } else {
      setBuildStatus(null);
      setBuildError(null);
      setPreviewAssetUrl(null);
    }

    return () => {
      cancelled = true;
      if (timer !== null) {
        window.clearTimeout(timer);
      }
    };
  }, [appId, currentRevisionId, loadPreviewRuntime, state?.preview_token]);

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
      setBuildStatus((revision.build_status as RevisionBuildStatus | undefined) || "queued");
      setBuildError(revision.build_error || null);
      setPreviewAssetUrl(null);
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
  }, [appId, currentRevisionId, entryFile, files, loadState]);

  const publish = useCallback(async () => {
    setIsPublishing(true);
    setError(null);
    try {
      await saveDraft();
      const updated = await publishedAppsService.publish(appId);
      setState((prev) => (prev ? { ...prev, app: updated } : prev));
      await loadState();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to publish app");
    } finally {
      setIsPublishing(false);
    }
  }, [appId, loadState, saveDraft]);

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

  const sendBuilderChat = useCallback(async () => {
    const input = chatInput.trim();
    if (!input) return;

    setChatInput("");
    setChatLog((prev) => [...prev, `You: ${input}`]);
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
      let pendingOps: BuilderPatchOp[] = [];
      let opsBaseRevision = currentRevisionId;
      let patchSummary = "";
      let patchRationale = "";
      let streamRequestId = "";
      const traceLines: string[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let splitIndex = buffer.indexOf("\n\n");
        while (splitIndex >= 0) {
          const raw = buffer.slice(0, splitIndex).trim();
          buffer = buffer.slice(splitIndex + 2);
          const parsed = parseSse(raw);
          if (parsed?.request_id && !streamRequestId) {
            streamRequestId = parsed.request_id;
          }
          if (parsed?.event === "token" && parsed?.data?.content) {
            assistantText += String(parsed.data.content);
          }
          if (parsed?.event === "status" && parsed?.data?.content) {
            traceLines.push(`Status: ${String(parsed.data.content)}`);
          }
          if (parsed?.event === "tool" && parsed?.data?.tool) {
            const toolName = String(parsed.data.tool);
            const status = String(parsed.data.status || "ok");
            const iteration = parsed.data.iteration ? ` (iter ${parsed.data.iteration})` : "";
            traceLines.push(`Tool${iteration} ${toolName}: ${status}`);
          }
          if (parsed?.event === "patch_ops" && Array.isArray(parsed?.data?.operations)) {
            pendingOps = parsed.data.operations as BuilderPatchOp[];
            opsBaseRevision = parsed?.data?.base_revision_id || opsBaseRevision;
            patchSummary = String(parsed?.data?.summary || "");
            patchRationale = String(parsed?.data?.rationale || "");
          }
          if (Array.isArray(parsed?.diagnostics) && parsed?.diagnostics.length > 0) {
            const firstDiagnostic = parsed.diagnostics[0];
            if (firstDiagnostic?.message) {
              traceLines.push(`Diagnostic: ${firstDiagnostic.message}`);
            }
          }
          splitIndex = buffer.indexOf("\n\n");
        }
      }

      if (traceLines.length > 0) {
        setChatLog((prev) => [...prev, ...traceLines.map((line) => `Builder Trace${streamRequestId ? ` (${streamRequestId.slice(0, 8)})` : ""}: ${line}`)]);
      }
      if (assistantText.trim() || patchSummary) {
        const responseText = assistantText.trim() || patchSummary;
        const rationaleText = patchRationale ? ` (${patchRationale})` : "";
        setChatLog((prev) => [...prev, `Builder: ${responseText}${rationaleText}`]);
      }

      if (pendingOps.length > 0) {
        const nextDraft = applyBuilderPatchOperations(files, entryFile, pendingOps);
        setFiles(nextDraft.files);
        setEntryFile(nextDraft.entryFile);
        if (!nextDraft.files[selectedFile || ""]) {
          setSelectedFile(Object.keys(nextDraft.files).sort()[0] || null);
        }

        const saved = await publishedAppsService.createRevision(appId, {
          base_revision_id: opsBaseRevision || undefined,
          operations: pendingOps,
        });
        setCurrentRevisionId(saved.id);
        setBuildStatus((saved.build_status as RevisionBuildStatus | undefined) || "queued");
        setBuildError(saved.build_error || null);
        setPreviewAssetUrl(null);
        setState((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            current_draft_revision: saved,
            app: {
              ...prev.app,
              current_draft_revision_id: saved.id,
            },
          };
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply builder patch");
    }
  }, [appId, chatInput, currentRevisionId, entryFile, files, selectedFile]);

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
            {buildStatus && (
              <Badge
                variant={
                  buildStatus === "succeeded"
                    ? "default"
                    : buildStatus === "failed"
                      ? "destructive"
                      : "secondary"
                }
              >
                build:{buildStatus}
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
                  buildStatus={buildStatus}
                  buildError={buildError}
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

          <aside className="flex h-full w-[360px] shrink-0 flex-col border-l border-border/60 bg-muted/10">
            <div className="border-b border-border/60 px-3 py-2">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Sparkles className="h-4 w-4" />
                Builder Chat
              </div>
            </div>
            <div className="min-h-0 flex-1 space-y-2 overflow-auto px-3 py-2">
              {chatLog.length === 0 ? (
                <p className="text-xs text-muted-foreground">Describe a UI change and the builder will generate file patch operations.</p>
              ) : (
                chatLog.map((line, idx) => (
                  <div key={`${idx}-${line.slice(0, 12)}`} className="rounded-md border border-border/50 bg-background p-2 text-xs">
                    {line}
                  </div>
                ))
              )}
            </div>
            <div className="border-t border-border/60 p-3">
              <div className="flex gap-2">
                <Input
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  placeholder="Make the header more bold..."
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      sendBuilderChat();
                    }
                  }}
                />
                <Button size="sm" onClick={sendBuilderChat}>Send</Button>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </Tabs>
  );
}
