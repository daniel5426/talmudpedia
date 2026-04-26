"use client"

import type { ChangeEvent } from "react"
import { useCallback, useMemo, useRef, useState } from "react"
import { ArtifactCredentialCodeEditor } from "@/components/admin/artifacts/ArtifactCredentialCodeEditor"
import { ArtifactWorkspaceSidebarHeader } from "@/components/admin/artifacts/ArtifactWorkspaceSidebarHeader"
import { ArtifactWorkspaceTabs } from "@/components/admin/artifacts/ArtifactWorkspaceTabs"
import { PierreFileTree, type PierreFileTreeAction } from "@/components/file-tree/PierreFileTree"
import {
  ARTIFACT_CONFIG_FILE_PATH,
  DEFAULT_SIDEBAR_WIDTH,
  editorLanguageForPath,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  nextAvailableDirPath,
  nextAvailablePath,
  normalizeImportedPath,
} from "@/components/admin/artifacts/artifactWorkspaceUtils"
import { Skeleton } from "@/components/ui/skeleton"
import { normalizeCredentialMentionLabels } from "@/lib/credential-mentions"
import { cn } from "@/lib/utils"
import { IntegrationCredential } from "@/services"
import { ArtifactLanguage, ArtifactSourceFile } from "@/services/artifacts"
import { Settings2 } from "lucide-react"

/* ------------------------------------------------------------------ */
/*  Props & types                                                      */
/* ------------------------------------------------------------------ */

interface ArtifactWorkspaceEditorProps {
  sourceFiles: ArtifactSourceFile[]
  language: ArtifactLanguage
  organizationId?: string
  dependencies?: string
  loading?: boolean
  activeFilePath: string
  entryModulePath?: string
  onActiveFileChange: (path: string) => void
  onSourceFilesChange: (files: ArtifactSourceFile[]) => void
  /** Controlled sidebar open state. */
  sidebarOpen?: boolean
  /** Called when sidebar open state changes (toggle, border click, drag). */
  onSidebarOpenChange?: (open: boolean) => void
  /** Slot rendered as the content of the config file. */
  configContent?: React.ReactNode
  availableCredentials?: IntegrationCredential[]
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function ArtifactWorkspaceEditor({
  sourceFiles,
  language,
  organizationId,
  dependencies,
  loading = false,
  activeFilePath,
  entryModulePath,
  onActiveFileChange,
  onSourceFilesChange,
  sidebarOpen: controlledSidebarOpen,
  onSidebarOpenChange,
  configContent,
  availableCredentials = [],
}: ArtifactWorkspaceEditorProps) {
  const palette = {
    appBg: "bg-background",
    sidebarBg: "bg-sidebar",
    topBarBg: "bg-sidebar",
    border: "border-border",
    subtleBorder: "border-border/60",
    text: "text-foreground",
    muted: "text-muted-foreground",
    dim: "text-muted-foreground/60",
    rowHover: "hover:bg-accent",
    activeRow: "bg-accent",
    activeTab: "bg-background text-foreground",
    inactiveTab: "bg-transparent text-muted-foreground",
    tabHover: "hover:bg-accent/60",
    accent: "text-primary",
    buttonHover: "hover:bg-accent",
    dropTarget: "bg-primary/10",
  }

  // ---- sidebar state ----
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH)
  const [internalSidebarOpen, setInternalSidebarOpen] = useState(true)
  const sidebarBeforeClose = useRef(DEFAULT_SIDEBAR_WIDTH)

  // Support both controlled and uncontrolled sidebar modes
  const isTreeOpen = controlledSidebarOpen !== undefined ? controlledSidebarOpen : internalSidebarOpen
  const setIsTreeOpen = useCallback(
    (nextOrFn: boolean | ((prev: boolean) => boolean)) => {
      const next = typeof nextOrFn === "function" ? nextOrFn(isTreeOpen) : nextOrFn
      setInternalSidebarOpen(next)
      onSidebarOpenChange?.(next)
    },
    [isTreeOpen, onSidebarOpenChange]
  )
  const isResizingSidebar = useRef(false)
  const [isResizingState, setIsResizingState] = useState(false)
  const resizeSidebarStart = useRef<{ x: number; w: number } | null>(null)
  const didDragSidebar = useRef(false)

  // ---- tree state ----
  const treePaths = useMemo(
    () =>
      sourceFiles.flatMap((file) => {
        if (file.path.endsWith("/.gitkeep")) return [`${file.path.slice(0, -"/.gitkeep".length)}/`]
        return [file.path]
      }),
    [sourceFiles],
  )

