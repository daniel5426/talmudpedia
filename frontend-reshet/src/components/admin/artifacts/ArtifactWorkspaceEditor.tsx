"use client"

import { useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { CodeEditor } from "@/components/ui/code-editor"
import { cn } from "@/lib/utils"
import { ArtifactSourceFile } from "@/services/artifacts"
import {
  ChevronLeft,
  ChevronRight,
  FileCode2,
  FolderTree,
  Plus,
  Trash2,
} from "lucide-react"

interface ArtifactWorkspaceEditorProps {
  sourceFiles: ArtifactSourceFile[]
  activeFilePath: string
  entryModulePath?: string
  onActiveFileChange: (path: string) => void
  onSourceFilesChange: (files: ArtifactSourceFile[]) => void
}

const DEFAULT_NEW_FILE_BASENAME = "module"

function nextAvailablePath(sourceFiles: ArtifactSourceFile[]): string {
  const paths = new Set(sourceFiles.map((file) => file.path))
  let index = 1
  while (true) {
    const candidate = `helpers/${DEFAULT_NEW_FILE_BASENAME}_${index}.py`
    if (!paths.has(candidate)) return candidate
    index += 1
  }
}

export function ArtifactWorkspaceEditor({
  sourceFiles,
  activeFilePath,
  entryModulePath,
  onActiveFileChange,
  onSourceFilesChange,
}: ArtifactWorkspaceEditorProps) {
  const [isTreeOpen, setIsTreeOpen] = useState(true)
  const activeFile = useMemo(
    () => sourceFiles.find((file) => file.path === activeFilePath) ?? sourceFiles[0] ?? null,
    [activeFilePath, sourceFiles]
  )

  const updateActiveContent = (nextContent: string) => {
    onSourceFilesChange(
      sourceFiles.map((file) =>
        file.path === (activeFile?.path ?? activeFilePath) ? { ...file, content: nextContent } : file
      )
    )
  }

  const handleAddFile = () => {
    const path = nextAvailablePath(sourceFiles)
    onSourceFilesChange([
      ...sourceFiles,
      {
        path,
        content: 'def helper():\n    return "new helper"\n',
      },
    ])
    onActiveFileChange(path)
    setIsTreeOpen(true)
  }

  const handleDeleteFile = (path: string) => {
    if (path === entryModulePath || sourceFiles.length <= 1) return
    const nextFiles = sourceFiles.filter((file) => file.path !== path)
    onSourceFilesChange(nextFiles)
    if (activeFilePath === path) {
      onActiveFileChange(nextFiles[0]?.path ?? "")
    }
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 overflow-hidden">
      <div
        className={cn(
          "border-r border-border/60 bg-muted/20 transition-all duration-200",
          isTreeOpen ? "w-72" : "w-12"
        )}
      >
        <div className="flex h-full flex-col">
          <div className="flex h-11 items-center justify-between border-b border-border/50 px-2">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setIsTreeOpen((current) => !current)}
              title={isTreeOpen ? "Collapse file tree" : "Open file tree"}
            >
              {isTreeOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </Button>
            {isTreeOpen ? (
              <>
                <div className="flex min-w-0 items-center gap-2">
                  <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <FolderTree className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      Workspace
                    </p>
                  </div>
                </div>
                <Button type="button" variant="outline" size="sm" className="h-7 gap-1 px-2 text-[11px]" onClick={handleAddFile}>
                  <Plus className="h-3.5 w-3.5" />
                  File
                </Button>
              </>
            ) : null}
          </div>

          {isTreeOpen ? (
            <div className="flex-1 overflow-auto p-2">
              <div className="space-y-1">
                {sourceFiles.map((file) => {
                  const isActive = file.path === activeFile?.path
                  const isEntry = file.path === entryModulePath
                  return (
                    <div
                      key={file.path}
                      className={cn(
                        "group flex items-center gap-2 rounded-lg border px-2 py-2 transition-colors",
                        isActive
                          ? "border-primary/30 bg-primary/10"
                          : "border-transparent bg-background/70 hover:border-border/60 hover:bg-background"
                      )}
                    >
                      <button
                        type="button"
                        className="flex min-w-0 flex-1 items-center gap-2 text-left"
                        onClick={() => onActiveFileChange(file.path)}
                      >
                        <FileCode2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{file.path.split("/").pop()}</p>
                          <p className="truncate text-[11px] text-muted-foreground">{file.path}</p>
                        </div>
                      </button>
                      {isEntry ? (
                        <Badge variant="outline" className="h-5 shrink-0 text-[10px]">
                          entry
                        </Badge>
                      ) : null}
                      {!isEntry && sourceFiles.length > 1 ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                          onClick={() => handleDeleteFile(file.path)}
                          title={`Delete ${file.path}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center gap-3 py-3">
              <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={handleAddFile} title="Add file">
                <Plus className="h-4 w-4" />
              </Button>
              {sourceFiles.map((file) => (
                <button
                  key={file.path}
                  type="button"
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-lg border transition-colors",
                    file.path === activeFile?.path
                      ? "border-primary/30 bg-primary/10 text-primary"
                      : "border-transparent bg-background/70 text-muted-foreground hover:border-border/60"
                  )}
                  onClick={() => onActiveFileChange(file.path)}
                  title={file.path}
                >
                  <FileCode2 className="h-4 w-4" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex h-11 items-center justify-between border-b border-border/50 bg-background/95 px-4">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{activeFile?.path ?? "handler.py"}</p>
            <p className="truncate text-[11px] text-muted-foreground">
              {activeFile?.path === entryModulePath ? "Entry module" : "Supporting module"}
            </p>
          </div>
          <Input value={activeFile?.path ?? ""} readOnly className="hidden h-8 w-[320px] text-xs font-mono lg:block" />
        </div>
        <div className="min-h-0 flex-1">
          <CodeEditor
            value={activeFile?.content ?? ""}
            onChange={updateActiveContent}
            height="100%"
            className="h-full w-full border-0 rounded-none"
          />
        </div>
      </div>
    </div>
  )
}
