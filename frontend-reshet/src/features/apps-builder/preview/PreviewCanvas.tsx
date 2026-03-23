"use client";

import { forwardRef, useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
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

function resolveWarmupStage(
  devStatus: DraftDevStatus | null | undefined,
  lifecyclePhase: SandboxLifecyclePhase | null | undefined,
  previewSrc: string | null,
  isFrameVisible: boolean,
): "sandbox" | "dependencies" | "preview" {
  if (previewSrc || isFrameVisible || devStatus === "serving" || devStatus === "running") {
    return "preview";
  }
  if (devStatus === "building" || lifecyclePhase === "syncing") {
    return "dependencies";
  }
  return "sandbox";
}

function PreviewWarmupState({
  title,
  detail,
  stage,
}: {
  title: string;
  detail: string;
  stage: "sandbox" | "dependencies" | "preview";
}) {
  const steps: Array<{ key: "sandbox" | "dependencies" | "preview"; label: string }> = [
    { key: "sandbox", label: "Starting sandbox" },
    { key: "dependencies", label: "Installing dependencies" },
    { key: "preview", label: "Connecting preview" },
  ];
  const activeIndex = steps.findIndex((step) => step.key === stage);
  const currentStep = steps[Math.max(activeIndex, 0)]?.label || "Preparing preview";

  return (
    <div className="w-full max-w-sm rounded-md border border-black/8 bg-white/92 px-5 py-4 shadow-[0_24px_60px_-40px_rgba(15,23,42,0.35)] backdrop-blur">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground/65">
            Preview
          </div>
          <div className="mt-2 text-[15px] font-medium tracking-[-0.01em] text-foreground">
            {title}
          </div>
          <div className="mt-1 text-[12px] leading-5 text-muted-foreground">
            {detail}
          </div>
        </div>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-black/8 bg-black/[0.03] text-foreground/70">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        </div>
      </div>

      <div className="mt-4 space-y-2">
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>{currentStep}</span>
          <span>Loading</span>
        </div>
        <div className="flex gap-1">
          {steps.map((step, index) => {
            const state =
              index < activeIndex ? "done" : index === activeIndex ? "active" : "pending";
            return (
              <div
                key={step.key}
                className={cn(
                  "h-[3px] flex-1 rounded-full transition-colors",
                  state === "done" && "bg-foreground/55",
                  state === "active" && "bg-foreground/80 animate-pulse",
                  state === "pending" && "bg-black/8",
                )}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
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
    const [isFrameVisible, setIsFrameVisible] = useState(false);
    const [resolvedPreviewSrc, setResolvedPreviewSrc] = useState<string | null>(null);
    const [showTransientOverlay, setShowTransientOverlay] = useState(false);
    const [lastUsablePreviewKey, setLastUsablePreviewKey] = useState<string | null>(null);

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
      && normalizedPreviewKey === lastUsablePreviewKey
      && Boolean(resolvedPreviewSrc);
    const warmupMessage = String(loadingMessage || "").trim() || (isPending ? "Starting draft preview..." : "Warming preview sandbox...");
    const previewSrc = hasEstablishedPreview ? resolvedPreviewSrc : (canLoadFrame || isTransientSameSessionPending ? resolvedPreviewSrc : null);
    const warmupStage = resolveWarmupStage(devStatus, lifecyclePhase, previewSrc, isFrameVisible);
    const warmupTitle =
      warmupStage === "sandbox"
        ? "Preparing draft preview"
        : warmupStage === "dependencies"
          ? "Installing app dependencies"
          : "Connecting live preview";
    const warmupDetail =
      warmupStage === "sandbox"
        ? "Creating the workspace and bootstrapping the draft sandbox."
        : warmupStage === "dependencies"
          ? "First startup can take longer while the sandbox installs the starter app."
          : warmupMessage;
    const showWarmupOverlay =
      !hasSessionError
      && !hasFailed
      && (
        (((isPending && !previewSrc) && !isTransientSameSessionPending) || (previewSrc && !isFrameVisible) || showTransientOverlay)
        || !previewUrl
      );

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
        setLastUsablePreviewKey(null);
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
      const nextUsablePreviewKey = normalizePreviewKey(previewUrl);
      setLastUsablePreviewKey(nextUsablePreviewKey);
      logPreviewCanvasDebug("frame_load", {
        previewUrl: previewUrl || null,
        resolvedPreviewSrc,
        normalizedPreviewKey: nextUsablePreviewKey,
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

        {showWarmupOverlay && (
          <div
            data-testid="preview-warmup-overlay"
            className="absolute inset-0 flex items-center justify-center bg-background/72 px-6 text-sm text-muted-foreground backdrop-blur-sm"
          >
            <PreviewWarmupState title={warmupTitle} detail={warmupDetail} stage={warmupStage} />
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
      </div>
    );
  },
);
