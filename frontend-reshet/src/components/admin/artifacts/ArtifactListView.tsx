"use client"

import { useMemo, useRef, useState } from "react"
import { Bot, Copy, Database, Download, Edit, Loader2, MoreHorizontal, Package, PencilLine, Trash2, Upload, Wrench } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { SearchInput } from "@/components/ui/search-input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Artifact, ArtifactKind } from "@/services/artifacts"
import { kindLabel } from "@/components/admin/artifacts/artifactPageUtils"
import { cn } from "@/lib/utils"

type ArtifactListViewProps = {
  artifacts: Artifact[]
  loading?: boolean
  publishingId: string | null
  bulkAction: "duplicate" | "publish" | "delete" | "import" | "export" | null
  onEditArtifact: (artifact: Artifact) => void
  onDeleteArtifact: (artifact: Artifact) => void
  onPublishArtifact: (artifact: Artifact) => void
  onDuplicateArtifact: (artifact: Artifact) => void
  onDownloadArtifact: (artifact: Artifact) => Promise<void> | void
  onUploadArtifactFiles: (files: File[]) => Promise<void> | void
  onBulkDeleteArtifacts: (artifacts: Artifact[]) => Promise<void>
  onBulkPublishArtifacts: (artifacts: Artifact[]) => Promise<void>
  onBulkDuplicateArtifacts: (artifacts: Artifact[]) => Promise<void>
  onBulkDownloadArtifacts: (artifacts: Artifact[]) => Promise<void>
}

function kindIcon(kind: ArtifactKind) {
  if (kind === "agent_node") return Bot
  if (kind === "rag_operator") return Database
  return Wrench
}

const createdAtFormatter = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
})

function formatCreatedAt(createdAt?: string) {
  if (!createdAt) return "—"
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return "—"
  return createdAtFormatter.format(date)
}

