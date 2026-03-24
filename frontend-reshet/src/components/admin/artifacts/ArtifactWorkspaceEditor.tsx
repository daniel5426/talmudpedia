"use client"

import type { PointerEvent as ReactPointerEvent } from "react"
import { useCallback, useMemo, useRef, useState } from "react"
import { ArtifactCredentialCodeEditor } from "@/components/admin/artifacts/ArtifactCredentialCodeEditor"
import { normalizeCredentialMentionLabels } from "@/lib/credential-mentions"
import { cn } from "@/lib/utils"
import { IntegrationCredential } from "@/services"
import { ArtifactSourceFile } from "@/services/artifacts"
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FilePlus2,
  Folder,
  FolderOpen,
  FolderPlus,
  Settings2,
  X,
} from "lucide-react"

/* ------------------------------------------------------------------ */
/*  Props & types                                                      */
/* ------------------------------------------------------------------ */

interface ArtifactWorkspaceEditorProps {
  sourceFiles: ArtifactSourceFile[]
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

type TreeNode = {
  name: string
  path: string
  kind: "directory" | "file"
  children?: TreeNode[]
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const DEFAULT_NEW_FILE_BASENAME = "module"
const MIN_SIDEBAR_WIDTH = 160
const MAX_SIDEBAR_WIDTH = 480
const DEFAULT_SIDEBAR_WIDTH = 240

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function nextAvailablePath(sourceFiles: ArtifactSourceFile[], directory: string): string {
  const paths = new Set(sourceFiles.map((f) => f.path))
  let idx = 1
  while (true) {
    const candidate = directory
      ? `${directory}/${DEFAULT_NEW_FILE_BASENAME}_${idx}.py`
      : `${DEFAULT_NEW_FILE_BASENAME}_${idx}.py`
    if (!paths.has(candidate)) return candidate
    idx += 1
  }
}

function nextAvailableDirPath(sourceFiles: ArtifactSourceFile[], parent: string): string {
  const dirNames = new Set<string>()
  const prefix = parent ? `${parent}/` : ""
  sourceFiles.forEach((f) => {
    if (f.path.startsWith(prefix)) {
      const rest = f.path.slice(prefix.length)
      const firstSeg = rest.split("/")[0]
      if (rest.includes("/")) dirNames.add(firstSeg)
    }
  })
  let idx = 1
  while (true) {
    const candidate = `folder_${idx}`
    if (!dirNames.has(candidate)) return candidate
    idx += 1
  }
}

function buildTree(sourceFiles: ArtifactSourceFile[]): TreeNode[] {
  const root: TreeNode = { name: "__root__", path: "", kind: "directory", children: [] }

  const ensureDir = (parent: TreeNode, name: string, path: string): TreeNode => {
    const existing = parent.children!.find((c) => c.name === name && c.kind === "directory")
    if (existing) return existing
    const node: TreeNode = { name, path, kind: "directory", children: [] }
    parent.children!.push(node)
    return node
  }

  sourceFiles.forEach((file) => {
    const parts = file.path.split("/").filter(Boolean)
    let current = root
    parts.forEach((part, idx) => {
      const isLeaf = idx === parts.length - 1
      const fullPath = parts.slice(0, idx + 1).join("/")
      if (isLeaf) {
        current.children!.push({ name: part, path: fullPath, kind: "file" })
      } else {
        current = ensureDir(current, part, fullPath)
      }
    })
  })

  const sort = (nodes: TreeNode[]): TreeNode[] =>
    nodes
      .map((n) =>
        n.kind === "directory" ? { ...n, children: sort(n.children || []) } : n
      )
      .sort((a, b) => {
        if (a.kind !== b.kind) return a.kind === "directory" ? -1 : 1
        return a.name.localeCompare(b.name)
      })

  return sort(root.children || [])
}

function collectDirectoryPaths(nodes: TreeNode[]): string[] {
  return nodes.flatMap((n) =>
    n.kind === "directory" ? [n.path, ...collectDirectoryPaths(n.children || [])] : []
  )
}

/** Move a source file from one path to another (handles directory moves). */
function moveFilePath(oldPath: string, newParent: string, fileName: string): string {
  return newParent ? `${newParent}/${fileName}` : fileName
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function ArtifactWorkspaceEditor({
  sourceFiles,
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
  const tree = useMemo(() => buildTree(sourceFiles), [sourceFiles])
  const [expandedDirs, setExpandedDirs] = useState<string[]>(() => collectDirectoryPaths(tree))

  const activeFile = useMemo(
    () => {
      if (activeFilePath === "__CONFIG__") return null
      return sourceFiles.find((f) => f.path === activeFilePath) ?? sourceFiles[0] ?? null
    },
    [activeFilePath, sourceFiles]
  )

  // ---- open tabs: ordered list of paths, independent of selection ----
  const [openTabs, setOpenTabs] = useState<string[]>(() => sourceFiles.map((f) => f.path))

  // ---- drag state for tabs ----
  const [draggingTab, setDraggingTab] = useState<string | null>(null)
  const [tabDropIndex, setTabDropIndex] = useState<number | null>(null)

  // ---- drag state for file tree ----
  const [draggingNode, setDraggingNode] = useState<string | null>(null)
  const [dropTargetDir, setDropTargetDir] = useState<string | null>(null)

  // ---- scroll state for tab transition effect ----
  const [isScrolled, setIsScrolled] = useState(false)

  const activatePath = (path: string) => {
    setIsScrolled(false)
    onActiveFileChange(path)
  }

  /* ================================================================ */
  /*  Handlers                                                         */
  /* ================================================================ */

  const updateActiveContent = (nextContent: string) => {
    onSourceFilesChange(
      sourceFiles.map((f) =>
        f.path === (activeFile?.path ?? activeFilePath) ? { ...f, content: nextContent } : f
      )
    )
  }

  const handleAddFile = () => {
    const path = nextAvailablePath(sourceFiles, "")
    onSourceFilesChange([
      ...sourceFiles,
      { path, content: 'def helper():\n    return "new helper"\n' },
    ])
    setOpenTabs((prev) => (prev.includes(path) ? prev : [...prev, path]))
    activatePath(path)
    if (!isTreeOpen) setIsTreeOpen(true)
  }

  const handleAddDir = useCallback(() => {
    const dirName = nextAvailableDirPath(sourceFiles, "")
    const filePath = `${dirName}/.gitkeep`
    onSourceFilesChange([
      ...sourceFiles,
      { path: filePath, content: "" },
    ])
    setExpandedDirs((prev) => (prev.includes(dirName) ? prev : [...prev, dirName]))
    if (!isTreeOpen) setIsTreeOpen(true)
  }, [sourceFiles, onSourceFilesChange, isTreeOpen, setIsTreeOpen])

  const handleDeleteFile = (path: string) => {
    if (path === entryModulePath || sourceFiles.length <= 1) return
    const next = sourceFiles.filter((f) => f.path !== path)
    onSourceFilesChange(next)
    if (activeFilePath === path) {
      activatePath(next[0]?.path ?? "")
    }
  }

  const handleCloseTab = (path: string) => {
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

  const toggleDir = (path: string) => {
    setExpandedDirs((cur) =>
      cur.includes(path) ? cur.filter((v) => v !== path) : [...cur, path]
    )
  }

  /* ---- sidebar resize via border ---- */
  const handleSidebarBorderPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
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

  const handleSidebarBorderPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!resizeSidebarStart.current) return
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

  const handleSidebarBorderPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!resizeSidebarStart.current) return
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
    setDraggingTab(path)
    e.dataTransfer.effectAllowed = "move"
    e.dataTransfer.setData("text/plain", path)
  }

  const handleTabDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    setTabDropIndex(index)
  }

  const handleTabDrop = (e: React.DragEvent, dropIdx: number) => {
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
    if (path === entryModulePath) {
      e.preventDefault()
      return
    }
    setDraggingNode(path)
    e.dataTransfer.effectAllowed = "move"
    e.dataTransfer.setData("application/x-tree-node", path)
  }

  const handleDirDragOver = (e: React.DragEvent, dirPath: string) => {
    e.preventDefault()
    e.stopPropagation()
    e.dataTransfer.dropEffect = "move"
    setDropTargetDir(dirPath)
  }

  const handleRootDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    setDropTargetDir("__root__")
  }

