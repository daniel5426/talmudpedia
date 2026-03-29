"use client"

import { FilePlus2, FolderPlus, Upload } from "lucide-react"

import { cn } from "@/lib/utils"

type ArtifactWorkspaceSidebarHeaderProps = {
  itemCount: number
  loading?: boolean
  palette: {
    subtleBorder: string
    dim: string
    buttonHover: string
  }
  onAddFile: () => void
  onImportFiles: () => void
  onAddFolder: () => void
}

export function ArtifactWorkspaceSidebarHeader({
  itemCount,
  loading = false,
  palette,
  onAddFile,
  onImportFiles,
  onAddFolder,
}: ArtifactWorkspaceSidebarHeaderProps) {
  return (
    <div
      className={cn(
        "flex h-[34px] shrink-0 items-center justify-between pl-3 pr-2 pt-1",
        palette.subtleBorder,
      )}
    >
      <span className={cn("text-[11px] font-medium uppercase tracking-[0.08em]", palette.dim)}>
        {itemCount} items
      </span>
      <div className="flex items-center">
        <button
          type="button"
          className={cn(
            "flex h-[22px] w-[22px] items-center justify-center rounded-[3px] transition-colors",
            palette.dim,
            palette.buttonHover,
          )}
          onClick={onAddFile}
          disabled={loading}
          title="New file"
        >
          <FilePlus2 className="h-[14px] w-[14px]" />
        </button>
        <button
          type="button"
          className={cn(
            "flex h-[22px] w-[22px] items-center justify-center rounded-[3px] transition-colors",
            palette.dim,
            palette.buttonHover,
          )}
          onClick={onImportFiles}
          disabled={loading}
          title="Import files"
        >
          <Upload className="h-[14px] w-[14px]" />
        </button>
        <button
          type="button"
          className={cn(
            "flex h-[22px] w-[22px] items-center justify-center rounded-[3px] transition-colors",
            palette.dim,
            palette.buttonHover,
          )}
          onClick={onAddFolder}
          disabled={loading}
          title="New folder"
        >
          <FolderPlus className="h-[14px] w-[14px]" />
        </button>
      </div>
    </div>
  )
}
