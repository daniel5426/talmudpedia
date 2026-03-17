"use client";

import { forwardRef, useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  isDraftDevFailureStatus,
  isDraftDevPendingStatus,
  isDraftDevServingStatus,
} from "@/services";
import type { SandboxLifecyclePhase } from "@/features/apps-builder/workspace/useAppsBuilderSandboxLifecycle";

type DraftDevStatus =
  | "starting"
  | "building"
  | "serving"
  | "degraded"
  | "running"
  | "stopping"
  | "stopped"
  | "expired"
  | "error";

type PreviewCanvasProps = {
  previewUrl?: string | null;
  previewAuthToken?: string | null;
  forceReady?: boolean;
  devStatus?: DraftDevStatus | null;
  devError?: string | null;
  lifecyclePhase?: SandboxLifecyclePhase | null;
  loadingMessage?: string | null;
  canRetry?: boolean;
  onRetry?: (() => void) | null;
};

const PREVIEW_REVEAL_DELAY_MS = 350;
const PREVIEW_MAX_HIDDEN_MS = 8_000;
const PREVIEW_TRANSIENT_OVERLAY_DELAY_MS = 700;
const PREVIEW_AUTH_MESSAGE_TYPE = "talmudpedia.preview-auth.v1";
const PREVIEW_DEBUG_BRIDGE_MESSAGE_TYPE = "talmudpedia.preview-debug.v1";

