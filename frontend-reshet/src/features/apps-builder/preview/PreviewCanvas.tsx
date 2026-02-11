"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { compileReactArtifactProject } from "@/lib/react-artifacts/compiler";

type RuntimeContext = {
  mode: "builder-preview" | "published-runtime";
  appSlug?: string;
  token?: string | null;
  basePath?: string;
};

const buildPreviewHtml = (bundle: string, css?: string, runtimeContextJson?: string) => {
  const safeBundle = bundle.replace(/<\/(script)/gi, "<\\/$1");
  const safeCss = (css || "").replace(/<\/(style)/gi, "<\\/$1");
  const contextJson = runtimeContextJson || "";
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline' https://cdn.tailwindcss.com;" />
    <style>
      * { box-sizing: border-box; }
      html, body { margin: 0; padding: 0; width: 100%; height: 100%; }
      body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; background: #fff; color: #111827; }
      #root { width: 100%; height: 100%; }
    </style>
    ${safeCss ? `<style>${safeCss}</style>` : ""}
  </head>
  <body>
    <div id="root"></div>
    <script src="https://cdn.tailwindcss.com"></script>
    ${contextJson ? `<script>window.__APP_RUNTIME_CONTEXT = ${contextJson};</script>` : ""}
    <script>${safeBundle}</script>
  </body>
</html>`;
};

type PreviewCanvasProps = {
  files: Record<string, string>;
  entryFile: string;
  runtimeContext?: RuntimeContext;
};

export function PreviewCanvas({ files, entryFile, runtimeContext }: PreviewCanvasProps) {
  const [status, setStatus] = useState<"idle" | "compiling" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [srcDoc, setSrcDoc] = useState<string>("");
  const runIdRef = useRef(0);

  const cacheKey = useMemo(() => JSON.stringify({ files, entryFile }), [files, entryFile]);
  const runtimeContextJson = useMemo(() => {
    if (!runtimeContext) return "";
    return JSON.stringify(runtimeContext).replace(/<\/(script)/gi, "<\\/$1");
  }, [runtimeContext?.mode, runtimeContext?.appSlug, runtimeContext?.token, runtimeContext?.basePath]);

  useEffect(() => {
    const runId = ++runIdRef.current;
    setStatus("compiling");
    setError(null);

    const timer = window.setTimeout(async () => {
      const result = await compileReactArtifactProject(files, entryFile);
      if (runId !== runIdRef.current) return;
      if (!result.ok) {
        setStatus("error");
        setError(result.error);
        return;
      }
      setStatus("ready");
      setSrcDoc(buildPreviewHtml(result.output, result.css, runtimeContextJson));
    }, 200);

    return () => {
      window.clearTimeout(timer);
    };
  }, [cacheKey, files, entryFile, runtimeContextJson]);

  return (
    <div className="relative h-full w-full overflow-hidden bg-white">
      <iframe title="App Preview" className="h-full w-full" sandbox="allow-scripts" srcDoc={srcDoc} />

      {status === "compiling" && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 bg-background/60 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Compiling preview...
        </div>
      )}

      {status === "error" && (
        <div className="absolute inset-0 overflow-auto bg-background/95 p-4 text-sm text-destructive">
          {error}
        </div>
      )}
    </div>
  );
}
