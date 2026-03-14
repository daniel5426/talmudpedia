"use client"

import { History, Loader2, RefreshCw, RotateCcw, Sparkles } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { ArtifactVersionListItem } from "@/services/artifacts"

type ArtifactVersionsDrawerProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  versions: ArtifactVersionListItem[]
  isLoading: boolean
  applyingRevisionId: string | null
  hasUnsavedChanges: boolean
  onRefresh: () => void
  onSelectVersion: (revisionId: string) => void
}

function formatVersionBadge(version: ArtifactVersionListItem): string {
  const label = String(version.version_label || "").trim()
  if (label && label !== "draft") {
    return label
  }
  return `Save ${version.revision_number}`
}

export function ArtifactVersionsDrawer({
  open,
  onOpenChange,
  versions,
  isLoading,
  applyingRevisionId,
  hasUnsavedChanges,
  onRefresh,
  onSelectVersion,
}: ArtifactVersionsDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 border-l border-border/70 bg-background/95 p-0 backdrop-blur sm:max-w-md">
        <SheetHeader className="gap-2 border-b border-border/60 bg-muted/20 px-5 py-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary">
                <History className="h-4.5 w-4.5" />
              </div>
              <div className="min-w-0">
                <SheetTitle className="text-base">Version History</SheetTitle>
                <SheetDescription className="mt-0.5 text-xs">
                  Every explicit save creates a reversible artifact version.
                </SheetDescription>
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
              onClick={onRefresh}
              disabled={isLoading}
              aria-label="Refresh versions"
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            </Button>
          </div>
        </SheetHeader>

        <div className="border-b border-border/60 px-5 py-3">
          <div className="flex items-start gap-2 rounded-2xl border border-primary/15 bg-primary/[0.06] px-3 py-2.5">
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
            <p className="text-xs leading-5 text-muted-foreground">
              Selecting a version loads it into the working draft. It does not overwrite the current saved artifact until you click <span className="font-medium text-foreground">Save</span>.
            </p>
          </div>
        </div>

        <ScrollArea className="min-h-0 flex-1 px-3 py-3">
          <div className="space-y-2">
            {isLoading && versions.length === 0 ? (
              <>
                <Skeleton className="h-24 w-full rounded-2xl" />
                <Skeleton className="h-24 w-full rounded-2xl" />
                <Skeleton className="h-24 w-full rounded-2xl" />
              </>
            ) : null}

            {versions.map((version) => {
              const isApplying = applyingRevisionId === version.id
              return (
                <button
                  key={version.id}
                  type="button"
                  className={cn(
                    "group block w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                    version.is_current_draft
                      ? "border-primary/35 bg-primary/[0.08]"
                      : "border-border/60 bg-background hover:border-border hover:bg-muted/25",
                  )}
                  onClick={() => onSelectVersion(version.id)}
                  disabled={Boolean(applyingRevisionId)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-foreground">
                          {formatVersionBadge(version)}
                        </span>
                        {version.is_current_draft ? <Badge className="h-5 bg-primary/15 px-2 text-[10px] text-primary">Current draft</Badge> : null}
                        {version.is_current_published ? <Badge variant="secondary" className="h-5 px-2 text-[10px]">Published</Badge> : null}
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                        <span>{new Date(version.created_at).toLocaleString()}</span>
                        <span>{version.source_file_count} files</span>
                        {version.created_by ? <span>{version.created_by}</span> : null}
                      </div>
                    </div>
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border/60 bg-background text-muted-foreground transition-colors group-hover:text-foreground">
                      {isApplying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                    </div>
                  </div>
                </button>
              )
            })}

            {!isLoading && versions.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
                No saved versions yet.
              </div>
            ) : null}
          </div>
        </ScrollArea>

        <div className="border-t border-border/60 px-5 py-3 text-[11px] text-muted-foreground">
          {hasUnsavedChanges
            ? "You have unsaved working-draft changes. Publishing from the editor will save first."
            : "The latest saved version is loaded. Publishing uses the latest saved version."}
        </div>
      </SheetContent>
    </Sheet>
  )
}
