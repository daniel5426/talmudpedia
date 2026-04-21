"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import {
  isDraftDevFailureStatus,
  isDraftDevPendingStatus,
  type DraftDevSessionStatus,
} from "@/services";
import type { SandboxLifecyclePhase } from "@/features/apps-builder/workspace/useAppsBuilderSandboxLifecycle";
import {
  appendPreviewRuntimeToken,
  buildBuilderPreviewDocumentUrl,
  logBuilderPreviewDebug,
  type PreviewTransportStatus,
} from "@/features/apps-builder/preview/previewTransport";

type UseBuilderPreviewTransportOptions = {
  sessionId: string | null;
  previewBaseUrl: string | null;
  previewRoute: string;
  previewTransportGeneration: number | null;
  livePreviewStatus: "booting" | "building" | "ready" | "failed_keep_last_good" | "failed_no_build" | "recovering" | null;
  livePreviewLastSuccessfulBuildId: string | null;
  livePreviewError: string | null;
  hardReloadToken: number;
  draftDevStatus: DraftDevSessionStatus | null;
  lifecyclePhase: SandboxLifecyclePhase | null;
  lastError: string | null;
};

export type BuilderPreviewTransportState = {
  sessionId: string | null;
  transportGeneration: number | null;
  transportKey: string | null;
  documentUrl: string | null;
  previewRoute: string;
  status: PreviewTransportStatus;
  hasUsableFrame: boolean;
  lastError: string | null;
  markFrameUsable: (transportKey: string | null) => void;
  clearUsableFrame: (transportKey: string | null) => void;
};

type DocumentState = {
  transportKey: string | null;
  documentUrl: string | null;
};

type DocumentAction = {
  type: "sync";
  transportKey: string | null;
  baseDocumentUrl: string | null;
  hasUsableFrame: boolean;
};

function stripRuntimeToken(value: string | null): string | null {
  if (!value) {
    return null;
  }
  try {
    const parsed = new URL(value);
    parsed.searchParams.delete("runtime_token");
    return parsed.toString();
  } catch {
    return value.replace(/([?&])runtime_token=[^&]+(&)?/, (_match, prefix, suffix) => (prefix === "?" && suffix ? "?" : suffix ? prefix : ""));
  }
}

function documentStateReducer(state: DocumentState, action: DocumentAction): DocumentState {
  if (action.type !== "sync") {
    return state;
  }
  const { transportKey, baseDocumentUrl, hasUsableFrame } = action;
  if (!transportKey || !baseDocumentUrl) {
    if (!state.transportKey && !state.documentUrl) {
      return state;
    }
    return {
      transportKey: null,
      documentUrl: null,
    };
  }
  const nextDocumentUrl = hasUsableFrame
    ? baseDocumentUrl
    : baseDocumentUrl;
  if (state.transportKey !== transportKey) {
    return {
      transportKey,
      documentUrl: nextDocumentUrl,
    };
  }
  if (state.documentUrl === nextDocumentUrl) {
    return state;
  }
  const normalizedCurrent = stripRuntimeToken(state.documentUrl);
  if (normalizedCurrent === baseDocumentUrl && hasUsableFrame) {
    return state;
  }
  return {
    transportKey,
    documentUrl: nextDocumentUrl,
  };
}

