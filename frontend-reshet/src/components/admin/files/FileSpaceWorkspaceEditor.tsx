"use client"

import { useCallback, useMemo, useRef, useState } from "react"
import { Settings2 } from "lucide-react"

import { ArtifactWorkspaceSidebarHeader } from "@/components/admin/artifacts/ArtifactWorkspaceSidebarHeader"
import { ArtifactWorkspaceTabs } from "@/components/admin/artifacts/ArtifactWorkspaceTabs"
import {
  ARTIFACT_CONFIG_FILE_PATH,
  DEFAULT_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
} from "@/components/admin/artifacts/artifactWorkspaceUtils"
import { PierreFileTree, type PierreFileTreeAction } from "@/components/file-tree/PierreFileTree"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { FileSpaceEntry } from "@/services"

/* ------------------------------------------------------------------ */
/*  Props                                                             */
/* ------------------------------------------------------------------ */

interface FileSpaceWorkspaceEditorProps {
  entries: FileSpaceEntry[]
  loading?: boolean
  activeFilePath: string
  unsavedPaths?: string[]
  onActiveFileChange: (path: string) => void
  onAddFolder: () => void
  onUploadFile: () => void
  onDeleteEntry: (path: string) => void
  onDownloadEntry: (path: string) => void
  onMoveEntry: (sourcePath: string, targetPath: string) => void
  sidebarOpen?: boolean
  onSidebarOpenChange?: (open: boolean) => void
  editorContent?: React.ReactNode
  configContent?: React.ReactNode
  openTabs: string[]
  setOpenTabs: React.Dispatch<React.SetStateAction<string[]>>
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function FileSpaceWorkspaceEditor({
  entries,
  loading = false,
  activeFilePath,
  unsavedPaths = [],
  onActiveFileChange,
  onAddFolder,
  onUploadFile,
  onDeleteEntry,
  onDownloadEntry,
  onMoveEntry,
  sidebarOpen: controlledSidebarOpen,
  onSidebarOpenChange,
  editorContent,
  configContent,
  openTabs,
  setOpenTabs,
}: FileSpaceWorkspaceEditorProps) {
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

  const isTreeOpen = controlledSidebarOpen !== undefined ? controlledSidebarOpen : internalSidebarOpen
  const setIsTreeOpen = useCallback(
    (nextOrFn: boolean | ((prev: boolean) => boolean)) => {
      const next = typeof nextOrFn === "function" ? nextOrFn(isTreeOpen) : nextOrFn
      setInternalSidebarOpen(next)
      onSidebarOpenChange?.(next)
    },
    [isTreeOpen, onSidebarOpenChange],
  )
  const isResizingSidebar = useRef(false)
  const [isResizingState, setIsResizingState] = useState(false)
  const resizeSidebarStart = useRef<{ x: number; w: number } | null>(null)
  const didDragSidebar = useRef(false)

  // ---- tree state ----
  const treePaths = useMemo(
    () => entries.map((entry) => (entry.entry_type === "directory" ? `${entry.path.replace(/\/+$/, "")}/` : entry.path)),
    [entries],
  )

  // ---- drag state for tabs ----
  const [draggingTab, setDraggingTab] = useState<string | null>(null)
  const [tabDropIndex, setTabDropIndex] = useState<number | null>(null)

  const [isScrolled, setIsScrolled] = useState(false)

  const activatePath = (path: string) => {
    setIsScrolled(false)
    onActiveFileChange(path)
  }

  const handleCopyPath = useCallback(async (path: string) => {
    try {
      await navigator.clipboard?.writeText(path)
    } catch (error) {
      console.error(error)
    }
  }, [])

  const fileTreeActions = useCallback((item: { kind: "directory" | "file"; path: string }): PierreFileTreeAction[] => {
    const actions: PierreFileTreeAction[] = [
      {
        label: "Upload file",
        icon: "new-file",
        onSelect: onUploadFile,
      },
      {
        label: "New folder",
        icon: "new-folder",
        onSelect: onAddFolder,
      },
      {
        label: "Rename",
        icon: "rename",
        startRenaming: true,
        onSelect: () => {},
      },
    ]
    if (item.kind === "file") {
      actions.push({
        label: "Download",
        icon: "download",
        onSelect: onDownloadEntry,
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
        onSelect: onDeleteEntry,
      },
    )
    return actions
  }, [handleCopyPath, onAddFolder, onDeleteEntry, onDownloadEntry, onUploadFile])

  /* ================================================================ */
  /*  Handlers                                                        */
  /* ================================================================ */

  const handleCloseTab = (path: string) => {
    if (loading) return
    const next = openTabs.filter((p) => p !== path)
    if (next.length === 0) return
    if (activeFilePath === path) {
      const closedIdx = openTabs.indexOf(path)
      const newActive = next[Math.min(closedIdx, next.length - 1)]
      activatePath(newActive)
    }
    setOpenTabs(next)
  }

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
      if (isTreeOpen) setIsTreeOpen(false)
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
    setDraggingTab(null)
    setTabDropIndex(null)
  }

  const handleTabDragEnd = () => {
    setDraggingTab(null)
    setTabDropIndex(null)
  }

  // Convert FileSpaceEntry[] to mock ArtifactSourceFile for ArtifactWorkspaceTabs compat:
  const sourceFilesLike = entries.map((e) => ({ path: e.path, content: "" }))

  return (
    <div className={cn("flex h-full min-h-0 min-w-0 overflow-hidden", palette.appBg, palette.text)}>
      {/* -------- SIDEBAR -------- */}
      <div
        className={cn(
          "mb-2.5 mx-1 mr-2 flex flex-col overflow-hidden rounded-md shadow-sm",
          isResizingState ? "transition-none" : "transition-[width] duration-150",
          palette.sidebarBg,
        )}
        style={{ width: isTreeOpen ? `${sidebarWidth}px` : "0px" }}
      >
        {isTreeOpen && (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <ArtifactWorkspaceSidebarHeader
              itemCount={entries.length}
              loading={loading}
              palette={palette}
              onAddFile={onUploadFile} // Reusing AddFile button for Upload File
              onImportFiles={() => onUploadFile()}
              onAddFolder={onAddFolder}
            />

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
                      activeFilePath === ARTIFACT_CONFIG_FILE_PATH && palette.activeRow,
                    )}
                  >
                    <button
                      type="button"
                      className={cn(
                        "flex min-w-0 flex-1 items-center gap-1 text-left text-[13px]",
                        activeFilePath !== ARTIFACT_CONFIG_FILE_PATH && palette.rowHover,
                        palette.text,
                      )}
                      style={{ paddingLeft: `10px` }}
                      onClick={() => {
                        activatePath(ARTIFACT_CONFIG_FILE_PATH)
                        setOpenTabs((prev) =>
                          prev.includes(ARTIFACT_CONFIG_FILE_PATH)
                            ? prev
                            : [...prev, ARTIFACT_CONFIG_FILE_PATH],
                        )
                      }}
                    >
                      <Settings2 className="h-[14px] w-[14px] shrink-0 text-muted-foreground" />
                      <span className="truncate pl-0.5">Configuration</span>
                    </button>
                  </div>
                  <PierreFileTree
                    paths={treePaths}
                    selectedPath={activeFilePath}
                    onSelectPath={(path) => {
                      activatePath(path)
                      setOpenTabs((prev) => (prev.includes(path) ? prev : [...prev, path]))
                    }}
                    onMovePath={onMoveEntry}
                    onRenamePath={onMoveEntry}
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
          isTreeOpen ? "w-[1px]" : "w-[1px]",
        )}
        style={{ background: "transparent" }}
        onPointerDown={handleSidebarBorderPointerDown}
        onPointerMove={handleSidebarBorderPointerMove}
        onPointerUp={handleSidebarBorderPointerUp}
        onPointerCancel={handleSidebarBorderPointerUp}
      >
        <div className="absolute inset-y-0 -left-[2px] w-[4px] bg-primary/30 opacity-0 transition-opacity duration-150 hover:opacity-100" />
      </div>

      {/* -------- MAIN AREA -------- */}
      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <ArtifactWorkspaceTabs
          activeFilePath={activeFilePath}
          sourceFiles={sourceFilesLike}
          openTabs={openTabs}
          unsavedPaths={unsavedPaths}
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

        <div
          className={cn(
            "pointer-events-none absolute left-0 right-3 top-[35px] z-10 h-6 bg-gradient-to-b from-border/20 via-border/5 to-transparent transition-opacity duration-300",
            isScrolled ? "opacity-100" : "opacity-0",
          )}
          aria-hidden="true"
        />

        <div className="flex min-h-0 flex-1 flex-col pt-1">
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
            <div
              className="flex-1 overflow-hidden rounded-md border-0 bg-background flex flex-col"
              onScroll={(e) => setIsScrolled(e.currentTarget.scrollTop > 0)}
            >
              {editorContent}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
