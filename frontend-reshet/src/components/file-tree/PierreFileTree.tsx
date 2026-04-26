"use client"

import type { CSSProperties, DragEvent } from "react"
import { useCallback, useEffect, useMemo, useRef } from "react"
import type { ContextMenuItem, ContextMenuOpenContext, FileTree as FileTreeModel } from "@pierre/trees"
import { FileTree, useFileTree, useFileTreeSelection } from "@pierre/trees/react"
import { Copy, Download, Edit3, FilePlus2, FolderPlus, Trash2 } from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

export type PierreFileTreeAction = {
  label: string
  icon?: "copy" | "delete" | "download" | "new-file" | "new-folder" | "rename"
  destructive?: boolean
  disabled?: boolean
  startRenaming?: boolean
  onSelect: (path: string, item: ContextMenuItem) => void
}

type PierreFileTreeProps = {
  paths: string[]
  selectedPath?: string | null
  initialExpansion?: "closed" | "open" | number
  emptyMessage?: string
  className?: string
  readOnly?: boolean
  onSelectPath?: (path: string) => void
  onMovePath?: (sourcePath: string, targetPath: string) => void
  onRenamePath?: (sourcePath: string, targetPath: string) => void
  canDragPath?: (path: string) => boolean
  actions?: PierreFileTreeAction[] | ((item: ContextMenuItem) => PierreFileTreeAction[])
}

const GITKEEP_SUFFIX = "/.gitkeep"

const normalizeInputPath = (path: string): string => {
  const trimmed = path.trim().replace(/^\/+/, "")
  if (!trimmed) return ""
  if (trimmed.endsWith(GITKEEP_SUFFIX)) {
    return `${trimmed.slice(0, -GITKEEP_SUFFIX.length).replace(/\/+$/, "")}/`
  }
  return trimmed.endsWith("/") ? trimmed : trimmed.replace(/\/+$/, "")
}

const pathSignature = (paths: readonly string[]): string => paths.join("\u001f")

const remapPathAfterMove = (path: string, sourcePath: string, targetPath: string): string => {
  if (path === sourcePath) return targetPath
  const sourcePrefix = sourcePath.endsWith("/") ? sourcePath : `${sourcePath}/`
  if (!path.startsWith(sourcePrefix)) return path
  const targetPrefix = targetPath.endsWith("/") ? targetPath : `${targetPath}/`
  return `${targetPrefix}${path.slice(sourcePrefix.length)}`
}

const normalizeFilePath = (path: string | null | undefined): string | null => {
  if (!path) return null
  const trimmed = path.trim().replace(/^\/+/, "").replace(/\/+$/, "")
  return trimmed || null
}

const basename = (path: string): string => {
  const normalized = normalizeFilePath(path) ?? path
  return normalized.split("/").filter(Boolean).pop() || normalized
}

const getFloatingContextMenuTriggerStyle = (anchorRect: ContextMenuOpenContext["anchorRect"]): CSSProperties => ({
  border: 0,
  height: 1,
  left: `${anchorRect.left}px`,
  opacity: 0,
  padding: 0,
  pointerEvents: "none",
  position: "fixed",
  top: `${anchorRect.bottom - 1}px`,
  width: 1,
})

const getContextMenuSideOffset = (anchorRect: ContextMenuOpenContext["anchorRect"]): number =>
  anchorRect.width === 0 && anchorRect.height === 0 ? 0 : -2

const actionIcon = (icon: PierreFileTreeAction["icon"]) => {
  if (icon === "copy") return <Copy className="h-4 w-4" />
  if (icon === "delete") return <Trash2 className="h-4 w-4" />
  if (icon === "download") return <Download className="h-4 w-4" />
  if (icon === "new-file") return <FilePlus2 className="h-4 w-4" />
  if (icon === "new-folder") return <FolderPlus className="h-4 w-4" />
  if (icon === "rename") return <Edit3 className="h-4 w-4" />
  return null
}

