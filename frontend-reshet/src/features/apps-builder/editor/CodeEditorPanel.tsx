"use client";

import { useMemo } from "react";

import { CodeEditor } from "@/components/ui/code-editor";
import { inferLanguage } from "@/features/apps-builder/editor/FileTree";

type CodeEditorPanelProps = {
  files: Record<string, string>;
  selectedFile: string | null;
  onUpdateFile: (path: string, content: string) => void;
};

export function CodeEditorPanel({ files, selectedFile, onUpdateFile }: CodeEditorPanelProps) {
  const sortedPaths = useMemo(() => Object.keys(files).sort(), [files]);
  const activePath = selectedFile && files[selectedFile] !== undefined ? selectedFile : sortedPaths[0] || null;
  const activeContent = activePath ? files[activePath] : "";

  return (
    <div className="flex min-w-0 flex-1 flex-col h-full">
      <div className="border-b border-border/60 px-3 py-2 text-xs text-muted-foreground">
        {activePath || "No file selected"}
      </div>
      <div className="min-h-0 flex-1">
        {activePath ? (
          <CodeEditor
            language={inferLanguage(activePath)}
            value={activeContent}
            onChange={(value) => onUpdateFile(activePath, value)}
            className="h-full"
            framed={false}
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
