"use client"

import type { ChangeEvent } from "react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ArtifactCredentialCodeEditor } from "@/components/admin/artifacts/ArtifactCredentialCodeEditor"
import { ArtifactWorkspaceSidebarHeader } from "@/components/admin/artifacts/ArtifactWorkspaceSidebarHeader"
import { ArtifactWorkspaceTabs } from "@/components/admin/artifacts/ArtifactWorkspaceTabs"
import {
  ARTIFACT_CONFIG_FILE_PATH,
  buildTree,
  collectDirectoryPaths,
  DEFAULT_SIDEBAR_WIDTH,
  editorLanguageForPath,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  moveFilePath,
  nextAvailableDirPath,
  nextAvailablePath,
  normalizeImportedPath,
  type TreeNode,
} from "@/components/admin/artifacts/artifactWorkspaceUtils"
import { Skeleton } from "@/components/ui/skeleton"
import { normalizeCredentialMentionLabels } from "@/lib/credential-mentions"
import { cn } from "@/lib/utils"
import { IntegrationCredential } from "@/services"
import { ArtifactLanguage, ArtifactSourceFile } from "@/services/artifacts"
import {
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  FileCode2,
  Folder,
  FolderOpen,
  Settings2,
  Trash2,
  X,
} from "lucide-react"

/* ------------------------------------------------------------------ */
/*  Props & types                                                      */
/* ------------------------------------------------------------------ */

interface ArtifactWorkspaceEditorProps {
  sourceFiles: ArtifactSourceFile[]
  language: ArtifactLanguage
  tenantSlug?: string
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

const TREE_MENU_DOUBLE_CLICK_MS = 180

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function ArtifactWorkspaceEditor({
  sourceFiles,
  language,
  tenantSlug,
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
  const tree = useMemo(() => buildTree(sourceFiles), [sourceFiles])
  const [expandedDirs, setExpandedDirs] = useState<string[]>(() => collectDirectoryPaths(tree))

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
  const importInputRef = useRef<HTMLInputElement | null>(null)
  const treeMenuRef = useRef<HTMLDivElement | null>(null)
  const lastTreeMenuClickRef = useRef<{ path: string; timestamp: number } | null>(null)

  // ---- scroll state for tab transition effect ----
  const [isScrolled, setIsScrolled] = useState(false)

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

  const activatePath = useCallback((path: string) => {
    setIsScrolled(false)
    onActiveFileChange(path)
  }, [onActiveFileChange, setIsScrolled])

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

  const handleAddFile = () => {
    if (loading) return
    const path = nextAvailablePath(sourceFiles, "", language)
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
  }

  const handleAddDir = useCallback(() => {
    if (loading) return
    const dirName = nextAvailableDirPath(sourceFiles, "")
    const filePath = `${dirName}/.gitkeep`
    onSourceFilesChange([
      ...sourceFiles,
      { path: filePath, content: "" },
    ])
    setExpandedDirs((prev) => (prev.includes(dirName) ? prev : [...prev, dirName]))
    if (!isTreeOpen) setIsTreeOpen(true)
  }, [isTreeOpen, loading, onSourceFilesChange, setIsTreeOpen, sourceFiles])

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

  const handleDeleteFile = (path: string) => {
    if (loading) return
    if (path === entryModulePath || sourceFiles.length <= 1) return
    const next = sourceFiles.filter((f) => f.path !== path)
    onSourceFilesChange(next)
    if (activeFilePath === path) {
      activatePath(next[0]?.path ?? "")
    }
  }

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

  const toggleDir = (path: string) => {
    if (loading) return
    setExpandedDirs((cur) =>
      cur.includes(path) ? cur.filter((v) => v !== path) : [...cur, path]
    )
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

  /* ---- file-tree drag-and-drop ---- */
  const handleNodeDragStart = (e: React.DragEvent, path: string) => {
    if (loading || path === entryModulePath) {
      e.preventDefault()
      return
    }
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

    if (loading) return
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
    } catch (error) {
      console.error(error)
    }
    setTreeMenu(null)
  }

  const handleDownloadFile = (path: string) => {
    const file = sourceFiles.find((entry) => entry.path === path)
    if (!file) {
      setTreeMenu(null)
      return
    }

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
    setTreeMenu(null)
  }

  const openTreeMenu = (
    event: React.MouseEvent<HTMLElement>,
    node: TreeNode,
    options?: { expanded?: boolean }
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
    node: TreeNode,
    options?: { expanded?: boolean }
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
          data-artifact-file-row={node.path}
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
          onContextMenu={(event) => openTreeMenu(event, node)}
          onClickCapture={(event) => maybeOpenTreeMenuFromClick(event, node)}
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
            <ArtifactWorkspaceSidebarHeader
              itemCount={sourceFiles.filter((file) => !file.path.endsWith("/.gitkeep")).length}
              loading={loading}
              palette={palette}
              onAddFile={handleAddFile}
              onImportFiles={() => importInputRef.current?.click()}
              onAddFolder={handleAddDir}
            />

            {/* File tree */}
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
              tenantSlug={tenantSlug}
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
              <FileCode2 className="h-4 w-4 text-muted-foreground" />
            ) : (
              <FolderOpen className="h-4 w-4 text-muted-foreground" />
            )}
            <span>{treeMenu.kind === "file" ? "Open file" : treeMenu.expanded ? "Collapse folder" : "Expand folder"}</span>
          </button>
          {treeMenu.kind === "file" ? (
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-foreground hover:bg-accent"
              onClick={() => handleDownloadFile(treeMenu.path)}
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
              if (treeMenu.kind === "file") {
                handleDeleteFile(treeMenu.path)
              } else {
                const prefix = `${treeMenu.path}/`
                const nextFiles = sourceFiles.filter((file) => file.path !== treeMenu.path && !file.path.startsWith(prefix))
                onSourceFilesChange(nextFiles)
                if (activeFilePath === treeMenu.path || activeFilePath.startsWith(prefix)) {
                  activatePath(nextFiles[0]?.path ?? ARTIFACT_CONFIG_FILE_PATH)
                }
              }
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