function PierreFileTreeContextMenu({
  actions,
  context,
  item,
  model,
}: {
  actions: PierreFileTreeAction[]
  context: ContextMenuOpenContext
  item: ContextMenuItem
  model: FileTreeModel
}) {
  if (actions.length === 0) return null

  return (
    <DropdownMenu
      open
      modal={false}
      onOpenChange={(open) => {
        if (!open) context.close()
      }}
    >
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-hidden="true"
          tabIndex={-1}
          style={getFloatingContextMenuTriggerStyle(context.anchorRect)}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        data-file-tree-context-menu-root="true"
        align="start"
        side="bottom"
        sideOffset={getContextMenuSideOffset(context.anchorRect)}
        className="z-[1000] min-w-52"
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          context.restoreFocus()
        }}
      >
        <div className="truncate px-2 py-1.5 text-xs text-muted-foreground">{normalizeFilePath(item.path) ?? item.path}</div>
        {actions.map((action) => (
          <DropdownMenuItem
            key={action.label}
            disabled={action.disabled}
            variant={action.destructive ? "destructive" : "default"}
            onSelect={() => {
              if (action.startRenaming) {
                context.close({ restoreFocus: false })
                model.startRenaming(item.path)
                return
              }
              action.onSelect(normalizeFilePath(item.path) ?? item.path, item)
              context.close()
            }}
          >
            {actionIcon(action.icon)}
            <span>{action.label}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function PierreFileTreeInner({
  paths,
  selectedPath,
  initialExpansion = "open",
  emptyMessage = "No files yet.",
  className,
  readOnly = false,
  onSelectPath,
  onMovePath,
  onRenamePath,
  canDragPath,
  actions = [],
}: PierreFileTreeProps) {
  const normalizedPaths = useMemo(
    () => Array.from(new Set(paths.map(normalizeInputPath).filter(Boolean))).sort(),
    [paths],
  )
  const selectablePaths = useMemo(
    () => new Set(normalizedPaths.filter((path) => !path.endsWith("/"))),
    [normalizedPaths],
  )
  const normalizedSelectedPath = normalizeFilePath(selectedPath)
  const selectedPathRef = useRef(normalizedSelectedPath)
  const onSelectPathRef = useRef(onSelectPath)
  const onMovePathRef = useRef(onMovePath)
  const onRenamePathRef = useRef(onRenamePath)
  const canDragPathRef = useRef(canDragPath)
  const selectablePathsRef = useRef(selectablePaths)
  const currentPathSignatureRef = useRef(pathSignature(normalizedPaths))
  const lastInternalPathSignatureRef = useRef<string | null>(null)
  const lastMoveEventRef = useRef<{ sourcePath: string; timestamp: number } | null>(null)
  const lastHandledSelectionRef = useRef<readonly string[]>([])

  useEffect(() => {
    selectedPathRef.current = normalizedSelectedPath
    onSelectPathRef.current = onSelectPath
    onMovePathRef.current = onMovePath
    onRenamePathRef.current = onRenamePath
    canDragPathRef.current = canDragPath
    selectablePathsRef.current = selectablePaths
  }, [canDragPath, normalizedSelectedPath, onMovePath, onRenamePath, onSelectPath, selectablePaths])

  const { model } = useFileTree({
    paths: normalizedPaths,
    initialExpansion,
    initialSelectedPaths:
      normalizedSelectedPath && selectablePaths.has(normalizedSelectedPath) ? [normalizedSelectedPath] : [],
    search: false,
    density: "compact",
    flattenEmptyDirectories: true,
    unsafeCSS: `
      [data-file-tree-virtualized-scroll='true'] {
        padding-inline: 0 !important;
      }

      [data-type='item']:hover,
      [data-type='item'][data-item-context-hover='true'],
      [data-type='item'][data-item-selected='true']:hover,
      [data-type='item'][data-item-selected='true'][data-item-context-hover='true'],
      [data-type='item'][data-item-selected='true']:hover:not([data-is-scrolling]) {
        background-color: var(--trees-bg-muted) !important;
        color: var(--trees-fg) !important;
        --truncate-marker-background-overlay-color: var(--trees-bg-muted) !important;
      }
    `,
    dragAndDrop: !readOnly && onMovePath
      ? {
          canDrag: (draggedPaths) => draggedPaths.every((path) => canDragPathRef.current?.(normalizeFilePath(path) ?? path) ?? true),
        }
      : false,
    renaming: !readOnly && (onRenamePath || onMovePath)
      ? {
          canRename: (item) => canDragPathRef.current?.(normalizeFilePath(item.path) ?? item.path) ?? true,
        }
      : false,
    composition: {
      contextMenu: {
        enabled: !readOnly && (typeof actions === "function" || actions.length > 0),
        triggerMode: "right-click",
      },
    },
  })
  const selectedPaths = useFileTreeSelection(model)

  useEffect(() => {
    const nextSignature = pathSignature(normalizedPaths)
    if (nextSignature === currentPathSignatureRef.current) return
    currentPathSignatureRef.current = nextSignature

    if (lastInternalPathSignatureRef.current === nextSignature) {
      lastInternalPathSignatureRef.current = null
      return
    }

    model.resetPaths(normalizedPaths)
  }, [model, normalizedPaths])

  useEffect(() => {
    if (selectedPaths === lastHandledSelectionRef.current) return
    const previousSelection = new Set(lastHandledSelectionRef.current)
    lastHandledSelectionRef.current = selectedPaths

    for (let index = selectedPaths.length - 1; index >= 0; index -= 1) {
      const selected = selectedPaths[index]
      if (previousSelection.has(selected)) continue
      const nextPath = normalizeFilePath(selected)
      if (!nextPath || nextPath === selectedPathRef.current || !selectablePathsRef.current.has(nextPath)) continue
      const item = model.getItem(selected)
      if (item == null || item.isDirectory()) continue
      onSelectPathRef.current?.(nextPath)
      break
    }
  }, [model, selectedPaths])

  useEffect(() => {
    const nextPath = normalizedSelectedPath
    if (!nextPath || !selectablePaths.has(nextPath)) {
      for (const path of model.getSelectedPaths()) {
        model.getItem(path)?.deselect()
      }
      return
    }

    for (const path of model.getSelectedPaths()) {
      if (path !== nextPath) {
        model.getItem(path)?.deselect()
      }
    }

    const item = model.getItem(nextPath)
    if (!item || item.isDirectory()) return
    if (!item.isSelected()) item.select()
  }, [model, normalizedSelectedPath, selectablePaths])

  useEffect(() => {
    return model.onMutation("*", (event) => {
      const moveEvents =
        event.operation === "move"
          ? [event]
          : event.operation === "batch"
            ? event.events.filter((entry) => entry.operation === "move")
            : []
      if (moveEvents.length === 0) return

      let nextPaths = normalizedPaths
      for (const moveEvent of moveEvents) {
        const sourcePath = normalizeInputPath(moveEvent.from)
        const targetPath = normalizeInputPath(moveEvent.to)
        if (!sourcePath || !targetPath || sourcePath === targetPath) continue
        nextPaths = nextPaths.map((path) => remapPathAfterMove(path, sourcePath, targetPath)).sort()
        lastMoveEventRef.current = { sourcePath, timestamp: Date.now() }
        ;(onRenamePathRef.current ?? onMovePathRef.current)?.(normalizeFilePath(sourcePath) ?? sourcePath, normalizeFilePath(targetPath) ?? targetPath)
      }
      lastInternalPathSignatureRef.current = pathSignature(nextPaths)
    })
  }, [model, normalizedPaths])

  const handleRootDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (readOnly || !onMovePathRef.current) return
    if (!event.dataTransfer.types.includes("text/plain")) return
    event.preventDefault()
    event.dataTransfer.dropEffect = "move"
  }, [readOnly])

  const handleRootDrop = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (readOnly || !onMovePathRef.current) return
    const sourcePath = normalizeFilePath(event.dataTransfer.getData("text/plain"))
    if (!sourcePath) return
    event.preventDefault()

    window.setTimeout(() => {
      const lastMoveEvent = lastMoveEventRef.current
      if (lastMoveEvent?.sourcePath === sourcePath && Date.now() - lastMoveEvent.timestamp < 250) return

      const targetPath = basename(sourcePath)
      if (targetPath !== sourcePath) {
        onMovePathRef.current?.(sourcePath, targetPath)
      }
    }, 0)
  }, [readOnly])

  if (normalizedPaths.length === 0) {
    return <p className="px-2 py-4 text-center text-xs text-muted-foreground">{emptyMessage}</p>
  }

  const resolvedStyle = {
    height: "100%",
    "--trees-focus-ring-width-override": "0px",
    "--trees-selected-focused-border-color-override": "transparent",
    "--trees-selected-bg-override": "hsl(var(--accent))",
    "--trees-selected-fg-override": "hsl(var(--accent-foreground))",
    "--trees-padding-inline-override": "0px",
  } as CSSProperties

  const resolveActions = (item: ContextMenuItem): PierreFileTreeAction[] =>
    typeof actions === "function" ? actions(item) : actions

  return (
    <div className="h-full min-h-0 w-full" onDragOver={handleRootDragOver} onDrop={handleRootDrop}>
    <FileTree
      model={model}
      className={cn("h-full min-h-0 w-full", className)}
      style={resolvedStyle}
      renderContextMenu={(item, context) => (
        <PierreFileTreeContextMenu
          actions={resolveActions(item)}
          context={context}
          item={item}
          model={model}
        />
      )}
    />
    </div>
  )
}

export function PierreFileTree(props: PierreFileTreeProps) {
  return <PierreFileTreeInner {...props} />
}
