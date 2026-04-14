"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import {
  isDraftDevFailureStatus,
  isDraftDevPendingStatus,
  isDraftDevServingStatus,
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
  previewAuthToken: string | null;
  previewRoute: string;
  previewTransportGeneration: number | null;
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
  previewAuthToken: string | null;
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
  const { transportKey, baseDocumentUrl, previewAuthToken } = action;
  if (!transportKey || !baseDocumentUrl) {
    if (!state.transportKey && !state.documentUrl) {
      return state;
    }
    return {
      transportKey: null,
      documentUrl: null,
    };
  }
  if (state.transportKey !== transportKey) {
    return {
      transportKey,
      documentUrl: appendPreviewRuntimeToken(baseDocumentUrl, previewAuthToken),
    };
  }
  const normalizedCurrent = stripRuntimeToken(state.documentUrl);
  if (normalizedCurrent === baseDocumentUrl) {
    return state;
  }
  return {
    transportKey,
    documentUrl: baseDocumentUrl,
  };
}

export function useBuilderPreviewTransport({
  sessionId,
  previewBaseUrl,
  previewAuthToken,
  previewRoute,
  previewTransportGeneration,
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
    });
  }, [hardReloadToken, previewBaseUrl, previewRoute]);

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

  useEffect(() => {
    dispatchDocumentState({
      type: "sync",
      transportKey,
      baseDocumentUrl,
      previewAuthToken: previewAuthToken || null,
    });
  }, [baseDocumentUrl, previewAuthToken, transportKey]);

  const documentUrl = documentState.documentUrl;

  const hasUsableFrame = Boolean(transportKey) && usableFrameKey === transportKey;

  const status = useMemo<PreviewTransportStatus>(() => {
    if (!sessionId) {
      return "idle";
    }
    if (isDraftDevFailureStatus(draftDevStatus) || lifecyclePhase === "error" || Boolean(lastError)) {
      return hasUsableFrame ? "reconnecting" : "failed";
    }
    if (
      hasUsableFrame
      && (
        isDraftDevPendingStatus(draftDevStatus)
        || lifecyclePhase === "ensuring"
        || lifecyclePhase === "recovering"
        || lifecyclePhase === "syncing"
      )
    ) {
      return "reconnecting";
    }
    if (isDraftDevServingStatus(draftDevStatus) && hasUsableFrame) {
      return "ready";
    }
    if (documentUrl || isDraftDevPendingStatus(draftDevStatus) || lifecyclePhase === "ensuring" || lifecyclePhase === "recovering" || lifecyclePhase === "syncing") {
      return hasUsableFrame ? "reconnecting" : "booting";
    }
    return hasUsableFrame ? "ready" : "idle";
  }, [documentUrl, draftDevStatus, hasUsableFrame, lastError, lifecyclePhase, sessionId]);

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
      draftDevStatus,
      lifecyclePhase,
      status,
      hasUsableFrame,
      previewAuthTokenPresent: Boolean(String(previewAuthToken || "").trim()),
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
    previewAuthToken,
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