export function ArtifactListView({
  artifacts,
  loading = false,
  publishingId,
  bulkAction,
  onEditArtifact,
  onDeleteArtifact,
  onPublishArtifact,
  onDuplicateArtifact,
  onDownloadArtifact,
  onUploadArtifactFiles,
  onBulkDeleteArtifacts,
  onBulkPublishArtifacts,
  onBulkDuplicateArtifacts,
  onBulkDownloadArtifacts,
}: ArtifactListViewProps) {
  const [searchQuery, setSearchQuery] = useState("")
  const [selectionMode, setSelectionMode] = useState(false)
  const [rawSelectedIds, setRawSelectedIds] = useState<string[]>([])
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const filteredArtifacts = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()
    if (!normalizedQuery) return artifacts
    return artifacts.filter((artifact) => (
      artifact.display_name.toLowerCase().includes(normalizedQuery)
      || kindLabel(artifact.kind).toLowerCase().includes(normalizedQuery)
      || artifact.owner_type.toLowerCase().includes(normalizedQuery)
      || artifact.version.toLowerCase().includes(normalizedQuery)
    ))
  }, [artifacts, searchQuery])
  const artifactIds = useMemo(() => new Set(artifacts.map((artifact) => artifact.id)), [artifacts])
  const selectedIds = useMemo(
    () => (selectionMode ? rawSelectedIds.filter((id) => artifactIds.has(id)) : []),
    [artifactIds, rawSelectedIds, selectionMode],
  )

  const selectedVisibleArtifacts = useMemo(
    () => filteredArtifacts.filter((artifact) => selectedIds.includes(artifact.id)),
    [filteredArtifacts, selectedIds],
  )
  const publishableSelectedArtifacts = useMemo(
    () => selectedVisibleArtifacts.filter((artifact) => artifact.type === "draft" && artifact.owner_type === "tenant"),
    [selectedVisibleArtifacts],
  )
  const deletableSelectedArtifacts = useMemo(
    () => selectedVisibleArtifacts.filter((artifact) => artifact.owner_type === "tenant"),
    [selectedVisibleArtifacts],
  )
  const allVisibleSelected = filteredArtifacts.length > 0 && selectedVisibleArtifacts.length === filteredArtifacts.length
  const someVisibleSelected = selectedVisibleArtifacts.length > 0 && !allVisibleSelected
  const isMutating = bulkAction !== null

  const toggleArtifactSelection = (artifactId: string, checked: boolean) => {
    setRawSelectedIds((current) => (
      checked
        ? Array.from(new Set([...current, artifactId]))
        : current.filter((id) => id !== artifactId)
    ))
  }

  const toggleSelectAllVisible = (checked: boolean) => {
    if (!checked) {
      setRawSelectedIds((current) => current.filter((id) => !filteredArtifacts.some((artifact) => artifact.id === id)))
      return
    }

    setRawSelectedIds((current) => Array.from(new Set([
      ...current,
      ...filteredArtifacts.map((artifact) => artifact.id),
    ])))
  }

  const runBulkAction = async (action: () => Promise<void>) => {
    await action()
    setRawSelectedIds([])
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <SearchInput
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="Search artifacts..."
          wrapperClassName="max-w-md flex-1"
        />
        <div className="flex flex-wrap items-center justify-end gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            multiple
            className="hidden"
            onChange={(event) => {
              const files = Array.from(event.target.files || [])
              if (files.length > 0) {
                void onUploadArtifactFiles(files)
              }
              event.currentTarget.value = ""
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5"
            disabled={isMutating}
            onClick={() => fileInputRef.current?.click()}
          >
            {bulkAction === "import" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            Upload Files
          </Button>
          {selectionMode && selectedVisibleArtifacts.length > 0 ? (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={isMutating}
                onClick={() => {
                  void runBulkAction(() => onBulkDownloadArtifacts(selectedVisibleArtifacts))
                }}
              >
                {bulkAction === "export" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                Download Files ({selectedVisibleArtifacts.length})
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={isMutating}
                onClick={() => {
                  void runBulkAction(() => onBulkDuplicateArtifacts(selectedVisibleArtifacts))
                }}
              >
                {bulkAction === "duplicate" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Copy className="h-3.5 w-3.5" />}
                Duplicate ({selectedVisibleArtifacts.length})
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={isMutating || publishableSelectedArtifacts.length === 0}
                onClick={() => {
                  void runBulkAction(() => onBulkPublishArtifacts(publishableSelectedArtifacts))
                }}
              >
                {bulkAction === "publish" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                Publish ({publishableSelectedArtifacts.length})
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                className="gap-1.5"
                disabled={isMutating || deletableSelectedArtifacts.length === 0}
                onClick={() => {
                  void runBulkAction(() => onBulkDeleteArtifacts(deletableSelectedArtifacts))
                }}
              >
                {bulkAction === "delete" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                Delete ({deletableSelectedArtifacts.length})
              </Button>
            </>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={cn("h-8 w-8 shrink-0 border-0 shadow-none", selectionMode && "bg-primary/5 text-primary")}
            onClick={() => {
              const nextSelectionMode = !selectionMode
              setSelectionMode(nextSelectionMode)
              if (!nextSelectionMode) {
                setRawSelectedIds([])
              }
            }}
            aria-label={selectionMode ? "Hide selection controls" : "Show selection controls"}
          >
            <PencilLine className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              {selectionMode ? (
                <TableHead className="w-8">
                  <Checkbox
                    checked={allVisibleSelected || (someVisibleSelected && "indeterminate")}
                    onCheckedChange={(checked) => toggleSelectAllVisible(Boolean(checked))}
                    aria-label="Select all visible artifacts"
                  />
                </TableHead>
              ) : null}
              <TableHead>Artifact</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead>Version</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              Array.from({ length: 4 }).map((_, index) => (
                <TableRow key={`skeleton-${index}`}>
                  {selectionMode ? (
                    <TableCell>
                      <Skeleton className="h-4 w-4 rounded-sm" />
                    </TableCell>
                  ) : null}
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-3">
                      <Skeleton className="h-8 w-8 rounded-lg" />
                      <div className="flex flex-col gap-2">
                        <Skeleton className="h-4 w-36" />
                        <Skeleton className="h-3 w-20" />
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-6 w-20 rounded-full" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-6 w-20 rounded-full" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-10" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-20" />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end">
                      <Skeleton className="h-8 w-8 rounded-md" />
                    </div>
                  </TableCell>
                </TableRow>
              ))
            ) : filteredArtifacts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={selectionMode ? 7 : 6} className="py-12 text-center text-muted-foreground">
                  <div className="flex flex-col items-center gap-2">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                      <Package className="h-6 w-6" />
                    </div>
                    <span>{searchQuery ? "No artifacts match your search." : "No artifacts found."}</span>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              filteredArtifacts.map((artifact) => {
                const Icon = kindIcon(artifact.kind)
                return (
                  <TableRow key={artifact.id} data-state={selectedIds.includes(artifact.id) ? "selected" : undefined}>
                    {selectionMode ? (
                      <TableCell>
                        <Checkbox
                          checked={selectedIds.includes(artifact.id)}
                          onCheckedChange={(checked) => toggleArtifactSelection(artifact.id, Boolean(checked))}
                          aria-label={`Select ${artifact.display_name}`}
                        />
                      </TableCell>
                    ) : null}
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-3">
                        <div className="rounded-lg bg-muted p-2">
                          <Icon className="h-4 w-4" />
                        </div>
                        <div className="flex flex-col">
                          <button
                            type="button"
                            className="w-fit cursor-pointer text-left transition hover:text-primary"
                            onClick={() => onEditArtifact(artifact)}
                          >
                            {artifact.display_name}
                          </button>
                          <span className="text-xs text-muted-foreground">{kindLabel(artifact.kind)}</span>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{kindLabel(artifact.kind)}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={artifact.owner_type === "system" ? "secondary" : "outline"}>{artifact.owner_type}</Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{artifact.version}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatCreatedAt(artifact.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Actions for ${artifact.display_name}`}
                            disabled={isMutating}
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => onEditArtifact(artifact)}>
                            <Edit className="mr-2 h-4 w-4" />
                            Edit
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => onDuplicateArtifact(artifact)}>
                            <Copy className="mr-2 h-4 w-4" />
                            Duplicate
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => void onDownloadArtifact(artifact)}>
                            <Download className="mr-2 h-4 w-4" />
                            Download file
                          </DropdownMenuItem>
                          {artifact.type === "draft" && artifact.owner_type === "tenant" ? (
                            <DropdownMenuItem
                              onClick={() => onPublishArtifact(artifact)}
                              disabled={publishingId === artifact.id || isMutating}
                            >
                              {publishingId === artifact.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                              Publish
                            </DropdownMenuItem>
                          ) : null}
                          {artifact.owner_type === "tenant" ? (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => onDeleteArtifact(artifact)} className="text-destructive">
                                <Trash2 className="mr-2 h-4 w-4" />
                                Delete
                              </DropdownMenuItem>
                            </>
                          ) : null}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
