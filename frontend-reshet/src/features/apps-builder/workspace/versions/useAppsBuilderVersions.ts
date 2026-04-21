"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { publishedAppsService } from "@/services";
import type { AppVersionListItem, PublishedAppRevision } from "@/services";

const PUBLISH_POLL_INTERVAL_MS = 2_000;
const PUBLISH_POLL_TIMEOUT_MS = 15 * 60_000;

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function parsePreviewBuildNotReadyMessage(err: unknown): string | null {
  const raw = err instanceof Error ? err.message : String(err || "");
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const code = String(parsed?.code || "").trim();
    if (code !== "VERSION_BUILD_NOT_READY") {
      return null;
    }
    const status = String(parsed?.build_status || "queued").trim() || "queued";
    const details = String(parsed?.build_error || "").trim();
    if (details) {
      return `Version preview build is ${status}: ${details}`;
    }
    return `Version preview build is ${status}.`;
  } catch {
    return null;
  }
}

type UseAppsBuilderVersionsOptions = {
  appId: string;
  currentRevisionId: string | null;
  onApplyRevision: (revision: PublishedAppRevision) => void;
  onRefreshState: () => Promise<void>;
  onError: (message: string | null) => void;
};

export function useAppsBuilderVersions({
  appId,
  currentRevisionId,
  onApplyRevision,
  onRefreshState,
  onError,
}: UseAppsBuilderVersionsOptions) {
  const [versions, setVersions] = useState<AppVersionListItem[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const selectedVersionIdRef = useRef<string | null>(null);
  const inspectedVersionIdRef = useRef<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<PublishedAppRevision | null>(null);
  const [inspectedVersionId, setInspectedVersionId] = useState<string | null>(null);
  const [inspectedPreviewUrl, setInspectedPreviewUrl] = useState<string | null>(null);
  const [isLoadingVersions, setIsLoadingVersions] = useState(false);
  const [isLoadingVersion, setIsLoadingVersion] = useState(false);
  const [isLoadingVersionPreview, setIsLoadingVersionPreview] = useState(false);
  const [inspectedPreviewNotice, setInspectedPreviewNotice] = useState<string | null>(null);
  const [isRestoringVersion, setIsRestoringVersion] = useState(false);
  const [isPublishingVersion, setIsPublishingVersion] = useState(false);
  const [publishStatus, setPublishStatus] = useState<string | null>(null);
  const lastMissingCurrentRevisionRefreshRef = useRef<string | null>(null);

  const loadVersion = useCallback(async (versionId: string, options: { inspect?: boolean } = {}) => {
    const shouldInspect = options.inspect ?? true;
    setIsLoadingVersion(true);
    if (shouldInspect) {
      setIsLoadingVersionPreview(true);
      setInspectedPreviewNotice(null);
    }
    try {
      const revision = await publishedAppsService.getVersion(appId, versionId);
      setSelectedVersion(revision);
      if (shouldInspect) {
        try {
          const previewRuntime = await publishedAppsService.getVersionPreviewRuntime(appId, versionId);
          inspectedVersionIdRef.current = versionId;
          setInspectedVersionId(versionId);
          setInspectedPreviewUrl(previewRuntime.preview_url || null);
        } catch (previewErr) {
          const notReadyMessage = parsePreviewBuildNotReadyMessage(previewErr);
          if (notReadyMessage) {
            inspectedVersionIdRef.current = versionId;
            setInspectedVersionId(versionId);
            setInspectedPreviewUrl(null);
            setInspectedPreviewNotice(notReadyMessage);
          } else {
            throw previewErr;
          }
        }
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load version");
    } finally {
      setIsLoadingVersion(false);
      setIsLoadingVersionPreview(false);
    }
  }, [appId, onError]);

  const refreshVersions = useCallback(async () => {
    setIsLoadingVersions(true);
    try {
      const list = await publishedAppsService.listVersions(appId, { limit: 100 });
      setVersions(list);

      const preferredVersionId = selectedVersionIdRef.current || list[0]?.id || null;
      if (preferredVersionId) {
        const stillExists = list.some((item) => item.id === preferredVersionId);
        const nextVersionId = stillExists ? preferredVersionId : list[0]?.id || null;
        setSelectedVersionId(nextVersionId);
        selectedVersionIdRef.current = nextVersionId;
        if (nextVersionId) {
          await loadVersion(nextVersionId, { inspect: stillExists && inspectedVersionIdRef.current === nextVersionId });
        } else {
          setSelectedVersion(null);
        }
      } else {
        setSelectedVersion(null);
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to list versions");
    } finally {
      setIsLoadingVersions(false);
    }
  }, [appId, loadVersion, onError]);

  useEffect(() => {
    setVersions([]);
    setSelectedVersion(null);
    setSelectedVersionId(null);
    selectedVersionIdRef.current = null;
    inspectedVersionIdRef.current = null;
    setInspectedVersionId(null);
    setInspectedPreviewUrl(null);
    setPublishStatus(null);
    lastMissingCurrentRevisionRefreshRef.current = null;
    void refreshVersions();
  }, [appId, refreshVersions]);

  useEffect(() => {
    const normalized = String(currentRevisionId || "").trim();
    if (!normalized) return;
    if (inspectedVersionId) return;
    if (selectedVersionIdRef.current === normalized) return;
    if (!versions.some((item) => item.id === normalized)) return;
    selectedVersionIdRef.current = normalized;
    setSelectedVersionId(normalized);
    void loadVersion(normalized, { inspect: false });
  }, [currentRevisionId, inspectedVersionId, loadVersion, versions]);

  useEffect(() => {
    const normalized = String(currentRevisionId || "").trim();
    if (!normalized) return;
    if (versions.some((item) => item.id === normalized)) {
      lastMissingCurrentRevisionRefreshRef.current = null;
      return;
    }
    if (isLoadingVersions) return;
    if (lastMissingCurrentRevisionRefreshRef.current === normalized) return;
    lastMissingCurrentRevisionRefreshRef.current = normalized;
    void refreshVersions();
  }, [currentRevisionId, isLoadingVersions, refreshVersions, versions]);

  const selectVersion = useCallback(async (versionId: string) => {
    setSelectedVersionId(versionId);
    selectedVersionIdRef.current = versionId;
    await loadVersion(versionId, { inspect: true });
  }, [loadVersion]);

  const clearInspectedVersion = useCallback(() => {
    inspectedVersionIdRef.current = null;
    setInspectedVersionId(null);
    setInspectedPreviewUrl(null);
    setInspectedPreviewNotice(null);
  }, []);

  const restoreSelectedVersion = useCallback(async (versionId?: string) => {
    const targetVersionId = String(versionId || selectedVersionIdRef.current || selectedVersionId || "").trim();
    if (!targetVersionId) return;
    setIsRestoringVersion(true);
    onError(null);
    try {
      const restored = await publishedAppsService.restoreVersion(appId, targetVersionId);
      onApplyRevision(restored);
      clearInspectedVersion();
      await onRefreshState();
      await refreshVersions();
      setSelectedVersionId(restored.id);
      selectedVersionIdRef.current = restored.id;
      setSelectedVersion(restored);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to restore selected version");
    } finally {
      setIsRestoringVersion(false);
    }
  }, [appId, clearInspectedVersion, onApplyRevision, onError, onRefreshState, refreshVersions, selectedVersionId]);

  const publishSelectedVersion = useCallback(async (versionId?: string) => {
    const targetVersionId = String(versionId || selectedVersionIdRef.current || selectedVersionId || "").trim();
    if (!targetVersionId) return;
    setIsPublishingVersion(true);
    onError(null);
    setPublishStatus("queued");

    try {
      const job = await publishedAppsService.publishVersion(appId, targetVersionId);
      setPublishStatus(job.status);

      let status = job.status;
      const startedAt = Date.now();
      while (status === "queued" || status === "running") {
        if (Date.now() - startedAt > PUBLISH_POLL_TIMEOUT_MS) {
          throw new Error("Publish timed out while waiting for completion");
        }
        await wait(PUBLISH_POLL_INTERVAL_MS);
        const current = await publishedAppsService.getPublishJobStatus(appId, job.job_id);
        status = current.status;
        setPublishStatus(status);
        if (status === "failed") {
          const diagnostics = Array.isArray(current.diagnostics) ? current.diagnostics : [];
          const primary = diagnostics.find((item) => item && typeof item === "object" && String((item as Record<string, unknown>).kind || "") === "publish_wait_build")
            || diagnostics[0];
          const baseMessage = (
            (primary as Record<string, unknown> | undefined)?.message as string | undefined
          ) || current.error || "Publish failed";
          const autoFix = diagnostics.find(
            (item) =>
              item &&
              typeof item === "object" &&
              String((item as Record<string, unknown>).kind || "") === "auto_fix_submission"
          ) as Record<string, unknown> | undefined;
          if (autoFix) {
            const autoFixRunId = String(autoFix.auto_fix_run_id || "").trim();
            if (autoFixRunId) {
              throw new Error(`${baseMessage} Auto-fix run queued: ${autoFixRunId}.`);
            }
            const skippedReason = String(autoFix.reason || "").trim();
            if (skippedReason) {
              throw new Error(`${baseMessage} Auto-fix skipped: ${skippedReason}.`);
            }
          }
          throw new Error(baseMessage);
        }
      }

      if (status !== "succeeded") {
        throw new Error("Publish ended in an unexpected state");
      }

      await Promise.all([onRefreshState(), refreshVersions()]);
    } catch (err) {
      setPublishStatus("failed");
      let message = err instanceof Error ? err.message : "Failed to publish selected version";
      try {
        const parsed = JSON.parse(message) as { message?: string };
        if (parsed?.message) {
          message = parsed.message;
        }
      } catch {
        // ignore non-JSON errors
      }
      onError(message);
    } finally {
      setIsPublishingVersion(false);
    }
  }, [appId, onError, onRefreshState, refreshVersions, selectedVersionId]);

  const selectedVersionMeta = useMemo(
    () => versions.find((item) => item.id === selectedVersionId) || null,
    [selectedVersionId, versions],
  );

  return {
    versions,
    selectedVersion,
    selectedVersionId,
    selectedVersionMeta,
    inspectedVersionId,
    inspectedPreviewUrl,
    inspectedPreviewNotice,
    isLoadingVersions,
    isLoadingVersion,
    isLoadingVersionPreview,
    isRestoringVersion,
    isPublishingVersion,
    publishStatus,
    refreshVersions,
    selectVersion,
    clearInspectedVersion,
    restoreSelectedVersion,
    publishSelectedVersion,
  };
}
