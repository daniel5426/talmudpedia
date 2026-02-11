"use client";

import { useMemo } from "react";
import { FileCode2, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CodeEditor } from "@/components/ui/code-editor";

type VirtualFileExplorerProps = {
  files: Record<string, string>;
  selectedFile: string | null;
  onSelectFile: (path: string) => void;
  onUpdateFile: (path: string, content: string) => void;
  onDeleteFile: (path: string) => void;
  onCreateFile: (path: string) => void;
};

const inferLanguage = (path: string): string => {
  if (path.endsWith(".tsx") || path.endsWith(".ts")) return "typescript";
  if (path.endsWith(".jsx") || path.endsWith(".js")) return "javascript";
  if (path.endsWith(".css")) return "css";
  if (path.endsWith(".json")) return "json";
  return "plaintext";
};

export function VirtualFileExplorer({
  files,
  selectedFile,
  onSelectFile,
  onUpdateFile,
  onDeleteFile,
  onCreateFile,
}: VirtualFileExplorerProps) {
  const sortedPaths = useMemo(() => Object.keys(files).sort(), [files]);
  const activePath = selectedFile && files[selectedFile] !== undefined ? selectedFile : sortedPaths[0] || null;
  const activeContent = activePath ? files[activePath] : "";

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-background">
      <aside className="flex w-72 shrink-0 flex-col border-r border-border/60 bg-muted/20">
        <div className="border-b border-border/60 p-2">
          <FileCreateInput onCreateFile={onCreateFile} />
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-2">
          <div className="space-y-1">
            {sortedPaths.map((path) => {
              const isActive = path === activePath;
              return (
                <div key={path} className="group flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => onSelectFile(path)}
                    className={`flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors ${
                      isActive ? "bg-primary/10 text-primary" : "hover:bg-muted"
                    }`}
                  >
                    <FileCode2 className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{path}</span>
                  </button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 group-hover:opacity-100"
                    onClick={() => onDeleteFile(path)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              );
            })}
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-border/60 px-3 py-2 text-xs text-muted-foreground">{activePath || "No file selected"}</div>
        <div className="min-h-0 flex-1">
          {activePath ? (
            <CodeEditor
              language={inferLanguage(activePath)}
              value={activeContent}
              onChange={(value) => onUpdateFile(activePath, value)}
              className="h-full"
              framed={false}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Create a file to start editing.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function FileCreateInput({ onCreateFile }: { onCreateFile: (path: string) => void }) {
  return (
    <form
      className="flex items-center gap-1"
      onSubmit={(event) => {
        event.preventDefault();
        const formData = new FormData(event.currentTarget);
        const rawPath = String(formData.get("path") || "").trim();
        if (!rawPath) return;
        onCreateFile(rawPath);
        event.currentTarget.reset();
      }}
    >
      <Input name="path" placeholder="src/NewFile.tsx" className="h-8 text-xs" />
      <Button type="submit" variant="outline" size="icon" className="h-8 w-8">
        <Plus className="h-3.5 w-3.5" />
      </Button>
    </form>
  );
}