  const handleDirDrop = (e: React.DragEvent, targetDir: string) => {
    e.preventDefault()
    e.stopPropagation()
    if (!draggingNode) return
    const actualTarget = targetDir === "__root__" ? "" : targetDir

    // Determine if we're dragging a file or directory
    const draggedFile = sourceFiles.find((f) => f.path === draggingNode)
    if (draggedFile) {
      // Moving a single file
      const fileName = draggingNode.split("/").pop()!
      const newPath = moveFilePath(draggingNode, actualTarget, fileName)
      if (newPath !== draggingNode && !sourceFiles.some((f) => f.path === newPath)) {
        onSourceFilesChange(
          sourceFiles.map((f) => (f.path === draggingNode ? { ...f, path: newPath } : f))
        )
        if (activeFilePath === draggingNode) activatePath(newPath)
      }
    } else {
      // Moving a directory — all files under it
      const prefix = draggingNode + "/"
      const dirName = draggingNode.split("/").pop()!
      const newDirPath = actualTarget ? `${actualTarget}/${dirName}` : dirName
      if (newDirPath !== draggingNode && !newDirPath.startsWith(draggingNode + "/")) {
        const updated = sourceFiles.map((f) => {
          if (f.path.startsWith(prefix) || f.path === draggingNode) {
            const newP = newDirPath + f.path.slice(draggingNode.length)
            return { ...f, path: newP }
          }
          return f
        })
        onSourceFilesChange(updated)
        if (activeFilePath.startsWith(prefix)) {
          activatePath(newDirPath + activeFilePath.slice(draggingNode.length))
        }
      }
    }

    setDraggingNode(null)
    setDropTargetDir(null)
  }