function logPreviewCanvasDebug(event: string, fields: Record<string, unknown> = {}): void {
  if (typeof console === "undefined" || typeof console.info !== "function") {
    return;
  }
  console.info("[apps-builder][preview]", {
    event,
    ...fields,
  });
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

export const PreviewCanvas = forwardRef<HTMLIFrameElement, PreviewCanvasProps>(
  function PreviewCanvas(
    { previewUrl, previewAuthToken, forceReady = false, devStatus, devError, lifecyclePhase, loadingMessage, canRetry = false, onRetry = null },
    ref,
  ) {
    const revealTimerRef = useRef<number | null>(null);
    const failSafeTimerRef = useRef<number | null>(null);
    const transientOverlayTimerRef = useRef<number | null>(null);
    const frameRef = useRef<HTMLIFrameElement | null>(null);
    const lastUsablePreviewKeyRef = useRef<string | null>(null);
    const [isFrameVisible, setIsFrameVisible] = useState(false);
    const [resolvedPreviewSrc, setResolvedPreviewSrc] = useState<string | null>(null);
    const [showTransientOverlay, setShowTransientOverlay] = useState(false);

    const normalizePreviewKey = useCallback((value: string | null | undefined): string | null => {
      const raw = String(value || "").trim();
      if (!raw) return null;
      try {
        const parsed = new URL(raw);
        parsed.searchParams.delete("runtime_token");
        parsed.searchParams.delete("preview_token");
        parsed.searchParams.delete("runtime_preview_token");
        parsed.hash = "";
        return parsed.toString();
      } catch {
        return raw;
      }
    }, []);

    const clearTimers = useCallback(() => {
      if (revealTimerRef.current !== null) {
        window.clearTimeout(revealTimerRef.current);
        revealTimerRef.current = null;
      }
      if (failSafeTimerRef.current !== null) {
        window.clearTimeout(failSafeTimerRef.current);
        failSafeTimerRef.current = null;
      }
      if (transientOverlayTimerRef.current !== null) {
        window.clearTimeout(transientOverlayTimerRef.current);
        transientOverlayTimerRef.current = null;
      }
    }, []);

    useEffect(() => clearTimers, [clearTimers]);

    const isPending = isDraftDevPendingStatus(devStatus) || lifecyclePhase === "ensuring" || lifecyclePhase === "recovering" || lifecyclePhase === "syncing";
    const hasFailed = isDraftDevFailureStatus(devStatus) || lifecyclePhase === "error";
    const hasSessionError = Boolean(devError);
    const canLoadFrame = (forceReady || isDraftDevServingStatus(devStatus)) && Boolean(previewUrl) && !hasFailed && !hasSessionError;
    const hasEstablishedPreview = Boolean(resolvedPreviewSrc) && !hasFailed && !hasSessionError;
    const normalizedPreviewKey = normalizePreviewKey(previewUrl);
    const isTransientSameSessionPending =
      !canLoadFrame
      && !hasFailed
      && !hasSessionError
      && Boolean(normalizedPreviewKey)
      && normalizedPreviewKey === lastUsablePreviewKeyRef.current
      && Boolean(resolvedPreviewSrc);
    const warmupMessage = String(loadingMessage || "").trim() || (isPending ? "Starting draft preview..." : "Warming preview sandbox...");
    const previewSrc = hasEstablishedPreview ? resolvedPreviewSrc : (canLoadFrame || isTransientSameSessionPending ? resolvedPreviewSrc : null);

    useEffect(() => {
      logPreviewCanvasDebug("state", {
        previewUrl: previewUrl || null,
        resolvedPreviewSrc,
        canLoadFrame,
        hasEstablishedPreview,
        isFrameVisible,
        isPending,
        hasFailed,
        hasSessionError,
        devStatus: devStatus || null,
        lifecyclePhase: lifecyclePhase || null,
        isTransientSameSessionPending,
        showTransientOverlay,
      });
    }, [
      canLoadFrame,
      devStatus,
      hasEstablishedPreview,
      hasFailed,
      hasSessionError,
      isFrameVisible,
      isPending,
      isTransientSameSessionPending,
      lifecyclePhase,
      previewUrl,
      resolvedPreviewSrc,
      showTransientOverlay,
    ]);

    useEffect(() => {
      if (hasFailed || hasSessionError) {
        setResolvedPreviewSrc(null);
        lastUsablePreviewKeyRef.current = null;
        return;
      }
      if (!previewUrl) {
        return;
      }
      const nextBaseUrl = String(previewUrl || "").trim();
      setResolvedPreviewSrc((current) => {
        if (!nextBaseUrl) {
          return null;
        }
        if (current) {
          try {
            const parsedCurrent = new URL(current);
            const parsedNext = new URL(nextBaseUrl);
            const currentRuntimeToken = parsedCurrent.searchParams.get("runtime_token");
            parsedCurrent.searchParams.delete("runtime_token");
            if (!currentRuntimeToken && String(previewAuthToken || "").trim()) {
              return appendRuntimeTokenToUrl(nextBaseUrl, previewAuthToken);
            }
            if (parsedCurrent.toString() === parsedNext.toString()) {
              return current;
            }
          } catch {
            if (current.startsWith(nextBaseUrl)) {
              return current;
            }
          }
        }
        return appendRuntimeTokenToUrl(nextBaseUrl, previewAuthToken);
      });
    }, [hasFailed, hasSessionError, previewAuthToken, previewUrl]);

    const setFrameRef = useCallback(
      (node: HTMLIFrameElement | null) => {
        frameRef.current = node;
        if (typeof ref === "function") {
          ref(node);
          return;
        }
        if (ref) {
          (ref as MutableRefObject<HTMLIFrameElement | null>).current = node;
        }
      },
      [ref],
    );

    const postPreviewAuthToken = useCallback(() => {
      const frame = frameRef.current;
      if (!frame?.contentWindow || !hasEstablishedPreview) return;
      let targetOrigin = "*";
      try {
        targetOrigin = new URL(previewUrl || "").origin;
      } catch {
        // Keep wildcard fallback for malformed/non-URL src values.
      }
      frame.contentWindow.postMessage(
        {
          type: PREVIEW_AUTH_MESSAGE_TYPE,
          token: (previewAuthToken || "").trim() || null,
        },
        targetOrigin,
      );
      logPreviewCanvasDebug("auth_posted", {
        targetOrigin,
        hasEstablishedPreview,
        previewUrl: previewUrl || null,
        previewAuthTokenPresent: Boolean(String(previewAuthToken || "").trim()),
      });
    }, [hasEstablishedPreview, previewAuthToken, previewUrl]);

    useEffect(() => {
      clearTimers();
      setShowTransientOverlay(false);

      if (!previewSrc && !isTransientSameSessionPending) {
        setIsFrameVisible(false);
        return;
      }

      if (isTransientSameSessionPending) {
        transientOverlayTimerRef.current = window.setTimeout(() => {
          setShowTransientOverlay(true);
        }, PREVIEW_TRANSIENT_OVERLAY_DELAY_MS);
        return;
      }

      setIsFrameVisible(false);
      failSafeTimerRef.current = window.setTimeout(() => {
        setIsFrameVisible(true);
      }, PREVIEW_MAX_HIDDEN_MS);
    }, [clearTimers, isTransientSameSessionPending, previewSrc, previewUrl]);

    useEffect(() => {
      if (!hasEstablishedPreview) return;
      postPreviewAuthToken();
      const timer = window.setTimeout(() => {
        postPreviewAuthToken();
      }, 180);
      return () => {
        window.clearTimeout(timer);
      };
    }, [hasEstablishedPreview, postPreviewAuthToken]);

    useEffect(() => {
      const handleMessage = (event: MessageEvent) => {
        const data = event.data;
        if (!data || typeof data !== "object" || data.type !== PREVIEW_DEBUG_BRIDGE_MESSAGE_TYPE) {
          return;
        }
        logPreviewCanvasDebug("iframe_bridge", {
          origin: event.origin,
          ...(typeof data.payload === "object" && data.payload ? data.payload : {}),
        });
      };
      window.addEventListener("message", handleMessage);
      return () => {
        window.removeEventListener("message", handleMessage);
      };
    }, []);

    const handleFrameLoad = useCallback(() => {
      clearTimers();
      postPreviewAuthToken();
      setShowTransientOverlay(false);
      lastUsablePreviewKeyRef.current = normalizePreviewKey(previewUrl);
      logPreviewCanvasDebug("frame_load", {
        previewUrl: previewUrl || null,
        resolvedPreviewSrc,
        normalizedPreviewKey: lastUsablePreviewKeyRef.current,
      });
      revealTimerRef.current = window.setTimeout(() => {
        setIsFrameVisible(true);
        logPreviewCanvasDebug("frame_revealed", {
          previewUrl: previewUrl || null,
          resolvedPreviewSrc,
        });
      }, PREVIEW_REVEAL_DELAY_MS);
    }, [clearTimers, normalizePreviewKey, postPreviewAuthToken, previewUrl, resolvedPreviewSrc]);

    return (
      <div className="relative h-full w-full overflow-hidden bg-white">
        {previewSrc ? (
          <iframe
            ref={setFrameRef}
            title="App Preview"
            data-testid="preview-iframe"
            className={cn(
              "h-full w-full transition-opacity duration-300 ease-out",
              isFrameVisible ? "opacity-100" : "pointer-events-none opacity-0",
            )}
            sandbox="allow-same-origin allow-scripts allow-forms"
            src={previewSrc || "about:blank"}
            onLoad={handleFrameLoad}
          />
        ) : null}

        {(((isPending && !previewSrc) && !isTransientSameSessionPending) || (previewSrc && !isFrameVisible) || showTransientOverlay) && !hasSessionError && !hasFailed && (
          <div
            data-testid="preview-warmup-overlay"
            className="absolute inset-0 flex items-center justify-center gap-2 bg-background/70 text-sm text-muted-foreground"
          >
            <div className="w-full max-w-sm rounded-lg border border-border/60 bg-background/95 p-4 shadow-sm">
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>{warmupMessage}</span>
              </div>
              <div className="mt-3 space-y-2">
                <Skeleton className="h-3 w-5/6" />
                <Skeleton className="h-3 w-2/3" />
              </div>
            </div>
          </div>
        )}

        {(hasFailed || hasSessionError) && (
          <div className="absolute inset-0 overflow-auto bg-background/95 p-4 text-sm text-destructive">
            <div>{devError || "Draft preview session failed. Retry to restart the sandbox."}</div>
            {canRetry && onRetry ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={onRetry}
              >
                Retry sandbox
              </Button>
            ) : null}
          </div>
        )}

        {!isPending && !hasFailed && !previewUrl && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/70 px-6 text-center text-sm text-muted-foreground">
            Preview is unavailable until the draft dev session is running.
          </div>
        )}
      </div>
    );
  },
);
