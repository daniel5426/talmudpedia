"use client";

import { useMemo } from "react";

import { CodeEditor } from "@/components/ui/code-editor";
import { inferLanguage } from "@/features/apps-builder/editor/FileTree";

type CodeEditorPanelProps = {
  files: Record<string, string>;
  selectedFile: string | null;
  onUpdateFile: (path: string, content: string) => void;
  readOnly?: boolean;
};

export function CodeEditorPanel({ files, selectedFile, onUpdateFile, readOnly = false }: CodeEditorPanelProps) {
  const sortedPaths = useMemo(() => Object.keys(files).sort(), [files]);
  const activePath = selectedFile && files[selectedFile] !== undefined ? selectedFile : sortedPaths[0] || null;
  const activeContent = activePath ? files[activePath] : "";

  return (
    <div className="flex min-w-0 flex-1 flex-col h-full">
      <div className="flex items-center justify-between gap-2 border-b border-border/60 px-3 py-2 text-xs text-muted-foreground">
        <span>{activePath || "No file selected"}</span>
        {readOnly ? (
          <span className="rounded border border-border/70 bg-muted/40 px-2 py-0.5 text-[10px] uppercase tracking-wide">
            Locked during run
          </span>
        ) : null}
      </div>
      <div className="min-h-0 flex-1">
        {activePath ? (
          <CodeEditor
            language={inferLanguage(activePath)}
            value={activeContent}
            onChange={(value) => {
              if (readOnly) return;
              onUpdateFile(activePath, value);
            }}
            className="h-full"
            framed={false}
            readOnly={readOnly}
            suppressValidationDecorations
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Create a file to start editing.
          </div>
        )}
      </div>
    </div>
  );
}
