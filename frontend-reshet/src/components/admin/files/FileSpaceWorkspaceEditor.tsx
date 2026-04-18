"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ChevronDown, ChevronRight, Copy, Download, FileCode2, FileText, Folder, FolderOpen, Settings2, Trash2, X } from "lucide-react"

import { ArtifactWorkspaceSidebarHeader } from "@/components/admin/artifacts/ArtifactWorkspaceSidebarHeader"
import { ArtifactWorkspaceTabs } from "@/components/admin/artifacts/ArtifactWorkspaceTabs"
import {
  ARTIFACT_CONFIG_FILE_PATH,
  DEFAULT_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
} from "@/components/admin/artifacts/artifactWorkspaceUtils"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { FileSpaceEntry } from "@/services"

/* ------------------------------------------------------------------ */
/*  Types & Utils                                                     */
/* ------------------------------------------------------------------ */

export type FileSpaceWorkspaceNode = {
  path: string
  name: string
  kind: "file" | "directory"
  children?: FileSpaceWorkspaceNode[]
  entry?: FileSpaceEntry
}

const TREE_MENU_DOUBLE_CLICK_MS = 180

function buildSpaceTree(entries: FileSpaceEntry[]): FileSpaceWorkspaceNode[] {
  const root: FileSpaceWorkspaceNode = { path: "", name: "", kind: "directory", children: [] }
  for (const entry of entries) {
    const parts = entry.path.split("/")
    let current = root
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      const isLast = i === parts.length - 1
      const isDir = !isLast || entry.entry_type === "directory"

      let child = current.children?.find((c) => c.name === part)
      if (!child) {
        const nodePath = parts.slice(0, i + 1).join("/")
        child = {
          path: nodePath,
          name: part,
          kind: isDir ? "directory" : "file",
          children: isDir ? [] : undefined,
          entry: isLast ? entry : undefined,
        }
        current.children = current.children || []
        current.children.push(child)
      }
      if (isDir) {
        current = child
      }
    }
  }

  const sortNodes = (node: FileSpaceWorkspaceNode) => {
    if (node.children) {
      node.children.sort((a, b) => {
        if (a.kind !== b.kind) return a.kind === "directory" ? -1 : 1
        return a.name.localeCompare(b.name)
      })
      node.children.forEach(sortNodes)
    }
  }
  sortNodes(root)
  return root.children || []
}

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
  const tree = useMemo(() => buildSpaceTree(entries), [entries])
  const [expandedDirs, setExpandedDirs] = useState<string[]>(() => {
    const defaultDirs: string[] = []
    function traverse(nodes: FileSpaceWorkspaceNode[]) {
      for (const node of nodes) {
        if (node.kind === "directory") {
          defaultDirs.push(node.path)
          if (node.children) traverse(node.children)
        }
      }
    }
    traverse(tree)
    return defaultDirs
  })

  // ---- drag state for tabs ----
  const [draggingTab, setDraggingTab] = useState<string | null>(null)
  const [tabDropIndex, setTabDropIndex] = useState<number | null>(null)

  // ---- drag state for file tree ----
  const [draggingNode, setDraggingNode] = useState<string | null>(null)
  const [dropTargetDir, setDropTargetDir] = useState<string | null>(null)
  const [treeMenu, setTreeMenu] = useState<{
    path: string
    kind: "file" | "directory"
    x: number
    y: number
    expanded?: boolean
  } | null>(null)

  const [isScrolled, setIsScrolled] = useState(false)
  const treeMenuRef = useRef<HTMLDivElement | null>(null)
  const lastTreeMenuClickRef = useRef<{ path: string; timestamp: number } | null>(null)

  const activatePath = (path: string) => {
    setIsScrolled(false)
    onActiveFileChange(path)
  }

  useEffect(() => {
    if (!treeMenu) return

    const handlePointerDown = (event: MouseEvent) => {
      if (treeMenuRef.current?.contains(event.target as Node)) return
      setTreeMenu(null)
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setTreeMenu(null)
      }
    }

    window.addEventListener("mousedown", handlePointerDown)
    window.addEventListener("keydown", handleKeyDown)
    return () => {
      window.removeEventListener("mousedown", handlePointerDown)
      window.removeEventListener("keydown", handleKeyDown)
    }
  }, [treeMenu])

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

  const toggleDir = (path: string) => {
    if (loading) return
    setExpandedDirs((cur) => (cur.includes(path) ? cur.filter((v) => v !== path) : [...cur, path]))
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

  /* ---- file-tree drag-and-drop ---- */
  const handleNodeDragStart = (e: React.DragEvent, path: string) => {
    if (loading) return
    setDraggingNode(path)
    e.dataTransfer.effectAllowed = "move"
    e.dataTransfer.setData("application/x-tree-node", path)
  }

  const handleDirDragOver = (e: React.DragEvent, dirPath: string) => {
    if (loading) return
    e.preventDefault()
    e.stopPropagation()
    e.dataTransfer.dropEffect = "move"
    setDropTargetDir(dirPath)
  }

  const handleRootDragOver = (e: React.DragEvent) => {
    if (loading) return
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    setDropTargetDir("__root__")
  }

  const handleDirDrop = (e: React.DragEvent, targetDir: string) => {
    e.preventDefault()
    e.stopPropagation()
    if (loading || !draggingNode) return
    const actualTarget = targetDir === "__root__" ? "" : targetDir

    const draggedNodeData = entries.find((en) => en.path === draggingNode)
    if (draggedNodeData) {
      const fileName = draggingNode.split("/").pop()!
      const newPath = actualTarget ? `${actualTarget}/${fileName}` : fileName

      if (newPath !== draggingNode && !entries.some((f) => f.path === newPath)) {
        onMoveEntry(draggingNode, newPath)
      }
    }

    setDraggingNode(null)
    setDropTargetDir(null)
  }

  const handleNodeDragEnd = () => {
    setDraggingNode(null)
    setDropTargetDir(null)
  }

  const handleCopyPath = async (path: string) => {
    try {
      await navigator.clipboard?.writeText(path)
    } catch (err) {
      console.error(err)
    }
    setTreeMenu(null)
  }

  const openTreeMenu = (
    event: React.MouseEvent<HTMLElement>,
    node: FileSpaceWorkspaceNode,
    options?: { expanded?: boolean },
  ) => {
    event.preventDefault()
    event.stopPropagation()
    setTreeMenu({
      path: node.path,
      kind: node.kind,
      x: event.clientX,
      y: event.clientY,
      expanded: options?.expanded,
    })
  }

  const maybeOpenTreeMenuFromClick = (
    event: React.MouseEvent<HTMLElement>,
    node: FileSpaceWorkspaceNode,
    options?: { expanded?: boolean },
  ) => {
    const now = event.timeStamp
    const lastClick = lastTreeMenuClickRef.current
    if (lastClick && lastClick.path === node.path && now - lastClick.timestamp <= TREE_MENU_DOUBLE_CLICK_MS) {
      lastTreeMenuClickRef.current = null
      openTreeMenu(event, node, options)
      return
    }
    lastTreeMenuClickRef.current = { path: node.path, timestamp: now }
  }

  /* ================================================================ */
  /*  Tree rendering                                                  */
  /* ================================================================ */

  const renderNode = (node: FileSpaceWorkspaceNode, depth: number): React.ReactElement => {
    if (node.kind === "directory") {
      const isExpanded = expandedDirs.includes(node.path)
      const isDropTarget = dropTargetDir === node.path
      return (
        <div key={node.path}>
          <button
            type="button"
            draggable
            onDragStart={(e) => handleNodeDragStart(e, node.path)}
            onDragEnd={handleNodeDragEnd}
            onDragOver={(e) => handleDirDragOver(e, node.path)}
            onDrop={(e) => handleDirDrop(e, node.path)}
            className={cn(
              "flex h-[22px] w-full items-center gap-1 text-left text-[13px] transition-colors duration-75",
              palette.text,
              isDropTarget ? palette.dropTarget : palette.rowHover,
            )}
            style={{ paddingLeft: `${8 + depth * 16}px` }}
            onClick={() => toggleDir(node.path)}
            onContextMenu={(event) => openTreeMenu(event, node, { expanded: isExpanded })}
            onClickCapture={(event) => maybeOpenTreeMenuFromClick(event, node, { expanded: isExpanded })}
          >
            <span className="flex h-4 w-4 shrink-0 items-center justify-center">
              {isExpanded ? (
                <ChevronDown className="h-3 w-3 opacity-60" />
              ) : (
                <ChevronRight className="h-3 w-3 opacity-60" />
              )}
            </span>
            {isExpanded ? (
              <FolderOpen className="h-[15px] w-[15px] shrink-0 text-[#dcb67a]" />
            ) : (
              <Folder className="h-[15px] w-[15px] shrink-0 text-[#dcb67a]" />
            )}
            <span className="truncate pl-0.5">{node.name}</span>
          </button>
          {isExpanded && (
            <div>{(node.children || []).map((child) => renderNode(child, depth + 1))}</div>
          )}
        </div>
      )
    }

    const isActive = node.path === activeFilePath
    const Icon = node.entry?.is_text ? FileText : FileCode2

    return (
      <div
        key={node.path}
        draggable
        onDragStart={(e) => handleNodeDragStart(e, node.path)}
        onDragEnd={handleNodeDragEnd}
        className={cn(
          "group flex h-[22px] items-center transition-colors duration-75",
          isActive && palette.activeRow,
        )}
      >
        <button
          type="button"
          className={cn(
            "flex min-w-0 flex-1 items-center gap-1 text-left text-[13px]",
            !isActive && palette.rowHover,
            palette.text,
          )}
          style={{ paddingLeft: `${10 + depth * 16}px` }}
          onClick={() => {
            activatePath(node.path)
            setOpenTabs((prev) => (prev.includes(node.path) ? prev : [...prev, node.path]))
          }}
          onContextMenu={(event) => openTreeMenu(event, node)}
          onClickCapture={(event) => maybeOpenTreeMenuFromClick(event, node)}
        >
          <Icon className="h-[14px] w-[14px] shrink-0 text-[#519aba]" />
          <span className="truncate pl-0.5">{node.name}</span>
        </button>
        <button
          type="button"
          className={cn(
            "mr-1 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[3px] opacity-0 transition-opacity group-hover:opacity-100",
            palette.muted,
            palette.buttonHover,
          )}
          onClick={() => onDeleteEntry(node.path)}
          title={`Delete ${node.path}`}
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    )
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
          <div
            className="flex min-h-0 flex-1 flex-col overflow-hidden"
            onDragOver={handleRootDragOver}
            onDrop={(e) => handleDirDrop(e, "__root__")}
          >
            <ArtifactWorkspaceSidebarHeader
              itemCount={entries.length}
              loading={loading}
              palette={palette}
              onAddFile={onUploadFile} // Reusing AddFile button for Upload File
              onImportFiles={() => onUploadFile()}
              onAddFolder={onAddFolder}
            />

            <div className="flex-1 overflow-y-auto overflow-x-hidden py-0.5">
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
                  {tree.map((node) => renderNode(node, 0))}
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

      {treeMenu ? (
        <div
          ref={treeMenuRef}
          className="fixed z-50 min-w-52 overflow-hidden rounded-xl border border-border/60 bg-background/96 p-1.5 shadow-[0_14px_40px_rgba(15,23,42,0.14)] backdrop-blur-sm"
          style={{
            left: `${treeMenu.x}px`,
            top: `${treeMenu.y}px`,
          }}
        >
          <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
            {treeMenu.path}
          </div>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-foreground hover:bg-accent"
            onClick={() => {
              if (treeMenu.kind === "file") {
                activatePath(treeMenu.path)
                setOpenTabs((prev) => (prev.includes(treeMenu.path) ? prev : [...prev, treeMenu.path]))
              } else {
                toggleDir(treeMenu.path)
              }
              setTreeMenu(null)
            }}
          >
            {treeMenu.kind === "file" ? (
              <FileText className="h-4 w-4 text-muted-foreground" />
            ) : (
              <FolderOpen className="h-4 w-4 text-muted-foreground" />
            )}
            <span>{treeMenu.kind === "file" ? "Open file" : treeMenu.expanded ? "Collapse folder" : "Expand folder"}</span>
          </button>
          {treeMenu.kind === "file" ? (
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-foreground hover:bg-accent"
              onClick={() => {
                onDownloadEntry(treeMenu.path)
                setTreeMenu(null)
              }}
            >
              <Download className="h-4 w-4 text-muted-foreground" />
              <span>Download file</span>
            </button>
          ) : null}
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-foreground hover:bg-accent"
            onClick={() => void handleCopyPath(treeMenu.path)}
          >
            <Copy className="h-4 w-4 text-muted-foreground" />
            <span>Copy path</span>
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-destructive hover:bg-destructive/10"
            onClick={() => {
              onDeleteEntry(treeMenu.path)
              setTreeMenu(null)
            }}
          >
            <Trash2 className="h-4 w-4" />
            <span>Delete</span>
          </button>
        </div>
      ) : null}
    </div>
  )
}