  const handleNodeDragEnd = () => {
    setDraggingNode(null)
    setDropTargetDir(null)
  }

  /* ================================================================ */
  /*  Tree rendering                                                   */
  /* ================================================================ */

  const renderNode = (node: TreeNode, depth: number): React.ReactElement => {
    if (node.kind === "directory") {
      const isExpanded = expandedDirs.includes(node.path)
      const isDropTarget = dropTargetDir === node.path
      return (
        <div key={node.path}>
          <button
            type="button"
            draggable={node.path !== entryModulePath}
            onDragStart={(e) => handleNodeDragStart(e, node.path)}
            onDragEnd={handleNodeDragEnd}
            onDragOver={(e) => handleDirDragOver(e, node.path)}
            onDrop={(e) => handleDirDrop(e, node.path)}
            className={cn(
              "flex h-[22px] w-full items-center gap-1 text-left text-[13px] transition-colors duration-75",
              palette.text,
              isDropTarget ? palette.dropTarget : palette.rowHover
            )}
            style={{ paddingLeft: `${8 + depth * 16}px` }}
            onClick={() => toggleDir(node.path)}
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

    const isActive = node.path === activeFile?.path
    const isEntry = node.path === entryModulePath
    const isGitkeep = node.name === ".gitkeep"

    if (isGitkeep) return <span key={node.path} />

    return (
      <div
        key={node.path}
        draggable={!isEntry}
        onDragStart={(e) => handleNodeDragStart(e, node.path)}
        onDragEnd={handleNodeDragEnd}
        className={cn(
          "group flex h-[22px] items-center transition-colors duration-75",
          isActive && palette.activeRow
        )}
      >
        <button
          type="button"
          className={cn(
            "flex min-w-0 flex-1 items-center gap-1 text-left text-[13px]",
            !isActive && palette.rowHover,
            palette.text
          )}
          style={{ paddingLeft: `${10 + depth * 16}px` }}
          onClick={() => {
            activatePath(node.path)
            setOpenTabs((prev) =>
              prev.includes(node.path) ? prev : [...prev, node.path]
            )
          }}
        >
          <FileCode2 className="h-[14px] w-[14px] shrink-0 text-[#519aba]" />
          <span className="truncate pl-0.5">{node.name}</span>
          {isEntry && (
            <span
              className={cn(
                "ml-auto mr-2 text-[9px] font-medium uppercase tracking-[0.1em]",
                palette.accent
              )}
            >
              entry
            </span>
          )}
        </button>
        {!isEntry && sourceFiles.length > 1 && (
          <button
            type="button"
            className={cn(
              "mr-1 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[3px] opacity-0 transition-opacity group-hover:opacity-100",
              palette.muted,
              palette.buttonHover
            )}
            onClick={() => handleDeleteFile(node.path)}
            title={`Delete ${node.path}`}
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    )
  }

  /* ================================================================ */
  /*  Render                                                           */
  /* ================================================================ */

  const visibleTabs = useMemo(() => {
    const sourcePaths = sourceFiles.map((f) => f.path)
    const sourcePathSet = new Set(sourcePaths)
    const kept = openTabs.filter((path) => path === "__CONFIG__" || sourcePathSet.has(path))
    const withActive =
      (activeFilePath === "__CONFIG__" || sourcePathSet.has(activeFilePath)) && !kept.includes(activeFilePath)
        ? [...kept, activeFilePath]
        : kept

    if (sourcePaths.length === 0) {
      return withActive
    }

    const hasFileTab = withActive.some((path) => path !== "__CONFIG__")
    return hasFileTab ? withActive : sourcePaths
  }, [activeFilePath, openTabs, sourceFiles])

  return (
    <div className={cn("flex h-full min-h-0 min-w-0 overflow-hidden", palette.appBg, palette.text)}>
      {/* -------- SIDEBAR -------- */}
      <div
        className={cn(
          "flex flex-col mx-1 mr-2 shadow-sm mb-2.5 rounded-md overflow-hidden",
          isResizingState ? "transition-none" : "transition-[width] duration-150",
          palette.sidebarBg
        )}
        style={{ width: isTreeOpen ? `${sidebarWidth}px` : "0px" }}
      >
        {isTreeOpen && (
          <div
            className="flex flex-1 flex-col overflow-hidden"
            onDragOver={handleRootDragOver}
            onDrop={(e) => handleDirDrop(e, "__root__")}
          >
            {/* Items count header + action buttons */}
            <div
              className={cn(
                "flex h-[34px] shrink-0 items-center justify-between pl-3 pr-2 pt-1",
                palette.subtleBorder
              )}
            >
              <span className={cn("text-[11px] font-medium uppercase tracking-[0.08em]", palette.dim)}>
                {sourceFiles.filter((f) => !f.path.endsWith("/.gitkeep")).length} items
              </span>
              <div className="flex items-center">
                <button
                  type="button"
                  className={cn(
                    "flex h-[22px] w-[22px] items-center justify-center rounded-[3px] transition-colors",
                    palette.dim,
                    palette.buttonHover
                  )}
                  onClick={handleAddFile}
                  title="New file"
                >
                  <FilePlus2 className="h-[14px] w-[14px]" />
                </button>
                <button
                  type="button"
                  className={cn(
                    "flex h-[22px] w-[22px] items-center justify-center rounded-[3px] transition-colors",
                    palette.dim,
                    palette.buttonHover
                  )}
                  onClick={handleAddDir}
                  title="New folder"
                >
                  <FolderPlus className="h-[14px] w-[14px]" />
                </button>
              </div>
            </div>

            {/* File tree */}
            <div className="flex-1 overflow-y-auto overflow-x-hidden py-0.5">
              <div
                className={cn(
                  "group flex h-[22px] items-center transition-colors duration-75",
                  activeFilePath === "__CONFIG__" && palette.activeRow
                )}
              >
                <button
                  type="button"
                  className={cn(
                    "flex min-w-0 flex-1 items-center gap-1 text-left text-[13px]",
                    activeFilePath !== "__CONFIG__" && palette.rowHover,
                    palette.text
                  )}
                  style={{ paddingLeft: `10px` }}
                  onClick={() => {
                    activatePath("__CONFIG__")
                    setOpenTabs((prev) =>
                      prev.includes("__CONFIG__") ? prev : [...prev, "__CONFIG__"]
                    )
                  }}
                >
                  <Settings2 className="h-[14px] w-[14px] shrink-0 text-muted-foreground" />
                  <span className="truncate pl-0.5">Configuration</span>
                </button>
              </div>
              {tree.map((node) => renderNode(node, 0))}
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
        {/* Tab bar wrapper */}
        <div className="relative z-10 flex h-[35px] shrink-0 mr-3 items-stretch overflow-x-auto bg-background transition-colors duration-300 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
          <div
            className={cn(
              "flex rounded-md shrink-0 items-stretch w-max transition-colors duration-300",
              palette.topBarBg
            )}
          >
            {visibleTabs.map((filePath, idx) => {
              if (filePath === "__CONFIG__") {
                const isActive = activeFilePath === "__CONFIG__"
                const isDragging = draggingTab === "__CONFIG__"
                const isDropTarget = tabDropIndex === idx
                return (
                  <div
                    key="__CONFIG__"
                    draggable
                    onDragStart={(e) => handleTabDragStart(e, "__CONFIG__")}
                    onDragEnd={handleTabDragEnd}
                    onDragOver={(e) => handleTabDragOver(e, idx)}
                    onDrop={(e) => handleTabDrop(e, idx)}
                    className={cn(
                      "group relative z-10 flex min-w-[100px] max-w-[180px] shrink-0 items-center gap-1.5 rounded-t-md px-3 text-[12px] transition-colors duration-75",
                      isActive
                        ? cn(palette.activeTab, "border-b-0 -mb-px z-[1]")
                        : cn(palette.inactiveTab, palette.tabHover, "rounded-md"),
                      isDragging && "opacity-40",
                      isDropTarget && "border-l-2 border-l-[#3794ff]",
                      idx === 0 && "rounded-tl-none"
                    )}
                    style={{
                      ...(isActive
                        ? {
                            borderLeft: idx === 0 ? undefined : `1px solid var(--border)`,
                            borderRight: `1px solid var(--border)`,
                            borderTop: `1px solid var(--border)`,
                            boxShadow: `inset 0 1px 0 0 0`,
                          }
                        : {}),
                    }}
                    onClick={() => activatePath("__CONFIG__")}
                  >
                    <Settings2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">Configuration</span>
                    <button
                      type="button"
                      className={cn(
                        "ml-auto flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[3px] opacity-0 transition-opacity group-hover:opacity-100",
                        palette.muted,
                        palette.buttonHover
                      )}
                      onClick={(e) => {
                        e.stopPropagation()
                        handleCloseTab("__CONFIG__")
                      }}
                      title="Close tab"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                )
              }

              const file = sourceFiles.find((f) => f.path === filePath)
              if (!file) return null
              const isActive = file.path === activeFile?.path
              const isEntry = file.path === entryModulePath
              const isDragging = draggingTab === file.path
              const isDropTarget = tabDropIndex === idx

              return (
                <div
                  key={file.path}
                  draggable
                  onDragStart={(e) => handleTabDragStart(e, file.path)}
                  onDragEnd={handleTabDragEnd}
                  onDragOver={(e) => handleTabDragOver(e, idx)}
                  onDrop={(e) => handleTabDrop(e, idx)}
                  className={cn(
                    "group relative z-10 flex min-w-[100px] max-w-[180px] shrink-0 items-center gap-1.5 rounded-t-md px-3 text-[12px] transition-colors duration-75",
                    isActive
                      ? cn(palette.activeTab, "border-b-0 -mb-px z-[1]")
                      : cn(palette.inactiveTab, palette.tabHover, "rounded-md"),
                    isDragging && "opacity-40",
                    isDropTarget && "border-l-2 border-l-[#3794ff]",
                    idx === 0 && "rounded-tl-none"
                  )}
                  style={{
                    ...(isActive
                      ? {
                          borderLeft: idx === 0 ? undefined : `1px solid var(--border)`,
                          borderRight: `1px solid var(--border)`,
                          borderTop: `1px solid var(--border)`,
                          boxShadow: `inset 0 1px 0 0 0`,
                        }
                      : {}),
                  }}
                  onClick={() => activatePath(file.path)}
                >
                  <FileCode2 className="h-3.5 w-3.5 shrink-0 text-[#519aba]" />
                  <span className="truncate">{file.path.split("/").pop()}</span>
                  {isEntry && (
                    <span className={cn("text-[9px] font-medium uppercase tracking-[0.08em]", palette.accent)}>
                      M
                    </span>
                  )}
                  {!isEntry && (
                    <button
                      type="button"
                      className={cn(
                        "ml-auto flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[3px] opacity-0 transition-opacity group-hover:opacity-100",
                        palette.muted,
                        palette.buttonHover
                      )}
                      onClick={(e) => {
                        e.stopPropagation()
                        handleCloseTab(file.path)
                      }}
                      title="Close tab"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </div>
              )
            })}
          </div>
          {/* Drop zone at end */}
          <div
            className="min-w-[40px] flex-1"
            onDragOver={(e) => {
              e.preventDefault()
              setTabDropIndex(visibleTabs.length)
            }}
            onDrop={(e) => handleTabDrop(e, visibleTabs.length)}
          />
        </div>

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
          {activeFilePath === "__CONFIG__" ? (
            <div 
               className="flex-1 overflow-auto bg-background"
               onScroll={(e) => setIsScrolled(e.currentTarget.scrollTop > 0)}
            >
              {configContent}
            </div>
          ) : (
            <ArtifactCredentialCodeEditor
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
