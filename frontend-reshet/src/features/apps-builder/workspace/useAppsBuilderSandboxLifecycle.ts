"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { publishedAppsService } from "@/services";
import {
  isDraftDevFailureStatus,
  isDraftDevPendingStatus,
  isDraftDevServingStatus,
} from "@/services";
import type { DraftDevSessionResponse, DraftDevSessionStatus } from "@/services";
import { filterAppsBuilderFiles } from "@/services/apps-builder-file-filter";
import {
  isCodingAgentRunActiveError,
  isDraftDevTransientBootstrapError,
  isDraftDevWarmupError,
  isDraftSandboxNotRunningError,
} from "@/features/apps-builder/workspace/draftDevErrors";

const DRAFT_DEV_SYNC_DEBOUNCE_MS = 800;
const DRAFT_DEV_HEARTBEAT_MS = 45_000;
const DRAFT_DEV_RECOVERY_ATTEMPTS = 3;
const DRAFT_DEV_RECOVERY_BACKOFF_MS = 700;
const DRAFT_DEV_WARMUP_POLL_MS = 2_000;

type EnsureReason = "startup" | "manual" | "recovering";

export type SandboxLifecyclePhase = "idle" | "ensuring" | "syncing" | "running" | "recovering" | "error";

type EnsureSessionOptions = {
  force?: boolean;
  reason?: EnsureReason;
};

type UseAppsBuilderSandboxLifecycleOptions = {
  appId: string;
  currentRevisionId: string | null;
  entryFile: string;
  files: Record<string, string>;
  hasActiveCodingRunLock: boolean;
  onSessionChange?: (session: DraftDevSessionResponse | null) => void;
  onRevisionFromSession?: (revisionId: string) => void;
};

type UseAppsBuilderSandboxLifecycleResult = {
  phase: SandboxLifecyclePhase;
  draftDevSessionId: string | null;
  draftDevStatus: DraftDevSessionStatus | null;
  draftDevError: string | null;
  previewAssetUrl: string | null;
  previewAuthToken: string | null;
  previewLoadingMessage: string;
  publishLockMessage: string | null;
  isReady: boolean;
  isBusy: boolean;
  canRetry: boolean;
  actionDisabledReason: string | null;
  hydrateFromBuilderSession: (session?: DraftDevSessionResponse | null) => void;
  ensureDraftDevSession: (options?: EnsureSessionOptions) => Promise<DraftDevSessionResponse | null>;
  retryEnsureDraftDevSession: () => Promise<DraftDevSessionResponse | null>;
};

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

function normalizePreviewSessionUrlForReloadCompare(url: string | null | undefined): string {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    parsed.searchParams.delete("preview_token");
    parsed.searchParams.delete("runtime_preview_token");
    const normalizedPath = parsed.pathname.endsWith("/") ? parsed.pathname.slice(0, -1) : parsed.pathname;
    parsed.pathname = normalizedPath || "/";
    parsed.search = parsed.searchParams.toString();
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return String(url).trim();
  }
}

function withPreviewBuildReloadKey(
  url: string | null | undefined,
  buildId: string | null | undefined,
  buildSeq: number | null | undefined,
): string | null {
  const rawUrl = String(url || "").trim();
  if (!rawUrl) {
    return null;
  }
  const normalizedBuildId = String(buildId || "").trim();
  const normalizedBuildSeq = Number(buildSeq || 0);
  const buildKey = normalizedBuildId || (normalizedBuildSeq > 0 ? `seq-${normalizedBuildSeq}` : "");
  if (!buildKey) {
    return rawUrl;
  }
  try {
    const parsed = new URL(rawUrl);
    parsed.searchParams.set("__preview_build", buildKey);
    return parsed.toString();
  } catch {
    const separator = rawUrl.includes("?") ? "&" : "?";
    return `${rawUrl}${separator}__preview_build=${encodeURIComponent(buildKey)}`;
  }
}

