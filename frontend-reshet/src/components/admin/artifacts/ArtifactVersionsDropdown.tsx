"use client"

import { History } from "lucide-react"

import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { ArtifactVersionListItem } from "@/services/artifacts"

type ArtifactVersionsDropdownProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  versions: ArtifactVersionListItem[]
  isLoading: boolean
  applyingRevisionId: string | null
  hasUnsavedChanges: boolean
  onSelectVersion: (revisionId: string) => void
}

export function ArtifactVersionsDropdown({
  open,
  onOpenChange,
  versions,
  isLoading,
  applyingRevisionId,
  hasUnsavedChanges,
  onSelectVersion,
}: ArtifactVersionsDropdownProps) {
  return (
    <DropdownMenu open={open} onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild>
        <Button
          size="sm"
          variant="ghost"
          className={cn(
            "h-8 w-8 p-0 text-muted-foreground hover:text-foreground",
            hasUnsavedChanges && "text-primary",
          )}
          title="Open version history"
        >
          <History className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={10}
        className=" rounded-md border-border/70 p-1.5 shadow-lg"
      >
        {isLoading && versions.length === 0 ? (
          <div className="space-y-1.5 p-1">
            <Skeleton className="h-12 w-full rounded-xl" />
            <Skeleton className="h-12 w-full rounded-xl" />
            <Skeleton className="h-12 w-full rounded-xl" />
          </div>
        ) : null}

        {!isLoading && versions.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-muted-foreground">
            No versions yet.
          </div>
        ) : null}

        {versions.map((version) => {
          return (
            <button
              key={version.id}
              type="button"
              className={cn(
                "flex w-full items-center justify-between text-left rounded-md px-3 py-2 transition-colors hover:bg-muted/60",
                version.is_current_draft && "bg-muted/40",
              )}
              onClick={() => onSelectVersion(version.id)}
              disabled={Boolean(applyingRevisionId)}
            >
              <div className="min-w-0">
                <div className="truncate text-xs font-medium text-foreground">
                  {new Date(version.created_at).toLocaleString()}
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {version.source_file_count} files
                </div>
              </div>
            </button>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