  const activeFile = useMemo(
    () => {
      if (activeFilePath === ARTIFACT_CONFIG_FILE_PATH) return null
      return sourceFiles.find((f) => f.path === activeFilePath) ?? sourceFiles[0] ?? null
    },
    [activeFilePath, sourceFiles]
  )

  // ---- open tabs: ordered list of paths, independent of selection ----
  const [openTabs, setOpenTabs] = useState<string[]>(() => sourceFiles.map((f) => f.path))

  // ---- drag state for tabs ----
  const [draggingTab, setDraggingTab] = useState<string | null>(null)
  const [tabDropIndex, setTabDropIndex] = useState<number | null>(null)

  const importInputRef = useRef<HTMLInputElement | null>(null)

  // ---- scroll state for tab transition effect ----
  const [isScrolled, setIsScrolled] = useState(false)

  const activatePath = useCallback((path: string) => {
    setIsScrolled(false)
    onActiveFileChange(path)
  }, [onActiveFileChange, setIsScrolled])

  const directoryForTreeItem = useCallback((item: { kind: "directory" | "file"; path: string }) => {
    const normalizedPath = item.path.replace(/\/+$/, "")
    if (item.kind === "directory") return normalizedPath
    const parts = normalizedPath.split("/").filter(Boolean)
    parts.pop()
    return parts.join("/")
  }, [])

  /* ================================================================ */
  /*  Handlers                                                         */
  /* ================================================================ */

  const updateActiveContent = (nextContent: string) => {
    if (loading) return
    onSourceFilesChange(
      sourceFiles.map((f) =>
        f.path === (activeFile?.path ?? activeFilePath) ? { ...f, content: nextContent } : f
      )
    )
  }

  const handleAddFile = useCallback((directory: string = "") => {
    if (loading) return
    const path = nextAvailablePath(sourceFiles, directory, language)
    onSourceFilesChange([
      ...sourceFiles,
      {
        path,
        content: language === "javascript"
          ? 'export function helper() {\n  return "new helper";\n}\n'
          : 'def helper():\n    return "new helper"\n',
      },
    ])
    setOpenTabs((prev) => (prev.includes(path) ? prev : [...prev, path]))
    activatePath(path)
    if (!isTreeOpen) setIsTreeOpen(true)
  }, [activatePath, isTreeOpen, language, loading, onSourceFilesChange, setIsTreeOpen, setOpenTabs, sourceFiles])

  const handleAddRootFile = useCallback(() => {
    handleAddFile("")
  }, [handleAddFile])

  const handleAddDir = useCallback((parent: string = "") => {
    if (loading) return
    const normalizedParent = parent.replace(/\/+$/, "")
    const dirName = nextAvailableDirPath(sourceFiles, normalizedParent)
    const filePath = `${dirName}/.gitkeep`
    const nextPath = normalizedParent ? `${normalizedParent}/${filePath}` : filePath
    onSourceFilesChange([
      ...sourceFiles,
      { path: nextPath, content: "" },
    ])
    if (!isTreeOpen) setIsTreeOpen(true)
  }, [isTreeOpen, loading, onSourceFilesChange, setIsTreeOpen, sourceFiles])

  const handleAddRootDir = useCallback(() => {
    handleAddDir("")
  }, [handleAddDir])

  const handleImportFiles = useCallback(async (event: ChangeEvent<HTMLInputElement>) => {
    if (loading) return
    const selectedFiles = Array.from(event.target.files || [])
    if (selectedFiles.length === 0) return

    const importedEntries = await Promise.all(
      selectedFiles.map(async (file) => ({
        path: normalizeImportedPath(file),
        content: await file.text(),
      }))
    )
    const validEntries = importedEntries.filter((entry) => entry.path)
    if (validEntries.length === 0) {
      event.target.value = ""
      return
    }

    const nextByPath = new Map(sourceFiles.map((file) => [file.path, file] as const))
    validEntries.forEach((entry) => {
      nextByPath.set(entry.path, entry)
    })
    const nextFiles = Array.from(nextByPath.values()).sort((left, right) => left.path.localeCompare(right.path))

    onSourceFilesChange(nextFiles)
    setOpenTabs((prev) => {
      const next = [...prev]
      validEntries.forEach((entry) => {
        if (!next.includes(entry.path)) next.push(entry.path)
      })
      return next
    })
    if (!sourceFiles.some((file) => file.path === activeFilePath) && validEntries[0]?.path) {
      activatePath(validEntries[0].path)
    }
    if (!isTreeOpen) setIsTreeOpen(true)
    event.target.value = ""
  }, [activeFilePath, activatePath, isTreeOpen, loading, onSourceFilesChange, setIsTreeOpen, setOpenTabs, sourceFiles])