function isWarmupRecoverySession(session: DraftDevSessionResponse | null | undefined): boolean {
  if (!session) return false;
  return isDraftDevWarmupError(session.last_error || null) && !isDraftDevServingStatus(session.status);
}

export function useAppsBuilderSandboxLifecycle({
  appId,
  currentRevisionId,
  entryFile,
  files,
  hasActiveCodingRunLock,
  onSessionChange,
  onRevisionFromSession,
}: UseAppsBuilderSandboxLifecycleOptions): UseAppsBuilderSandboxLifecycleResult {
  const [phase, setPhase] = useState<SandboxLifecyclePhase>("idle");
  const [draftDevSessionId, setDraftDevSessionId] = useState<string | null>(null);
  const [draftDevStatus, setDraftDevStatus] = useState<DraftDevSessionStatus | null>(null);
  const [draftDevError, setDraftDevError] = useState<string | null>(null);
  const [previewAssetUrl, setPreviewAssetUrl] = useState<string | null>(null);
  const [previewAuthToken, setPreviewAuthToken] = useState<string | null>(null);
  const [publishLockMessage, setPublishLockMessage] = useState<string | null>(null);
  const [recoveryExhausted, setRecoveryExhausted] = useState(false);

  const ensureInFlightRef = useRef<Promise<DraftDevSessionResponse | null> | null>(null);
  const syncInFlightRef = useRef<Promise<DraftDevSessionResponse | null> | null>(null);
  const syncFingerprintRef = useRef<string>("");
  const currentSyncFingerprintRef = useRef<string>("");
  const revisionFingerprintSeedRef = useRef<string | null>(null);
  const latestSessionPayloadRef = useRef<DraftDevSessionResponse | null>(null);
  const draftDevErrorRef = useRef<string | null>(null);
  const sessionSnapshotRef = useRef<{
    sessionId: string | null;
    status: DraftDevSessionStatus | null;
    previewUrl: string | null;
  }>({
    sessionId: null,
    status: null,
    previewUrl: null,
  });

  const filteredFiles = useMemo(() => filterAppsBuilderFiles(files), [files]);
  const currentSyncFingerprint = useMemo(
    () => buildDraftDevSyncFingerprint(entryFile, filteredFiles),
    [entryFile, filteredFiles],
  );

  useEffect(() => {
    draftDevErrorRef.current = draftDevError;
  }, [draftDevError]);

  const applySession = useCallback((session: DraftDevSessionResponse, options?: { markSynced?: boolean }) => {
    const warmupRecovery = isWarmupRecoverySession(session);
    latestSessionPayloadRef.current = session;
    setDraftDevSessionId(session.session_id || null);
    setDraftDevStatus((session.status as DraftDevSessionStatus | undefined) || null);
    setDraftDevError(warmupRecovery ? null : session.last_error || null);
    setPreviewAuthToken(session.preview_auth_token || null);
    setRecoveryExhausted(false);

    const nextPreviewUrl = withPreviewBuildReloadKey(
      session.preview_url || null,
      session.current_preview_build_id || null,
      session.preview_build_seq ?? 0,
    );
    setPreviewAssetUrl((current) => {
      const currentNormalized = normalizePreviewSessionUrlForReloadCompare(current);
      const nextNormalized = normalizePreviewSessionUrlForReloadCompare(nextPreviewUrl);
      if (current && nextPreviewUrl && currentNormalized === nextNormalized) {
        return current;
      }
      return nextPreviewUrl;
    });

    if (options?.markSynced) {
      syncFingerprintRef.current = currentSyncFingerprintRef.current;
    }

    if (isDraftDevServingStatus(session.status as DraftDevSessionStatus | undefined)) {
      setPhase("running");
    } else if (warmupRecovery) {
      setPhase("recovering");
    } else if (isDraftDevPendingStatus(session.status as DraftDevSessionStatus | undefined)) {
      setPhase((prev) => (prev === "recovering" ? "recovering" : "ensuring"));
    } else if (isDraftDevFailureStatus(session.status as DraftDevSessionStatus | undefined)) {
      setPhase("error");
    } else {
      setPhase("idle");
    }

    const revisionId = String(session.revision_id || "").trim();
    if (revisionId) {
      onRevisionFromSession?.(revisionId);
    }
    onSessionChange?.(session);
  }, [onRevisionFromSession, onSessionChange]);

  const clearSession = useCallback(() => {
    latestSessionPayloadRef.current = null;
    setDraftDevSessionId(null);
    setDraftDevStatus(null);
    setDraftDevError(null);
    setPreviewAssetUrl(null);
    setPreviewAuthToken(null);
    setPhase("idle");
    onSessionChange?.(null);
  }, [onSessionChange]);

  const hydrateFromBuilderSession = useCallback((session?: DraftDevSessionResponse | null) => {
    if (!session) {
      clearSession();
      return;
    }
    applySession(session, { markSynced: true });
  }, [applySession, clearSession]);

  const ensureDraftDevSession = useCallback(async (options?: EnsureSessionOptions) => {
    const reason = options?.reason || "manual";
    const force = Boolean(options?.force);

    const reusableSession = latestSessionPayloadRef.current;
    const hasReusableRunningSession =
      !force
      && isDraftDevServingStatus(reusableSession?.status)
      && Boolean(reusableSession?.session_id)
      && Boolean(reusableSession?.preview_url)
      && !draftDevErrorRef.current;
    if (hasReusableRunningSession) {
      return reusableSession || null;
    }

    if (ensureInFlightRef.current) {
      return ensureInFlightRef.current;
    }

    const ensurePromise = (async () => {
      setPublishLockMessage(null);
      setDraftDevError(null);
      setPhase(reason === "recovering" ? "recovering" : "ensuring");

      let lastError: unknown = null;
      for (let attempt = 0; attempt < DRAFT_DEV_RECOVERY_ATTEMPTS; attempt += 1) {
        try {
          const session = await publishedAppsService.ensureDraftDevSession(appId);
          applySession(session, { markSynced: true });
          return session;
        } catch (err) {
          lastError = err;
          if (!isDraftDevTransientBootstrapError(err) || attempt === DRAFT_DEV_RECOVERY_ATTEMPTS - 1) {
            if (isCodingAgentRunActiveError(err)) {
              throw err;
            }
            setRecoveryExhausted(isDraftDevTransientBootstrapError(err));
            const message = err instanceof Error ? err.message : "Failed to start preview sandbox";
            setDraftDevError(message);
            setPreviewAssetUrl(null);
            setPhase("error");
            throw err instanceof Error ? err : new Error(message);
          }
          setPhase("recovering");
          await wait(DRAFT_DEV_RECOVERY_BACKOFF_MS * (attempt + 1));
        }
      }

      setRecoveryExhausted(true);
      const finalError = lastError instanceof Error ? lastError : new Error("Failed to recover preview sandbox");
      setDraftDevError(finalError.message);
      setPreviewAssetUrl(null);
      setPhase("error");
      throw finalError;
    })().finally(() => {
      ensureInFlightRef.current = null;
    });

    ensureInFlightRef.current = ensurePromise;
    return ensurePromise;
  }, [appId, applySession]);

  const syncDraftDevSession = useCallback(async (fingerprint: string) => {
    if (!currentRevisionId || !draftDevSessionId || !isDraftDevServingStatus(draftDevStatus)) {
      return null;
    }
    if (syncInFlightRef.current) {
      return syncInFlightRef.current;
    }

    const syncPromise = (async () => {
      setPhase("syncing");
      try {
        const session = await publishedAppsService.syncDraftDevSession(appId, {
          files: filteredFiles,
          entry_file: entryFile,
          revision_id: currentRevisionId,
        });
        applySession(session, { markSynced: true });
        syncFingerprintRef.current = fingerprint;
        return session;
      } catch (err) {
        if (isCodingAgentRunActiveError(err)) {
          setPhase("running");
          return null;
        }

        if (isDraftSandboxNotRunningError(err)) {
          setDraftDevError(null);
          setPhase("recovering");
          try {
            const session = await ensureDraftDevSession({ force: true, reason: "recovering" });
            syncFingerprintRef.current = fingerprint;
            return session;
          } catch (ensureErr) {
            if (isCodingAgentRunActiveError(ensureErr)) {
              setDraftDevError(null);
              return null;
            }
            const message = ensureErr instanceof Error ? ensureErr.message : "Failed to recover preview sandbox";
            setDraftDevError(message);
            setPreviewAssetUrl(null);
            setPhase("error");
            throw ensureErr;
          }
        }

        const message = err instanceof Error ? err.message : "Failed to sync draft preview sandbox";
        setDraftDevError(message);
        setPhase("error");
        throw err instanceof Error ? err : new Error(message);
      }
    })().finally(() => {
      syncInFlightRef.current = null;
    });

    syncInFlightRef.current = syncPromise;
    return syncPromise;
  }, [appId, applySession, currentRevisionId, draftDevSessionId, draftDevStatus, ensureDraftDevSession, entryFile, filteredFiles]);

  const retryEnsureDraftDevSession = useCallback(async () => {
    setRecoveryExhausted(false);
    try {
      return await ensureDraftDevSession({ force: true, reason: "manual" });
    } catch (err) {
      if (isCodingAgentRunActiveError(err)) {
        setDraftDevError(null);
        setPhase("idle");
        return null;
      }
      throw err;
    }
  }, [ensureDraftDevSession]);

  useEffect(() => {
    sessionSnapshotRef.current = {
      sessionId: draftDevSessionId,
      status: draftDevStatus,
      previewUrl: previewAssetUrl,
    };
  }, [draftDevSessionId, draftDevStatus, previewAssetUrl]);

  useEffect(() => {
    currentSyncFingerprintRef.current = currentSyncFingerprint;
  }, [currentSyncFingerprint]);

  useEffect(() => {
    if (!currentRevisionId) {
      syncFingerprintRef.current = "";
      revisionFingerprintSeedRef.current = null;
      return;
    }
    if (revisionFingerprintSeedRef.current === currentRevisionId) {
      return;
    }
    revisionFingerprintSeedRef.current = currentRevisionId;
    syncFingerprintRef.current = currentSyncFingerprint;
  }, [currentRevisionId, currentSyncFingerprint]);

  // Reset local lifecycle state when the workspace scope changes.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setPhase("idle");
    setDraftDevSessionId(null);
    setDraftDevStatus(null);
    setDraftDevError(null);
    setPreviewAssetUrl(null);
    setPreviewAuthToken(null);
    setPublishLockMessage(null);
    setRecoveryExhausted(false);
    syncFingerprintRef.current = "";
    revisionFingerprintSeedRef.current = null;
    latestSessionPayloadRef.current = null;
    ensureInFlightRef.current = null;
    syncInFlightRef.current = null;
  }, [appId]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    if (!currentRevisionId) {
      return;
    }
    if (hasActiveCodingRunLock) {
      return;
    }

    const snapshot = sessionSnapshotRef.current;
    const hasReusableSession =
      isDraftDevServingStatus(snapshot.status)
      && Boolean(snapshot.sessionId)
      && Boolean(snapshot.previewUrl);

    if (hasReusableSession || isDraftDevPendingStatus(snapshot.status)) {
      return;
    }

    void ensureDraftDevSession({ reason: "startup" }).catch((err) => {
      if (isCodingAgentRunActiveError(err)) {
        setDraftDevError(null);
      }
    });
  }, [currentRevisionId, ensureDraftDevSession, hasActiveCodingRunLock]);

  useEffect(() => {
    if (!currentRevisionId) {
      syncFingerprintRef.current = "";
      return;
    }
    if (hasActiveCodingRunLock) {
      return;
    }
    if (!draftDevSessionId || !isDraftDevServingStatus(draftDevStatus)) {
      return;
    }

    const fingerprint = currentSyncFingerprint;
    if (syncFingerprintRef.current === fingerprint) {
      return;
    }

    const timer = window.setTimeout(() => {
      void syncDraftDevSession(fingerprint).catch(() => {
        // Errors are handled and materialized in local lifecycle state.
      });
    }, DRAFT_DEV_SYNC_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [
    currentRevisionId,
    currentSyncFingerprint,
    draftDevSessionId,
    draftDevStatus,
    hasActiveCodingRunLock,
    syncDraftDevSession,
  ]);

  useEffect(() => {
    if (!draftDevSessionId) {
      return;
    }

    const interval = window.setInterval(() => {
      publishedAppsService
        .heartbeatDraftDevSessionQuiet(appId)
        .then((result) => {
          if (result.publish_locked) {
            setPublishLockMessage(result.message || "Publish is running. Preview session lock is expected.");
            return;
          }
          if (result.session) {
            setPublishLockMessage(null);
            applySession(result.session);
          }
        })
        .catch(() => {
          // Heartbeat failures should not hard-break editing.
        });
    }, DRAFT_DEV_HEARTBEAT_MS);

    return () => {
      window.clearInterval(interval);
    };
  }, [appId, applySession, draftDevSessionId]);

  useEffect(() => {
    if (!draftDevSessionId) {
      return;
    }
    const latestSession = latestSessionPayloadRef.current;
    if (!isWarmupRecoverySession(latestSession)) {
      return;
    }

    const timer = window.setTimeout(() => {
      publishedAppsService
        .heartbeatDraftDevSessionQuiet(appId)
        .then((result) => {
          if (result.session) {
            applySession(result.session);
          }
        })
        .catch(() => {
          // Keep polling while the sandbox is still warming up.
        });
    }, DRAFT_DEV_WARMUP_POLL_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [appId, applySession, draftDevSessionId, draftDevStatus, phase]);

  const isReady =
    isDraftDevServingStatus(draftDevStatus)
    && Boolean(draftDevSessionId)
    && Boolean(previewAssetUrl)
    && !draftDevError;

  const isBusy = phase === "ensuring" || phase === "recovering" || phase === "syncing";

  const actionDisabledReason = useMemo(() => {
    if (phase === "syncing") {
      return "Syncing latest changes to sandbox...";
    }
    if (phase === "ensuring" || phase === "recovering" || isDraftDevPendingStatus(draftDevStatus)) {
      return "Waiting for sandbox to finish loading...";
    }
    if (isDraftDevFailureStatus(draftDevStatus) || draftDevError) {
      return "Sandbox is unavailable. Retry to continue.";
    }
    if (draftDevStatus === "stopped" || !draftDevSessionId || !previewAssetUrl) {
      return "Sandbox is not running yet.";
    }
    return null;
  }, [draftDevError, draftDevSessionId, draftDevStatus, phase, previewAssetUrl]);

  const previewLoadingMessage = useMemo(() => {
    if (phase === "syncing") {
      return "Syncing latest changes to sandbox...";
    }
    if (phase === "recovering") {
      return "Recovering preview sandbox...";
    }
    if (phase === "ensuring" || isDraftDevPendingStatus(draftDevStatus)) {
      return "Starting preview sandbox...";
    }
    if (!isReady) {
      return "Waiting for preview sandbox...";
    }
    return "Warming preview sandbox...";
  }, [draftDevStatus, isReady, phase]);

  const canRetry = (phase === "error" || recoveryExhausted || Boolean(draftDevError)) && !isBusy;

  return {
    phase,
    draftDevSessionId,
    draftDevStatus,
    draftDevError,
    previewAssetUrl,
    previewAuthToken,
    previewLoadingMessage,
    publishLockMessage,
    isReady,
    isBusy,
    canRetry,
    actionDisabledReason,
    hydrateFromBuilderSession,
    ensureDraftDevSession,
    retryEnsureDraftDevSession,
  };
}
