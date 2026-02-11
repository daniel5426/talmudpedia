"use client";

import { Loader2 } from "lucide-react";

type PreviewBuildStatus = "queued" | "running" | "succeeded" | "failed";

type PreviewCanvasProps = {
  previewUrl?: string | null;
  buildStatus?: PreviewBuildStatus | null;
  buildError?: string | null;
};

export function PreviewCanvas({ previewUrl, buildStatus, buildError }: PreviewCanvasProps) {
  const isPending = buildStatus === "queued" || buildStatus === "running";
  const hasFailed = buildStatus === "failed";

  return (
    <div className="relative h-full w-full overflow-hidden bg-white">
      <iframe
        title="App Preview"
        className="h-full w-full"
        sandbox="allow-same-origin allow-scripts"
        src={previewUrl || "about:blank"}
      />

      {isPending && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 bg-background/70 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Build in progress...
        </div>
      )}

      {hasFailed && (
        <div className="absolute inset-0 overflow-auto bg-background/95 p-4 text-sm text-destructive">
          {buildError || "Build failed. Retry from the builder controls."}
        </div>
      )}

      {!isPending && !hasFailed && !previewUrl && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/70 px-6 text-center text-sm text-muted-foreground">
          Preview is unavailable until this revision has a successful static build.
        </div>
      )}
    </div>
  );
}
