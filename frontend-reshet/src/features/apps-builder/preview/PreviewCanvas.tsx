"use client";

import { forwardRef, useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { SandboxLifecyclePhase } from "@/features/apps-builder/workspace/useAppsBuilderSandboxLifecycle";

type DraftDevStatus = "starting" | "running" | "stopped" | "expired" | "error";

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
const PREVIEW_AUTH_MESSAGE_TYPE = "talmudpedia.preview-auth.v1";

export const PreviewCanvas = forwardRef<HTMLIFrameElement, PreviewCanvasProps>(
  function PreviewCanvas(
    { previewUrl, previewAuthToken, forceReady = false, devStatus, devError, lifecyclePhase, loadingMessage, canRetry = false, onRetry = null },
    ref,
  ) {
    const revealTimerRef = useRef<number | null>(null);
    const failSafeTimerRef = useRef<number | null>(null);
    const frameRef = useRef<HTMLIFrameElement | null>(null);
    const [isFrameVisible, setIsFrameVisible] = useState(false);

    const clearTimers = useCallback(() => {
      if (revealTimerRef.current !== null) {
        window.clearTimeout(revealTimerRef.current);
        revealTimerRef.current = null;
      }
      if (failSafeTimerRef.current !== null) {
        window.clearTimeout(failSafeTimerRef.current);
        failSafeTimerRef.current = null;
      }
    }, []);

    useEffect(() => clearTimers, [clearTimers]);

    const isPending = devStatus === "starting" || lifecyclePhase === "ensuring" || lifecyclePhase === "recovering" || lifecyclePhase === "syncing";
    const hasFailed = devStatus === "error" || devStatus === "expired" || lifecyclePhase === "error";
    const hasSessionError = Boolean(devError);
    const canLoadFrame = (forceReady || devStatus === "running") && Boolean(previewUrl) && !hasFailed && !hasSessionError;
    const warmupMessage = String(loadingMessage || "").trim() || (isPending ? "Starting draft preview..." : "Warming preview sandbox...");

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
      if (!frame?.contentWindow || !canLoadFrame) return;
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
    }, [canLoadFrame, previewAuthToken, previewUrl]);

    useEffect(() => {
      clearTimers();
      setIsFrameVisible(false);

      if (!canLoadFrame) {
        return;
      }

      failSafeTimerRef.current = window.setTimeout(() => {
        setIsFrameVisible(true);
      }, PREVIEW_MAX_HIDDEN_MS);
    }, [canLoadFrame, clearTimers, previewUrl]);

    useEffect(() => {
      if (!canLoadFrame) return;
      postPreviewAuthToken();
      const timer = window.setTimeout(() => {
        postPreviewAuthToken();
      }, 180);
      return () => {
        window.clearTimeout(timer);
      };
    }, [canLoadFrame, postPreviewAuthToken]);

    const handleFrameLoad = useCallback(() => {
      clearTimers();
      postPreviewAuthToken();
      revealTimerRef.current = window.setTimeout(() => {
        setIsFrameVisible(true);
      }, PREVIEW_REVEAL_DELAY_MS);
    }, [clearTimers, postPreviewAuthToken]);

    return (
      <div className="relative h-full w-full overflow-hidden bg-white">
        {canLoadFrame ? (
          <iframe
            ref={setFrameRef}
            title="App Preview"
            data-testid="preview-iframe"
            className={cn(
              "h-full w-full transition-opacity duration-300 ease-out",
              isFrameVisible ? "opacity-100" : "pointer-events-none opacity-0",
            )}
            sandbox="allow-same-origin allow-scripts allow-forms"
            src={previewUrl || "about:blank"}
            onLoad={handleFrameLoad}
          />
        ) : null}

        {(isPending || (canLoadFrame && !isFrameVisible)) && !hasSessionError && !hasFailed && (
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
