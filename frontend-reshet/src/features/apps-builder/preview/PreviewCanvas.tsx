"use client";

import { forwardRef, useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type DraftDevStatus = "starting" | "running" | "stopped" | "expired" | "error";

type PreviewCanvasProps = {
  previewUrl?: string | null;
  devStatus?: DraftDevStatus | null;
  devError?: string | null;
};

const PREVIEW_REVEAL_DELAY_MS = 350;
const PREVIEW_MAX_HIDDEN_MS = 8_000;

export const PreviewCanvas = forwardRef<HTMLIFrameElement, PreviewCanvasProps>(
  function PreviewCanvas({ previewUrl, devStatus, devError }, ref) {
    const revealTimerRef = useRef<number | null>(null);
    const failSafeTimerRef = useRef<number | null>(null);
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

    const isPending = devStatus === "starting";
    const hasFailed = devStatus === "error" || devStatus === "expired";
    const hasSessionError = Boolean(devError);
    const canLoadFrame = devStatus === "running" && Boolean(previewUrl) && !hasFailed && !hasSessionError;

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

    const handleFrameLoad = useCallback(() => {
      clearTimers();
      revealTimerRef.current = window.setTimeout(() => {
        setIsFrameVisible(true);
      }, PREVIEW_REVEAL_DELAY_MS);
    }, [clearTimers]);

    return (
      <div className="relative h-full w-full overflow-hidden bg-white">
        {canLoadFrame ? (
          <iframe
            ref={ref}
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
                <span>{isPending ? "Starting draft preview..." : "Warming preview sandbox..."}</span>
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
            {devError || "Draft preview session failed. Re-open Preview to restart the sandbox."}
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