  const handleCloseTab = (path: string) => {
    if (loading) return
    if (path === entryModulePath) return
    const next = openTabs.filter((p) => p !== path)
    if (next.length === 0) return
    if (activeFilePath === path) {
      const closedIdx = openTabs.indexOf(path)
      const newActive = next[Math.min(closedIdx, next.length - 1)]
      activatePath(newActive)
    }
    setOpenTabs(next)
  }

  const handleMoveTreePath = useCallback((sourcePath: string, targetPath: string) => {
    if (loading || sourcePath === entryModulePath) return
    const draggedFile = sourceFiles.find((file) => file.path === sourcePath)
    if (draggedFile) {
      if (targetPath !== sourcePath && !sourceFiles.some((file) => file.path === targetPath)) {
        onSourceFilesChange(sourceFiles.map((file) => (file.path === sourcePath ? { ...file, path: targetPath } : file)))
        if (activeFilePath === sourcePath) activatePath(targetPath)
        setOpenTabs((prev) => prev.map((path) => (path === sourcePath ? targetPath : path)))
      }
      return
    }

    const prefix = `${sourcePath}/`
    if (targetPath === sourcePath || targetPath.startsWith(prefix)) return
    const updated = sourceFiles.map((file) => {
      if (!file.path.startsWith(prefix)) return file
      return { ...file, path: `${targetPath}${file.path.slice(sourcePath.length)}` }
    })
    onSourceFilesChange(updated)
    if (activeFilePath.startsWith(prefix)) {
      activatePath(`${targetPath}${activeFilePath.slice(sourcePath.length)}`)
    }
    setOpenTabs((prev) => prev.map((path) => (path.startsWith(prefix) ? `${targetPath}${path.slice(sourcePath.length)}` : path)))
  }, [activeFilePath, activatePath, entryModulePath, loading, onSourceFilesChange, setOpenTabs, sourceFiles])

  const handleDeleteTreePath = useCallback((path: string, kind: "directory" | "file") => {
    if (loading || path === entryModulePath) return
    const prefix = `${path.replace(/\/+$/, "")}/`
    const next = kind === "directory"
      ? sourceFiles.filter((file) => !file.path.startsWith(prefix))
      : sourceFiles.filter((file) => file.path !== path)
    onSourceFilesChange(next)
    setOpenTabs((prev) => prev.filter((openPath) => (kind === "directory" ? !openPath.startsWith(prefix) : openPath !== path)))
    if (activeFilePath === path || activeFilePath.startsWith(prefix)) {
      activatePath(next[0]?.path ?? ARTIFACT_CONFIG_FILE_PATH)
    }
  }, [activeFilePath, activatePath, entryModulePath, loading, onSourceFilesChange, setOpenTabs, sourceFiles])

  const handleCopyPath = useCallback(async (path: string) => {
    try {
      await navigator.clipboard?.writeText(path)
    } catch (error) {
      console.error(error)
    }
  }, [])

  const handleDownloadFile = useCallback((path: string) => {
    const file = sourceFiles.find((entry) => entry.path === path)
    if (!file) return
    const fileName = path.split("/").pop() || "artifact-file"
    const blob = new Blob([file.content], { type: "text/plain;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }, [sourceFiles])

  const fileTreeActions = useCallback((item: { kind: "directory" | "file"; path: string }): PierreFileTreeAction[] => {
    const targetDirectory = directoryForTreeItem(item)
    const itemPath = item.path.replace(/\/+$/, "")
    const isEntry = itemPath === entryModulePath
    const actions: PierreFileTreeAction[] = [
      {
        label: "New file",
        icon: "new-file",
        onSelect: () => handleAddFile(targetDirectory),
      },
      {
        label: "New folder",
        icon: "new-folder",
        onSelect: () => handleAddDir(targetDirectory),
      },
      {
        label: "Rename",
        icon: "rename",
        disabled: isEntry,
        startRenaming: true,
        onSelect: () => {},
      },
    ]
    if (item.kind === "file") {
      actions.push({
        label: "Download",
        icon: "download",
        onSelect: handleDownloadFile,
      })
    }
    actions.push(
      {
        label: "Copy path",
        icon: "copy",
        onSelect: (path) => void handleCopyPath(path),
      },
      {
        label: "Delete",
        icon: "delete",
        destructive: true,
        disabled: isEntry || (item.kind === "file" && sourceFiles.length <= 1),
        onSelect: (path, selectedItem) => handleDeleteTreePath(path, selectedItem.kind),
      },
    )
    return actions
  }, [directoryForTreeItem, entryModulePath, handleAddDir, handleAddFile, handleCopyPath, handleDeleteTreePath, handleDownloadFile, sourceFiles.length])

  /* ---- sidebar resize via border ---- */
  const handleSidebarBorderPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (loading) return
    e.preventDefault()
    e.stopPropagation()
    isResizingSidebar.current = true
    setIsResizingState(true)
    didDragSidebar.current = false
    resizeSidebarStart.current = { x: e.clientX, w: isTreeOpen ? sidebarWidth : 0 }
    e.currentTarget.setPointerCapture(e.pointerId)
    document.body.style.cursor = "col-resize"
    document.body.style.userSelect = "none"
  }

  const handleSidebarBorderPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (loading || !resizeSidebarStart.current) return
    const delta = e.clientX - resizeSidebarStart.current.x
    if (Math.abs(delta) > 3) didDragSidebar.current = true
    const raw = resizeSidebarStart.current.w + delta
    if (raw < MIN_SIDEBAR_WIDTH / 2) {
      if (isTreeOpen) {
        setIsTreeOpen(false)
      }
    } else {
      if (!isTreeOpen) setIsTreeOpen(true)
      setSidebarWidth(Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, raw)))
    }
  }

