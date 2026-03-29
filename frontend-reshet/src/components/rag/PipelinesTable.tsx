"use client"

import React from "react"
import { useDirection } from "@/components/direction-provider"
import { VisualPipeline } from "@/services"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Progress } from "@/components/ui/progress"
import { SearchInput } from "@/components/ui/search-input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Edit,
  History,
  Trash2,
  CheckCircle2,
  Play,
  Loader2,
  MoreHorizontal,
  Copy,
  Database,
  PencilLine,
  Search,
  Workflow,
} from "lucide-react"
import { cn } from "@/lib/utils"
import Link from "next/link"

interface RunningJobStatus {
  jobId: string
  status: string
  progress?: number
}

interface PipelinesTableProps {
  pipelines: VisualPipeline[]
  onDelete?: (id: string) => void
  onViewHistory?: (pipeline: VisualPipeline) => void
  onRun?: (pipeline: VisualPipeline) => void
  onDuplicate?: (pipeline: VisualPipeline) => void
  onBulkDelete?: (ids: string[]) => Promise<void>
  canDelete?: boolean
  showDescription?: boolean
  runningJobs?: Record<string, RunningJobStatus>
  runningCompileId?: string | null
  duplicatingPipelineId?: string | null
}

export function PipelinesTable({
  pipelines,
  onDelete,
  onViewHistory,
  onRun,
  onDuplicate,
  onBulkDelete,
  canDelete = true,
  showDescription = true,
  runningJobs,
  runningCompileId,
  duplicatingPipelineId,
}: PipelinesTableProps) {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const [searchQuery, setSearchQuery] = React.useState("")
  const [selectionMode, setSelectionMode] = React.useState(false)
  const [selectedIds, setSelectedIds] = React.useState<string[]>([])

  const filteredPipelines = React.useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()
    if (!normalizedQuery) return pipelines
    return pipelines.filter((pipeline) => {
      const typeLabel = pipeline.pipeline_type === "retrieval" ? "retrieval" : "ingestion"
      return [
        pipeline.name,
        pipeline.description ?? "",
        typeLabel,
        `v${pipeline.version}`,
      ].some((value) => value.toLowerCase().includes(normalizedQuery))
    })
  }, [pipelines, searchQuery])

  React.useEffect(() => {
    if (!selectionMode) {
      setSelectedIds([])
      return
    }
    setSelectedIds((current) => current.filter((id) => filteredPipelines.some((pipeline) => pipeline.id === id)))
  }, [filteredPipelines, selectionMode])

  const allVisibleSelected = filteredPipelines.length > 0 && selectedIds.length === filteredPipelines.length
  const someVisibleSelected = selectedIds.length > 0 && !allVisibleSelected

  const toggleSelection = (pipelineId: string, checked: boolean) => {
    setSelectedIds((current) => (
      checked ? Array.from(new Set([...current, pipelineId])) : current.filter((id) => id !== pipelineId)
    ))
  }

  const toggleAllVisible = (checked: boolean) => {
    if (!checked) {
      setSelectedIds([])
      return
    }
    setSelectedIds(filteredPipelines.map((pipeline) => pipeline.id))
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <SearchInput
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="Search pipelines..."
          wrapperClassName="max-w-md flex-1"
          iconPosition={isRTL ? "right" : "left"}
          className={cn(isRTL && "text-right")}
        />
        <div className="flex items-center justify-end gap-2">
          <div className="text-sm text-muted-foreground">
            {filteredPipelines.length} {filteredPipelines.length === 1 ? "pipeline" : "pipelines"}
          </div>
          {selectionMode && selectedIds.length > 0 && onBulkDelete ? (
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => {
                void onBulkDelete(selectedIds)
              }}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete ({selectedIds.length})
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 border-0 shadow-none data-[active=true]:bg-primary/5 data-[active=true]:text-primary"
            data-active={selectionMode}
            onClick={() => setSelectionMode((current) => !current)}
            aria-label={selectionMode ? "Hide selection controls" : "Show selection controls"}
          >
            <PencilLine className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="overflow-hidden rounded-xl border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              {selectionMode ? (
                <TableHead className="w-8">
                  <Checkbox
                    checked={allVisibleSelected || (someVisibleSelected && "indeterminate")}
                    onCheckedChange={(checked) => toggleAllVisible(Boolean(checked))}
                    aria-label="Select all visible pipelines"
                  />
                </TableHead>
              ) : null}
              <TableHead className={cn(isRTL ? "text-right" : "text-left")}>Pipeline</TableHead>
              {showDescription && <TableHead className={cn(isRTL ? "text-right" : "text-left")}>Description</TableHead>}
              <TableHead className={cn(isRTL ? "text-right" : "text-left")}>Type</TableHead>
              <TableHead className={cn(isRTL ? "text-right" : "text-left")}>Version</TableHead>
              <TableHead className={cn(isRTL ? "text-right" : "text-left")}>Status</TableHead>
              <TableHead className={cn(isRTL ? "text-right" : "text-left")}>Updated</TableHead>
              <TableHead className={cn(isRTL ? "text-left" : "text-right")}>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredPipelines.length === 0 ? (
              <TableRow>
                <TableCell colSpan={selectionMode ? (showDescription ? 8 : 7) : (showDescription ? 7 : 6)} className="py-12 text-center">
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                      <Workflow className="h-6 w-6" />
                    </div>
                    <span>{searchQuery ? "No pipelines match your search." : "No pipelines found."}</span>
                    <span className="max-w-sm text-sm text-muted-foreground/80">
                      {searchQuery ? "Try a different pipeline name or type." : "Create a pipeline to start building ingestion and retrieval flows."}
                    </span>
                  </div>
                </TableCell>
              </TableRow>
            ) : filteredPipelines.map((pipeline) => {
              const runningJob = runningJobs?.[pipeline.id]
              const isCompiling = runningCompileId === pipeline.id
              const isDuplicating = duplicatingPipelineId === pipeline.id
              const pipelineHref = runningJob?.jobId
                ? `/admin/pipelines/${pipeline.id}?jobId=${runningJob.jobId}`
                : `/admin/pipelines/${pipeline.id}`
              const TypeIcon = pipeline.pipeline_type === "retrieval" ? Search : Database

              return (
                <TableRow key={pipeline.id}>
                  {selectionMode ? (
                    <TableCell>
                      <Checkbox
                        checked={selectedIds.includes(pipeline.id)}
                        onCheckedChange={(checked) => toggleSelection(pipeline.id, Boolean(checked))}
                        aria-label={`Select ${pipeline.name}`}
                      />
                    </TableCell>
                  ) : null}
                  <TableCell className={cn("font-medium", isRTL ? "text-right" : "text-left")}>
                    <div className={cn("flex items-center gap-3", isRTL && "flex-row-reverse")}>
                      <div className="rounded-lg bg-muted p-2">
                        <TypeIcon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <Link href={pipelineHref} className="block truncate transition hover:text-primary">
                          {pipeline.name}
                        </Link>
                        {!showDescription && pipeline.description ? (
                          <span className="block truncate text-xs font-normal text-muted-foreground">
                            {pipeline.description}
                          </span>
                        ) : null}
                        {runningJob ? (
                          <div className="mt-2">
                            <Progress value={runningJob.progress ?? 5} className="h-1" />
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </TableCell>
                  {showDescription ? (
                    <TableCell className={cn("max-w-[240px] text-muted-foreground", isRTL ? "text-right" : "text-left")}>
                      <span className="line-clamp-2">{pipeline.description || "—"}</span>
                    </TableCell>
                  ) : null}
                  <TableCell className={isRTL ? "text-right" : "text-left"}>
                    {pipeline.pipeline_type === "retrieval" ? (
                      <Badge variant="outline" className="border-purple-500/20 bg-purple-500/10 text-purple-600">
                        Retrieval
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="border-blue-500/20 bg-blue-500/10 text-blue-600">
                        Ingestion
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className={isRTL ? "text-right" : "text-left"}>
                    <Badge variant="outline">v{pipeline.version}</Badge>
                  </TableCell>
                  <TableCell className={isRTL ? "text-right" : "text-left"}>
                    {runningJob ? (
                      <Badge className="border-blue-500/20 bg-blue-500/10 text-blue-600">
                        <Play className={cn("h-3 w-3", isRTL ? "ml-1" : "mr-1")} />
                        Running
                      </Badge>
                    ) : pipeline.is_published ? (
                      <Badge className="border-green-500/20 bg-green-500/10 text-green-600">
                        <CheckCircle2 className={cn("h-3 w-3", isRTL ? "ml-1" : "mr-1")} />
                        Published
                      </Badge>
                    ) : (
                      <Badge variant="secondary">
                        <Edit className={cn("h-3 w-3", isRTL ? "ml-1" : "mr-1")} />
                        Draft
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className={cn("text-sm text-muted-foreground", isRTL ? "text-right" : "text-left")}>
                    {new Date(pipeline.updated_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell className={isRTL ? "text-left" : "text-right"}>
                    <div className={cn("flex", isRTL ? "justify-start" : "justify-end")}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" title="Pipeline Actions">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align={isRTL ? "start" : "end"} className="w-44">
                          {onRun ? (
                            <DropdownMenuItem onClick={() => onRun(pipeline)} disabled={isCompiling}>
                              {isCompiling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                              <span>{isCompiling ? "Preparing Run..." : "Run Pipeline"}</span>
                            </DropdownMenuItem>
                          ) : null}
                          {onViewHistory ? (
                            <DropdownMenuItem onClick={() => onViewHistory(pipeline)}>
                              <History className="h-4 w-4" />
                              <span>View History</span>
                            </DropdownMenuItem>
                          ) : null}
                          {onDuplicate ? (
                            <DropdownMenuItem onClick={() => onDuplicate(pipeline)} disabled={isDuplicating}>
                              {isDuplicating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Copy className="h-4 w-4" />}
                              <span>{isDuplicating ? "Duplicating..." : "Duplicate"}</span>
                            </DropdownMenuItem>
                          ) : null}
                          {onDelete ? (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => onDelete(pipeline.id)}
                                disabled={!canDelete}
                                className="text-destructive focus:text-destructive"
                              >
                                <Trash2 className="h-4 w-4" />
                                <span>Delete Pipeline</span>
                              </DropdownMenuItem>
                            </>
                          ) : null}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
