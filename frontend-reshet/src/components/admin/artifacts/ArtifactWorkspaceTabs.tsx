"use client"

import { FileCode2, Settings2, X } from "lucide-react"

import { ARTIFACT_CONFIG_FILE_PATH } from "@/components/admin/artifacts/artifactWorkspaceUtils"
import { cn } from "@/lib/utils"
import type { ArtifactSourceFile } from "@/services/artifacts"

type ArtifactWorkspaceTabsProps = {
  activeFilePath: string
  sourceFiles: ArtifactSourceFile[]
  openTabs: string[]
  unsavedPaths?: string[]
  entryModulePath?: string
  loading?: boolean
  draggingTab: string | null
  tabDropIndex: number | null
  palette: {
    activeTab: string
    inactiveTab: string
    tabHover: string
    buttonHover: string
    muted: string
    accent: string
    topBarBg: string
  }
  onActivatePath: (path: string) => void
  onCloseTab: (path: string) => void
  onTabDragStart: (event: React.DragEvent, path: string) => void
  onTabDragOver: (event: React.DragEvent, index: number) => void
  onTabDrop: (event: React.DragEvent, index: number) => void
  onTabDragEnd: () => void
  onTabDropIndexChange: (index: number) => void
}

export function ArtifactWorkspaceTabs({
  activeFilePath,
  sourceFiles,
  openTabs,
  unsavedPaths = [],
  entryModulePath,
  loading = false,
  draggingTab,
  tabDropIndex,
  palette,
  onActivatePath,
  onCloseTab,
  onTabDragStart,
  onTabDragOver,
  onTabDrop,
  onTabDragEnd,
  onTabDropIndexChange,
}: ArtifactWorkspaceTabsProps) {
  const sourcePaths = sourceFiles.map((file) => file.path)
  const sourcePathSet = new Set(sourcePaths)
  const unsavedPathSet = new Set(unsavedPaths)
  const keptTabs = openTabs.filter((path) => path === ARTIFACT_CONFIG_FILE_PATH || sourcePathSet.has(path))
  const visibleTabs =
    (activeFilePath === ARTIFACT_CONFIG_FILE_PATH || sourcePathSet.has(activeFilePath)) && !keptTabs.includes(activeFilePath)
      ? [...keptTabs, activeFilePath]
      : keptTabs
  const finalVisibleTabs =
    sourcePaths.length > 0 && !visibleTabs.some((path) => path !== ARTIFACT_CONFIG_FILE_PATH) ? sourcePaths : visibleTabs

  return (
    <div className="relative z-10 flex h-[35px] shrink-0 mr-3 items-stretch overflow-x-auto bg-background transition-colors duration-300 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
      <div className={cn("flex rounded-md shrink-0 items-stretch w-max transition-colors duration-300", palette.topBarBg)}>
        {finalVisibleTabs.map((filePath, index) => {
          if (filePath === ARTIFACT_CONFIG_FILE_PATH) {
            const isActive = activeFilePath === ARTIFACT_CONFIG_FILE_PATH
            const isDragging = draggingTab === ARTIFACT_CONFIG_FILE_PATH
            const isDropTarget = tabDropIndex === index
            return (
              <div
                key={ARTIFACT_CONFIG_FILE_PATH}
                draggable
                onDragStart={(event) => onTabDragStart(event, ARTIFACT_CONFIG_FILE_PATH)}
                onDragEnd={onTabDragEnd}
                onDragOver={(event) => onTabDragOver(event, index)}
                onDrop={(event) => onTabDrop(event, index)}
                className={cn(
                  "group relative z-10 flex min-w-[100px] max-w-[180px] shrink-0 items-center gap-1.5 rounded-t-md px-3 text-[12px] transition-colors duration-75",
                  isActive ? cn(palette.activeTab, "border-b-0 -mb-px z-[1]") : cn(palette.inactiveTab, palette.tabHover, "rounded-md"),
                  isDragging && "opacity-40",
                  isDropTarget && "border-l-2 border-l-[#3794ff]",
                  index === 0 && "rounded-tl-none",
                )}
                style={{
                  ...(isActive
                    ? {
                        borderLeft: index === 0 ? undefined : "1px solid var(--border)",
                        borderRight: "1px solid var(--border)",
                        borderTop: "1px solid var(--border)",
                        boxShadow: "inset 0 1px 0 0 0",
                      }
                    : {}),
                }}
                onClick={() => {
                  if (loading) return
                  onActivatePath(ARTIFACT_CONFIG_FILE_PATH)
                }}
              >
                <Settings2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">Configuration</span>
                <button
                  type="button"
                  className={cn(
                    "ml-auto flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[3px] opacity-0 transition-opacity group-hover:opacity-100",
                    palette.muted,
                    palette.buttonHover,
                  )}
                  onClick={(event) => {
                    event.stopPropagation()
                    onCloseTab(ARTIFACT_CONFIG_FILE_PATH)
                  }}
                  title="Close tab"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )
          }

          const file = sourceFiles.find((sourceFile) => sourceFile.path === filePath)
          if (!file) return null

          const isActive = file.path === activeFilePath
          const isEntry = file.path === entryModulePath
          const isDragging = draggingTab === file.path
          const isDropTarget = tabDropIndex === index
          const isUnsaved = unsavedPathSet.has(file.path)

          return (
            <div
              key={file.path}
              draggable
              onDragStart={(event) => onTabDragStart(event, file.path)}
              onDragEnd={onTabDragEnd}
              onDragOver={(event) => onTabDragOver(event, index)}
              onDrop={(event) => onTabDrop(event, index)}
              className={cn(
                "group relative z-10 flex min-w-[100px] max-w-[180px] shrink-0 items-center gap-1.5 rounded-t-md px-3 text-[12px] transition-colors duration-75",
                isActive ? cn(palette.activeTab, "border-b-0 -mb-px z-[1]") : cn(palette.inactiveTab, palette.tabHover, "rounded-md"),
                isDragging && "opacity-40",
                isDropTarget && "border-l-2 border-l-[#3794ff]",
                index === 0 && "rounded-tl-none",
              )}
              style={{
                ...(isActive
                  ? {
                      borderLeft: index === 0 ? undefined : "1px solid var(--border)",
                      borderRight: "1px solid var(--border)",
                      borderTop: "1px solid var(--border)",
                      boxShadow: "inset 0 1px 0 0 0",
                    }
                  : {}),
              }}
              onClick={() => {
                if (loading) return
                onActivatePath(file.path)
              }}
            >
              <FileCode2 className="h-3.5 w-3.5 shrink-0 text-[#519aba]" />
              <span className="truncate">{file.path.split("/").pop()}</span>
              {isUnsaved ? (
                <span
                  aria-label="Unsaved changes"
                  className="h-2 w-2 shrink-0 rounded-full bg-primary"
                  title="Unsaved changes"
                />
              ) : null}
              {isEntry && <span className={cn("text-[9px] font-medium uppercase tracking-[0.08em]", palette.accent)}>M</span>}
              {!isEntry && (
                <button
                  type="button"
                  className={cn(
                    "ml-auto flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[3px] opacity-0 transition-opacity group-hover:opacity-100",
                    palette.muted,
                    palette.buttonHover,
                  )}
                  onClick={(event) => {
                    event.stopPropagation()
                    onCloseTab(file.path)
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
      <div
        className="min-w-[40px] flex-1"
        onDragOver={(event) => {
          event.preventDefault()
          onTabDropIndexChange(finalVisibleTabs.length)
        }}
        onDrop={(event) => onTabDrop(event, finalVisibleTabs.length)}
      />
    </div>
  )
}