export function useBuilderPreviewTransport({
  sessionId,
  previewBaseUrl,
  previewRoute,
  previewTransportGeneration,
  livePreviewStatus,
  livePreviewLastSuccessfulBuildId,
  livePreviewError,
  hardReloadToken,
  draftDevStatus,
  lifecyclePhase,
  lastError,
}: UseBuilderPreviewTransportOptions): BuilderPreviewTransportState {
  const [usableFrameKey, setUsableFrameKey] = useState<string | null>(null);
  const [documentState, dispatchDocumentState] = useReducer(documentStateReducer, {
    transportKey: null,
    documentUrl: null,
  });
  const loggedSnapshotRef = useRef<string>("");

  const baseDocumentUrl = useMemo(() => {
    if (!previewBaseUrl) {
      return null;
    }
    return buildBuilderPreviewDocumentUrl({
      baseUrl: previewBaseUrl,
      route: previewRoute,
      reloadToken: hardReloadToken,
      buildId: livePreviewLastSuccessfulBuildId,
    });
  }, [hardReloadToken, livePreviewLastSuccessfulBuildId, previewBaseUrl, previewRoute]);

  const transportGeneration = useMemo(() => {
    if (!sessionId) {
      return null;
    }
    const serverGeneration = Math.max(0, Number(previewTransportGeneration || 0));
    const reloadGeneration = Math.max(0, Number(hardReloadToken || 0));
    return serverGeneration * 1000 + reloadGeneration;
  }, [hardReloadToken, previewTransportGeneration, sessionId]);

  const transportKey = useMemo(() => {
    if (!sessionId || transportGeneration === null) {
      return null;
    }
    return `${sessionId}:${transportGeneration}`;
  }, [sessionId, transportGeneration]);

  const hasUsableFrame = Boolean(transportKey) && usableFrameKey === transportKey;

  useEffect(() => {
    dispatchDocumentState({
      type: "sync",
      transportKey,
      baseDocumentUrl,
      hasUsableFrame,
    });
  }, [baseDocumentUrl, hasUsableFrame, transportKey]);

  const documentUrl = documentState.documentUrl;

  const status = useMemo<PreviewTransportStatus>(() => {
    if (!sessionId) {
      return "idle";
    }
    if (isDraftDevFailureStatus(draftDevStatus) || lifecyclePhase === "error" || Boolean(lastError)) {
      return hasUsableFrame ? "reconnecting" : "failed";
    }
    if (livePreviewStatus === "failed_keep_last_good") {
      return hasUsableFrame ? "ready" : "failed";
    }
    if (livePreviewStatus === "failed_no_build") {
      return "failed";
    }
    if (livePreviewStatus === "booting" || livePreviewStatus === "building") {
      return hasUsableFrame ? "reconnecting" : "booting";
    }
    if (livePreviewStatus === "recovering") {
      return hasUsableFrame ? "reconnecting" : "booting";
    }
    if (livePreviewStatus === "ready" && hasUsableFrame) {
      return "ready";
    }
    if (
      hasUsableFrame
      && !isDraftDevPendingStatus(draftDevStatus)
      && lifecyclePhase !== "ensuring"
      && lifecyclePhase !== "recovering"
      && lifecyclePhase !== "syncing"
    ) {
      return "ready";
    }
    if (hasUsableFrame && (
      isDraftDevPendingStatus(draftDevStatus)
      || lifecyclePhase === "ensuring"
      || lifecyclePhase === "recovering"
      || lifecyclePhase === "syncing"
    )) {
      return "reconnecting";
    }
    if (documentUrl || isDraftDevPendingStatus(draftDevStatus) || lifecyclePhase === "ensuring" || lifecyclePhase === "recovering" || lifecyclePhase === "syncing") {
      return hasUsableFrame ? "reconnecting" : "booting";
    }
    return hasUsableFrame ? "ready" : "idle";
  }, [documentUrl, draftDevStatus, hasUsableFrame, lastError, lifecyclePhase, livePreviewStatus, sessionId]);

  const markFrameUsable = useCallback((nextTransportKey: string | null) => {
    if (!nextTransportKey) {
      return;
    }
    setUsableFrameKey(nextTransportKey);
  }, []);

  const clearUsableFrame = useCallback((nextTransportKey: string | null) => {
    setUsableFrameKey((current) => {
      if (!current) {
        return current;
      }
      if (!nextTransportKey || current === nextTransportKey) {
        return null;
      }
      return current;
    });
  }, []);

  useEffect(() => {
    const snapshot = {
      sessionId,
      transportGeneration,
      transportKey,
      previewRoute,
      previewBaseUrl,
      baseDocumentUrl,
      documentUrl,
      livePreviewStatus,
      livePreviewLastSuccessfulBuildId,
      livePreviewError,
      draftDevStatus,
      lifecyclePhase,
      status,
      hasUsableFrame,
      previewAuthTokenPresent: false,
      lastError: lastError || null,
    };
    const serialized = JSON.stringify(snapshot);
    if (loggedSnapshotRef.current === serialized) {
      return;
    }
    loggedSnapshotRef.current = serialized;
    logBuilderPreviewDebug("preview-transport", "state", snapshot);
  }, [
    baseDocumentUrl,
    documentUrl,
    draftDevStatus,
    hasUsableFrame,
    lastError,
    lifecyclePhase,
    livePreviewError,
    livePreviewLastSuccessfulBuildId,
    livePreviewStatus,
      previewBaseUrl,
    previewRoute,
    sessionId,
    status,
    transportGeneration,
    transportKey,
  ]);

  return {
    sessionId,
    transportGeneration,
    transportKey,
    documentUrl,
    previewRoute,
    status,
    hasUsableFrame,
    lastError,
    markFrameUsable,
    clearUsableFrame,
  };
}
