"use client";

import { forwardRef, useCallback, useEffect, useReducer, useRef, type MutableRefObject } from "react";
import { Check, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { PreviewLoadingState } from "@/features/apps-builder/preview/previewLoadingState";
import { logBuilderPreviewDebug, type PreviewTransportStatus } from "@/features/apps-builder/preview/previewTransport";

type PreviewCanvasProps = {
  previewUrl?: string | null;
  transportKey?: string | null;
  transportStatus?: PreviewTransportStatus | null;
  hasUsableFrame?: boolean;
  loadingMessage?: string | null;
  loadingState?: PreviewLoadingState | null;
  errorMessage?: string | null;
  canRetry?: boolean;
  onRetry?: (() => void) | null;
  onFrameReady?: ((transportKey: string | null) => void) | null;
  onFrameCleared?: ((transportKey: string | null) => void) | null;
};

type PreviewFrameState = { key: string; src: string };

type PreviewCanvasState = {
  visibleFrame: PreviewFrameState | null;
  stagedFrame: PreviewFrameState | null;
  clearedFrameKey: string | null;
};

type PreviewCanvasAction =
  | {
      type: "sync";
      previewUrl: string | null;
      transportKey: string | null;
    }
  | {
      type: "staged_loaded";
    }
  | {
      type: "cleared_ack";
    };

const PREVIEW_DEBUG_BRIDGE_MESSAGE_TYPE = "talmudpedia.preview-debug.v1";

function PreviewWarmupState({
  state,
}: {
  state: PreviewLoadingState;
}) {
  return (
    <div className="w-full max-w-md rounded-xl border border-black/8 bg-white/92 px-5 py-4 shadow-[0_24px_60px_-40px_rgba(15,23,42,0.35)] backdrop-blur">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground/65">
            Preview
          </div>
          <div className="mt-2 text-[15px] font-medium tracking-[-0.01em] text-foreground">
            {state.title}
          </div>
          <div className="mt-1 text-[12px] leading-5 text-muted-foreground">
            {state.detail}
          </div>
          <div className="mt-4 space-y-2.5">
            {state.steps.map((step) => (
              <div key={step.label} className="flex items-center gap-2.5 text-[12px]">
                <div
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                    step.status === "complete" && "border-emerald-300 bg-emerald-50 text-emerald-600",
                    step.status === "current" && "border-foreground/15 bg-black/[0.03] text-foreground/80",
                    step.status === "pending" && "border-black/10 bg-transparent text-muted-foreground/50",
                    step.status === "error" && "border-destructive/30 bg-destructive/10 text-destructive",
                  )}
                >
                  {step.status === "complete" ? (
                    <Check className="h-3 w-3" />
                  ) : step.status === "current" ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  )}
                </div>
                <div
                  className={cn(
                    "truncate",
                    step.status === "current" && "font-medium text-foreground",
                    step.status === "complete" && "text-foreground/80",
                    step.status === "pending" && "text-muted-foreground",
                    step.status === "error" && "text-destructive",
                  )}
                >
                  {step.label}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-black/8 bg-black/[0.03] text-foreground/70">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        </div>
      </div>
    </div>
  );
}

function previewCanvasReducer(state: PreviewCanvasState, action: PreviewCanvasAction): PreviewCanvasState {
  switch (action.type) {
    case "sync": {
      const nextFrame =
        action.transportKey && action.previewUrl
          ? {
              key: action.transportKey,
              src: action.previewUrl,
            }
          : null;

      if (!nextFrame) {
        if (!state.stagedFrame) {
          return state;
        }
        return {
          ...state,
          stagedFrame: null,
        };
      }
      if (!state.visibleFrame) {
        return {
          visibleFrame: nextFrame,
          stagedFrame: null,
          clearedFrameKey: null,
        };
      }
      if (state.visibleFrame.key === nextFrame.key) {
        if (state.visibleFrame.src === nextFrame.src) {
          if (!state.stagedFrame) {
            return state;
          }
          return {
            ...state,
            stagedFrame: null,
          };
        }
        if (state.stagedFrame?.key === nextFrame.key && state.stagedFrame.src === nextFrame.src) {
          return state;
        }
        return {
          ...state,
          stagedFrame: nextFrame,
        };
      }
      return {
        visibleFrame: nextFrame,
        stagedFrame: null,
        clearedFrameKey: state.visibleFrame.key,
      };
    }
    case "staged_loaded": {
      if (!state.stagedFrame) {
        return state;
      }
      return {
        visibleFrame: state.stagedFrame,
        stagedFrame: null,
        clearedFrameKey: null,
      };
    }
    case "cleared_ack": {
      if (!state.clearedFrameKey) {
        return state;
      }
      return {
        ...state,
        clearedFrameKey: null,
      };
    }
    default:
      return state;
  }
}

export const PreviewCanvas = forwardRef<HTMLIFrameElement, PreviewCanvasProps>(
  function PreviewCanvas(
    {
      previewUrl,
          transportKey,
      transportStatus = "idle",
      hasUsableFrame = false,
      loadingMessage,
      loadingState,
      errorMessage,
      canRetry = false,
      onRetry = null,
      onFrameReady = null,
      onFrameCleared = null,
    },
    ref,
  ) {
    const visibleFrameRef = useRef<HTMLIFrameElement | null>(null);
    const stagedFrameRef = useRef<HTMLIFrameElement | null>(null);
    const [frameState, dispatchFrameState] = useReducer(previewCanvasReducer, {
      visibleFrame: null,
      stagedFrame: null,
      clearedFrameKey: null,
    });

    const { visibleFrame, stagedFrame, clearedFrameKey } = frameState;

    const showFullLoading = !hasUsableFrame && (
      transportStatus === "booting"
      || transportStatus === "reconnecting"
      || Boolean(loadingState)
    );
    const showReconnectOverlay = hasUsableFrame && Boolean(visibleFrame) && Boolean(stagedFrame);
    const showInlineError = Boolean(visibleFrame) && Boolean(errorMessage) && !showFullLoading;
    const showFullError = !visibleFrame && Boolean(errorMessage) && transportStatus === "failed";
    const warmupState = loadingState || {
      title: transportStatus === "reconnecting" ? "Reconnecting live preview" : "Preparing draft preview",
      detail: String(loadingMessage || "").trim() || "Loading preview...",
      steps: [],
    };
    const warmupDetail = warmupState.detail;

    useEffect(() => {
      dispatchFrameState({
        type: "sync",
        previewUrl: previewUrl || null,
        transportKey: transportKey || null,
      });
    }, [previewUrl, transportKey]);

    useEffect(() => {
      if (!clearedFrameKey) {
        return;
      }
      onFrameCleared?.(clearedFrameKey);
      dispatchFrameState({ type: "cleared_ack" });
    }, [clearedFrameKey, onFrameCleared]);

    useEffect(() => {
      const handleMessage = (event: MessageEvent) => {
        const data = event.data;
        if (!data || typeof data !== "object" || data.type !== PREVIEW_DEBUG_BRIDGE_MESSAGE_TYPE) {
          return;
        }
        logBuilderPreviewDebug("preview", "iframe_bridge", {
          origin: event.origin,
          ...(typeof data.payload === "object" && data.payload ? data.payload : {}),
        });
      };
      window.addEventListener("message", handleMessage);
      return () => {
        window.removeEventListener("message", handleMessage);
      };
    }, []);

    const setVisibleFrameNode = useCallback(
      (node: HTMLIFrameElement | null) => {
        visibleFrameRef.current = node;
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

    const handleVisibleLoad = useCallback(() => {
      if (!visibleFrameRef.current || !visibleFrame) {
        return;
      }
      onFrameReady?.(visibleFrame.key);
      logBuilderPreviewDebug("preview", "frame_load.visible", {
        transportKey: visibleFrame.key,
        previewUrl: visibleFrame.src,
      });
    }, [onFrameReady, visibleFrame]);

    const handleStagedLoad = useCallback(() => {
      if (!stagedFrameRef.current || !stagedFrame) {
        return;
      }
      dispatchFrameState({ type: "staged_loaded" });
      onFrameReady?.(stagedFrame.key);
      logBuilderPreviewDebug("preview", "frame_load.staged_swap", {
        transportKey: stagedFrame.key,
        previewUrl: stagedFrame.src,
      });
    }, [onFrameReady, stagedFrame]);

    useEffect(() => {
      logBuilderPreviewDebug("preview", "canvas_state", {
        transportKey: transportKey || null,
        transportStatus,
        previewUrl: previewUrl || null,
        visibleFrameKey: visibleFrame?.key || null,
        visibleFrameSrc: visibleFrame?.src || null,
        stagedFrameKey: stagedFrame?.key || null,
        stagedFrameSrc: stagedFrame?.src || null,
        showFullLoading,
        showReconnectOverlay,
        showInlineError,
        showFullError,
        hasRetry: Boolean(canRetry && onRetry),
        hasUsableFrame,
      });
    }, [
      canRetry,
      hasUsableFrame,
      onRetry,
      previewUrl,
      showFullError,
      showFullLoading,
      showInlineError,
      showReconnectOverlay,
      stagedFrame,
      transportKey,
      transportStatus,
      visibleFrame,
    ]);

    return (
      <div className="relative h-full w-full overflow-hidden bg-white">
        {visibleFrame ? (
          <iframe
            ref={setVisibleFrameNode}
            title="App Preview"
            data-testid="preview-iframe"
            className="h-full w-full"
            sandbox="allow-same-origin allow-scripts allow-forms"
            src={visibleFrame.src}
            onLoad={handleVisibleLoad}
          />
        ) : null}

        {stagedFrame ? (
          <iframe
            ref={stagedFrameRef}
            title="App Preview Pending"
            className="pointer-events-none absolute inset-0 h-full w-full opacity-0"
            sandbox="allow-same-origin allow-scripts allow-forms"
            src={stagedFrame.src}
            onLoad={handleStagedLoad}
          />
        ) : null}

        {showFullLoading ? (
          <div
            data-testid="preview-warmup-overlay"
            className="absolute inset-0 flex items-center justify-center bg-background/72 px-6 text-sm text-muted-foreground backdrop-blur-sm"
          >
            <PreviewWarmupState state={warmupState} />
          </div>
        ) : null}

        {showReconnectOverlay ? (
          <div className="pointer-events-none absolute left-4 top-4 rounded-md border border-black/8 bg-white/92 px-3 py-2 text-xs text-foreground shadow-sm backdrop-blur">
            <div className="flex items-center gap-2">
              <Loader2 className="h-3 w-3 animate-spin text-foreground/70" />
              <span>{warmupDetail}</span>
            </div>
          </div>
        ) : null}

        {showInlineError ? (
          <div className="absolute left-4 right-4 top-4 rounded-md border border-destructive/25 bg-background/95 px-3 py-2 text-xs text-destructive shadow-sm">
            <div>{errorMessage || "Draft preview session failed. Retry to restart the sandbox."}</div>
            {canRetry && onRetry ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-2 h-7 px-2 text-xs"
                onClick={onRetry}
              >
                Retry sandbox
              </Button>
            ) : null}
          </div>
        ) : null}

        {showFullError ? (
          <div className="absolute inset-0 overflow-auto bg-background/95 p-4 text-sm text-destructive">
            <div>{errorMessage || "Draft preview session failed. Retry to restart the sandbox."}</div>
            {canRetry && onRetry ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className={cn("mt-3")}
                onClick={onRetry}
              >
                Retry sandbox
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  },
);
