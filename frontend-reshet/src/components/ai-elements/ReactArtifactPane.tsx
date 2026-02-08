"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CodeEditor } from "@/components/ui/code-editor";
import {
  Artifact,
  ArtifactActions,
  ArtifactAction,
  ArtifactContent,
  ArtifactHeader,
  ArtifactTitle,
} from "@/components/ai-elements/artifact";
import { cn } from "@/lib/utils";
import { PlayIcon, RotateCcwIcon, XIcon } from "lucide-react";
import { compileReactArtifact } from "@/lib/react-artifacts/compiler";
import type { ReactArtifact } from "@/lib/react-artifacts/types";

const buildPreviewHtml = (bundle: string) => {
  const safeBundle = bundle.replace(/<\/(script)/gi, "<\\/$1");
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline' https://cdn.tailwindcss.com;" />
    <style>
      * { box-sizing: border-box; }
      html, body { margin: 0; padding: 0; width: 100%; height: 100%; }
      body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; background: #fff; color: #0f172a; }
      #root { width: 100%; height: 100%; }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      (function() {
        const send = (level, args) => {
          const message = args
            .map((arg) => {
              if (typeof arg === "string") return arg;
              try { return JSON.stringify(arg); } catch { return String(arg); }
            })
            .join(" ");
          parent.postMessage({ source: "react-artifact", type: "console", level, message }, "*");
        };
        ["log", "warn", "error"].forEach((level) => {
          const original = console[level];
          console[level] = (...args) => {
            send(level, args);
            original(...args);
          };
        });
        window.addEventListener("error", (event) => {
          send("error", [event.message]);
        });
        window.addEventListener("unhandledrejection", (event) => {
          const reason = event?.reason;
          send("error", [reason?.message || String(reason)]);
        });
      })();
    </script>
    <script>${safeBundle}</script>
  </body>
</html>`;
};

export type ReactArtifactPaneProps = {
  artifact: ReactArtifact;
  onCodeChange: (nextCode: string) => void;
  onClose: () => void;
  onRun?: () => void;
  onReset?: () => void;
};

type ConsoleLog = {
  level: "log" | "warn" | "error";
  message: string;
  timestamp: Date;
};

const ConsolePanel = ({ logs }: { logs: ConsoleLog[] }) => (
  <div className="rounded-md border bg-muted/30">
    <div className="flex items-center justify-between border-b px-3 py-2 text-xs font-medium text-muted-foreground">
      Console
    </div>
    <div className="max-h-40 space-y-1 overflow-y-auto px-3 py-2 font-mono text-xs">
      {logs.length === 0 ? (
        <p className="text-muted-foreground">No console output</p>
      ) : (
        logs.map((log, index) => (
          <div
            className={cn(
              log.level === "error" && "text-destructive",
              log.level === "warn" && "text-yellow-600",
              log.level === "log" && "text-foreground"
            )}
            key={`${log.timestamp.getTime()}-${index}`}
          >
            <span className="text-muted-foreground">
              {log.timestamp.toLocaleTimeString()}
            </span>{" "}
            {log.message}
          </div>
        ))
      )}
    </div>
  </div>
);

export const ReactArtifactPane = ({
  artifact,
  onCodeChange,
  onClose,
  onRun,
  onReset,
}: ReactArtifactPaneProps) => {
  const [previewSrcDoc, setPreviewSrcDoc] = useState<string>("");
  const [status, setStatus] = useState<"idle" | "compiling" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<ConsoleLog[]>([]);
  const runIdRef = useRef(0);
  const editorLanguage = artifact.language === "jsx" ? "javascript" : "typescript";

  const statusLabel = useMemo(() => {
    if (status === "compiling") return "Compiling...";
    if (status === "error") return "Build failed";
    if (status === "ready") return "Live";
    return "Idle";
  }, [status]);

  const runCompile = useCallback(async (manual = false) => {
    const runId = ++runIdRef.current;
    setStatus("compiling");
    setError(null);
    setLogs([]);

    const result = await compileReactArtifact(artifact.code);
    if (runId !== runIdRef.current) return;

    if (!result.ok) {
      setStatus("error");
      setError(result.error);
      return;
    }

    setStatus("ready");
    setPreviewSrcDoc(buildPreviewHtml(result.output));
    if (manual) {
      onRun?.();
    }
  }, [artifact.code, onRun]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      runCompile(false);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [artifact.code, artifact.id, runCompile]);

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      const data = event.data as { source?: string; type?: string; level?: ConsoleLog["level"]; message?: string };
      if (!data || data.source !== "react-artifact" || data.type !== "console") return;
      if (!data.message || !data.level) return;
      setLogs((prev) => [
        ...prev,
        {
          level: data.level,
          message: data.message,
          timestamp: new Date(),
        },
      ]);
    };

    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  return (
    <div className="h-full w-[420px] max-w-[50vw] shrink-0 border-l bg-background">
      <Artifact className="h-full rounded-none border-none shadow-none">
        <ArtifactHeader>
          <div className="min-w-0">
            <ArtifactTitle className="truncate">{artifact.title}</ArtifactTitle>
            <p className="text-xs text-muted-foreground">{statusLabel}</p>
          </div>
          <ArtifactActions>
            <ArtifactAction tooltip="Run" onClick={() => runCompile(true)}>
              <PlayIcon className="size-4" />
            </ArtifactAction>
            <ArtifactAction tooltip="Reset" onClick={onReset} disabled={!onReset}>
              <RotateCcwIcon className="size-4" />
            </ArtifactAction>
            <ArtifactAction tooltip="Close" onClick={onClose}>
              <XIcon className="size-4" />
            </ArtifactAction>
          </ArtifactActions>
        </ArtifactHeader>

        <ArtifactContent className="flex h-full flex-col gap-4 p-4">
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Editor</p>
            <CodeEditor
              className="h-[240px]"
              height={240}
              language={editorLanguage}
              onChange={onCodeChange}
              value={artifact.code}
            />
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-2">
            <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <span>Preview</span>
              {error && <span className="text-destructive">Build failed</span>}
            </div>
            <div className="relative min-h-0 flex-1 overflow-hidden rounded-md border bg-white">
              <iframe
                className="size-full"
                sandbox="allow-scripts"
                srcDoc={previewSrcDoc}
                title="React preview"
              />
              {status === "compiling" && (
                <div className="absolute inset-0 flex items-center justify-center bg-background/70 text-sm text-muted-foreground">
                  Compiling...
                </div>
              )}
              {error && (
                <div className="absolute inset-0 overflow-auto bg-background/95 p-4 text-sm text-destructive">
                  {error}
                </div>
              )}
            </div>
            <ConsolePanel logs={logs} />
          </div>
        </ArtifactContent>
      </Artifact>
    </div>
  );
};