  const handleSidebarBorderPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (loading || !resizeSidebarStart.current) return
    const wasClick = !didDragSidebar.current
    resizeSidebarStart.current = null
    isResizingSidebar.current = false
    setIsResizingState(false)
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
    document.body.style.cursor = ""
    document.body.style.userSelect = ""

    if (wasClick) {
      if (isTreeOpen) {
        sidebarBeforeClose.current = sidebarWidth
        setIsTreeOpen(false)
      } else {
        setSidebarWidth(sidebarBeforeClose.current || DEFAULT_SIDEBAR_WIDTH)
        setIsTreeOpen(true)
      }
    }
  }

  /* ---- tab drag-and-drop ---- */
  const handleTabDragStart = (e: React.DragEvent, path: string) => {
    if (loading) return
    setDraggingTab(path)
    e.dataTransfer.effectAllowed = "move"
    e.dataTransfer.setData("text/plain", path)
  }

  const handleTabDragOver = (e: React.DragEvent, index: number) => {
    if (loading) return
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    setTabDropIndex(index)
  }

  const handleTabDrop = (e: React.DragEvent, dropIdx: number) => {
    if (loading) return
    e.preventDefault()
    if (draggingTab === null) return
    setOpenTabs((prev) => {
      const from = prev.indexOf(draggingTab)
      if (from === -1) return prev
      const next = [...prev]
      next.splice(from, 1)
      const adjustedIdx = dropIdx > from ? dropIdx - 1 : dropIdx
      next.splice(adjustedIdx, 0, draggingTab)
      return next
    })
    if (loading) return
    setDraggingTab(null)
    setTabDropIndex(null)
  }

  const handleTabDragEnd = () => {
    setDraggingTab(null)
    setTabDropIndex(null)
  }

  /* ================================================================ */
  /*  Render                                                           */
  /* ================================================================ */

  return (
    <div className={cn("flex h-full min-h-0 min-w-0 overflow-hidden", palette.appBg, palette.text)}>
      <input
        ref={importInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleImportFiles}
      />
      {/* -------- SIDEBAR -------- */}
      <div
        className={cn(
          "mx-1 mb-2.5 mr-2 flex flex-col overflow-hidden rounded-md shadow-sm",
          isResizingState ? "transition-none" : "transition-[width] duration-150",
          palette.sidebarBg
        )}
        style={{ width: isTreeOpen ? `${sidebarWidth}px` : "0px" }}
      >
        {isTreeOpen && (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            {/* Items count header + action buttons */}
            <ArtifactWorkspaceSidebarHeader
              itemCount={sourceFiles.filter((file) => !file.path.endsWith("/.gitkeep")).length}
              loading={loading}
              palette={palette}
              onAddFile={handleAddRootFile}
              onImportFiles={() => importInputRef.current?.click()}
              onAddFolder={handleAddRootDir}
            />

            {/* File tree */}
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              {loading ? (
                <div className="space-y-1 px-2 py-2">
                  {Array.from({ length: 4 }).map((_, index) => (
                    <div key={index} className="flex h-[22px] items-center gap-2 rounded-sm px-2">
                      <Skeleton className="h-3.5 w-3.5 rounded-sm" />
                      <Skeleton className="h-3 w-28 rounded-sm" />
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <div
                    className={cn(
                      "group flex h-[22px] items-center transition-colors duration-75",
                      activeFilePath === ARTIFACT_CONFIG_FILE_PATH && palette.activeRow
                    )}
                  >
                    <button
                      type="button"
                      className={cn(
                        "flex min-w-0 flex-1 items-center gap-1 text-left text-[13px]",
                        activeFilePath !== ARTIFACT_CONFIG_FILE_PATH && palette.rowHover,
                        palette.text
                      )}
                      style={{ paddingLeft: `10px` }}
                      onClick={() => {
                        activatePath(ARTIFACT_CONFIG_FILE_PATH)
                        setOpenTabs((prev) =>
                          prev.includes(ARTIFACT_CONFIG_FILE_PATH) ? prev : [...prev, ARTIFACT_CONFIG_FILE_PATH]
                        )
                      }}
                    >
                      <Settings2 className="h-[14px] w-[14px] shrink-0 text-muted-foreground" />
                      <span className="truncate pl-0.5">Configuration</span>
                    </button>
                  </div>
                  <PierreFileTree
                    paths={treePaths}
                    selectedPath={activeFile?.path ?? null}
                    onSelectPath={(path) => {
                      activatePath(path)
                      setOpenTabs((prev) => (prev.includes(path) ? prev : [...prev, path]))
                    }}
                    onMovePath={handleMoveTreePath}
                    onRenamePath={handleMoveTreePath}
                    canDragPath={(path) => path !== entryModulePath}
                    actions={fileTreeActions}
                  />
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* -------- SIDEBAR RESIZE HANDLE -------- */}
      <div
        className={cn(
          "relative z-10 shrink-0 cursor-col-resize select-none",
          isTreeOpen ? "w-[1px]" : "w-[1px]"
        )}
        style={{ background: "transparent" }}
        onPointerDown={handleSidebarBorderPointerDown}
        onPointerMove={handleSidebarBorderPointerMove}
        onPointerUp={handleSidebarBorderPointerUp}
        onPointerCancel={handleSidebarBorderPointerUp}
      >
        {/* Hover highlight */}
        <div className="absolute inset-y-0 -left-[2px] w-[4px] opacity-0 hover:opacity-100 transition-opacity duration-150 bg-primary/30"
        />
      </div>

      {/* -------- MAIN AREA -------- */}
      <div className="relative flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
        <ArtifactWorkspaceTabs
          activeFilePath={activeFilePath}
          sourceFiles={sourceFiles}
          openTabs={openTabs}
          entryModulePath={entryModulePath}
          loading={loading}
          draggingTab={draggingTab}
          tabDropIndex={tabDropIndex}
          palette={palette}
          onActivatePath={activatePath}
          onCloseTab={handleCloseTab}
          onTabDragStart={handleTabDragStart}
          onTabDragOver={handleTabDragOver}
          onTabDrop={handleTabDrop}
          onTabDragEnd={handleTabDragEnd}
          onTabDropIndexChange={setTabDropIndex}
        />

        {/* Scroll shadow effect */}
        <div
          className={cn(
            "pointer-events-none absolute left-0 right-3 top-[35px] z-10 h-6 bg-gradient-to-b from-border/20 via-border/5 to-transparent transition-opacity duration-300",
            isScrolled ? "opacity-100" : "opacity-0"
          )}
          aria-hidden="true"
        />

        {/* Editor */}
        <div className="min-h-0 flex-1 flex flex-col pt-1">
          {loading ? (
            <div className="flex-1 bg-background" />
          ) : activeFilePath === ARTIFACT_CONFIG_FILE_PATH ? (
            <div 
               className="flex-1 overflow-auto bg-background"
               onScroll={(e) => setIsScrolled(e.currentTarget.scrollTop > 0)}
            >
              {configContent}
            </div>
          ) : (
            <ArtifactCredentialCodeEditor
              editorLanguage={editorLanguageForPath(activeFile?.path ?? activeFilePath)}
              sourceFiles={sourceFiles}
              activeFilePath={activeFile?.path ?? activeFilePath}
              organizationId={organizationId}
              dependencies={dependencies}
              value={normalizeCredentialMentionLabels(activeFile?.content ?? "", availableCredentials)}
              onChange={updateActiveContent}
              credentials={availableCredentials}
              height="100%"
              className="h-full w-full border-0 rounded-md"
              onScroll={setIsScrolled}
            />
          )}
        </div>
      </div>
    </div>
  )
}
