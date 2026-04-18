"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import {
  FolderOpen,
  HardDrive,
  MoreVertical,
  Trash2,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { SearchInput } from "@/components/ui/search-input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { FileSpace } from "@/services"

type FileSpaceListViewProps = {
  spaces: FileSpace[]
  loading?: boolean
  bulkAction: "delete" | null
  onDeleteSpace: (space: FileSpace) => void
}

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
})

function formatBytes(totalBytes?: number | null) {
  if (!totalBytes || totalBytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB", "TB"]
  let size = totalBytes
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  const digits = size >= 100 || unitIndex === 0 ? 0 : size >= 10 ? 1 : 2
  return `${size.toFixed(digits).replace(/\.0+$|(\.\d*[1-9])0+$/, "$1")} ${units[unitIndex]}`
}

function formatDate(dateStr?: string | null) {
  if (!dateStr) return "—"
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return "—"
  return dateFormatter.format(date)
}

function relativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "—"
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  if (Number.isNaN(then)) return "—"
  const diff = now - then
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (seconds < 60) return "just now"
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days < 30) return `${days}d ago`
  return dateFormatter.format(new Date(dateStr))
}

export function FileSpaceListView({
  spaces,
  loading = false,
  bulkAction,
  onDeleteSpace,
}: FileSpaceListViewProps) {
  const [searchQuery, setSearchQuery] = useState("")

  const filteredSpaces = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()
    if (!normalizedQuery) return spaces
    return spaces.filter(
      (space) =>
        space.name.toLowerCase().includes(normalizedQuery) ||
        (space.description || "").toLowerCase().includes(normalizedQuery) ||
        space.status.toLowerCase().includes(normalizedQuery),
    )
  }, [spaces, searchQuery])

  const isMutating = bulkAction !== null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <SearchInput
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="Search file spaces..."
          wrapperClassName="max-w-md w-full"
        />
        <div className="flex flex-wrap items-center justify-end gap-2">
          {/* Card view specific controls could go here */}
        </div>
      </div>
      
      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={`skeleton-${index}`} className="flex flex-col space-y-3 rounded-xl border border-border/50 bg-card p-5">
              <div className="flex items-start justify-between">
                <Skeleton className="h-10 w-10 rounded-lg" />
                <Skeleton className="h-6 w-16 xl:w-20 rounded-full" />
              </div>
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <div className="pt-2">
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : filteredSpaces.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/70 py-24 text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-muted/50">
            <HardDrive className="h-7 w-7 text-muted-foreground/60" />
          </div>
          <h2 className="text-lg font-medium text-foreground">
            {searchQuery ? "No file spaces match your search" : "No file spaces found"}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {searchQuery
              ? "Try adjusting your search filters."
              : "Create a shared file space to get started."}
          </p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {filteredSpaces.map((space) => (
            <Link
              href={`/admin/files/${space.id}`}
              key={space.id}
              className="group relative flex flex-col justify-between rounded-xl border border-border/60 bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm"
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/50 bg-muted/40 text-muted-foreground/70 transition-colors group-hover:text-primary">
                    <FolderOpen className="h-4.5 w-4.5" />
                  </div>
                  <div onClick={(e) => e.preventDefault()} className="absolute right-3 top-3">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                          disabled={isMutating}
                        >
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem asChild>
                          <Link href={`/admin/files/${space.id}`}>
                            <FolderOpen className="mr-2 h-4 w-4" />
                            Open
                          </Link>
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => onDeleteSpace(space)}
                          className="text-destructive"
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          Archive
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
                
                <div className="mt-3 min-w-0">
                  <h3 className="truncate text-[15px] font-semibold leading-5 text-foreground transition-colors group-hover:text-primary">
                    {space.name}
                  </h3>
                  <p className="mt-1 line-clamp-2 min-h-[36px] text-[13px] leading-4.5 text-muted-foreground/80">
                    {space.description || "No description provided."}
                  </p>
                </div>
              </div>

              <div className="mt-4 space-y-2 border-t border-border/40 pt-3">
                <div className="flex items-center justify-between gap-3 text-[11px] font-medium text-muted-foreground/70">
                  <span className="truncate">{space.file_count ?? 0} files</span>
                  <span className="truncate">{formatBytes(space.total_bytes)}</span>
                </div>
                <div className="flex items-center justify-between gap-3 text-[11px] font-medium text-muted-foreground/60">
                  <span className="truncate">Created {formatDate(space.created_at)}</span>
                  <span className="truncate">Updated {relativeTime(space.updated_at)}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
