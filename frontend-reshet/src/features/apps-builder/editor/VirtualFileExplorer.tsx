"use client";

import { FileTree } from "@/features/apps-builder/editor/FileTree";
import { CodeEditorPanel } from "@/features/apps-builder/editor/CodeEditorPanel";

type VirtualFileExplorerProps = {
  files: Record<string, string>;
  selectedFile: string | null;
  onSelectFile: (path: string) => void;
  onUpdateFile: (path: string, content: string) => void;
  onDeleteFile: (path: string) => void;
  onCreateFile: (path: string) => void;
};

export function VirtualFileExplorer({
  files,
  selectedFile,
  onSelectFile,
  onUpdateFile,
  onDeleteFile,
  onCreateFile,
}: VirtualFileExplorerProps) {
  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-background">
      <aside className="flex w-72 shrink-0 flex-col border-r border-border/60 bg-muted/20">
        <FileTree
          files={files}
          selectedFile={selectedFile}
          onSelectFile={onSelectFile}
          onDeleteFile={onDeleteFile}
          onCreateFile={onCreateFile}
        />
      </aside>
      <CodeEditorPanel
        files={files}
        selectedFile={selectedFile}
        onUpdateFile={onUpdateFile}
      />
    </div>
  );
}
