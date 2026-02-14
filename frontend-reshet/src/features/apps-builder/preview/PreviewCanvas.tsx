"use client";

import { Loader2 } from "lucide-react";

type DraftDevStatus = "starting" | "running" | "stopped" | "expired" | "error";

type PreviewCanvasProps = {
  previewUrl?: string | null;
  devStatus?: DraftDevStatus | null;
  devError?: string | null;
};

export function PreviewCanvas({ previewUrl, devStatus, devError }: PreviewCanvasProps) {
  const isPending = devStatus === "starting";
  const hasFailed = devStatus === "error" || devStatus === "expired";
  const hasSessionError = Boolean(devError);

  return (
    <div className="relative h-full w-full overflow-hidden bg-white">
      <iframe
        title="App Preview"
        className="h-full w-full"
        sandbox="allow-same-origin allow-scripts"
        src={previewUrl || "about:blank"}
      />

      {isPending && !hasSessionError && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 bg-background/70 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Starting draft preview...
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
}
