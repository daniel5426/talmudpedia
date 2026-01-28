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
import { Progress } from "@/components/ui/progress"
import {
  Edit,
  ExternalLink,
  History,
  Trash2,
  CheckCircle2,
  Play,
  Loader2,
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
  canDelete?: boolean
  showDescription?: boolean
  runningJobs?: Record<string, RunningJobStatus>
  runningCompileId?: string | null
}

export function PipelinesTable({
  pipelines,
  onDelete,
  onViewHistory,
  onRun,
  canDelete = true,
  showDescription = true,
  runningJobs,
  runningCompileId,
}: PipelinesTableProps) {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"

  if (pipelines.length === 0) {
    return (
      <div className="text-center text-muted-foreground py-8">
        No pipelines found. Create one to get started.
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className={isRTL ? "text-right" : "text-left"}>Name</TableHead>
          {showDescription && <TableHead className={isRTL ? "text-right" : "text-left"}>Description</TableHead>}
          <TableHead className={isRTL ? "text-right" : "text-left"}>Version</TableHead>
          <TableHead className={isRTL ? "text-right" : "text-left"}>Status</TableHead>
          <TableHead className={isRTL ? "text-right" : "text-left"}>Updated</TableHead>
          <TableHead className={isRTL ? "text-left" : "text-right"}>Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {pipelines.map((pipeline) => {
          const runningJob = runningJobs?.[pipeline.id]
          const isCompiling = runningCompileId === pipeline.id
          const pipelineHref = runningJob?.jobId
            ? `/admin/pipelines/${pipeline.id}?jobId=${runningJob.jobId}`
            : `/admin/pipelines/${pipeline.id}`
          return (
          <TableRow key={pipeline.id}>
            <TableCell className={cn("font-medium", isRTL ? "text-right" : "text-left")}>
              <div className="flex flex-col">
                <Link href={pipelineHref} className="hover:underline">
                  {pipeline.name}
                </Link>
                {!showDescription && pipeline.description && (
                  <span className="text-xs text-muted-foreground font-normal">
                    {pipeline.description}
                  </span>
                )}
                {runningJob && (
                  <div className="mt-2">
                    <Progress value={runningJob.progress ?? 5} className="h-1" />
                  </div>
                )}
              </div>
            </TableCell>
            {showDescription && (
              <TableCell className={cn("text-muted-foreground max-w-[200px] truncate", isRTL ? "text-right" : "text-left")}>
                {pipeline.description || "-"}
              </TableCell>
            )}
            <TableCell className={isRTL ? "text-right" : "text-left"}>
              <Badge variant="outline">v{pipeline.version}</Badge>
            </TableCell>
            <TableCell className={isRTL ? "text-right" : "text-left"}>
              {runningJob ? (
                <Badge className="bg-blue-500/10 text-blue-600 border-blue-500/20">
                  <Play className={cn("h-3 w-3", isRTL ? "ml-1" : "mr-1")} />
                  Running
                </Badge>
              ) : pipeline.is_published ? (
                <Badge className="bg-green-500/10 text-green-600 border-green-500/20">
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
            <TableCell className={isRTL ? "text-right" : "text-left"}>
              {new Date(pipeline.updated_at).toLocaleDateString()}
            </TableCell>
            <TableCell className={isRTL ? "text-left" : "text-right"}>
              <div className={cn("flex gap-1", isRTL ? "justify-start" : "justify-end")}>
                {onRun && (
                  <Button
                    variant="ghost"
                    size="icon"
                    title={isCompiling ? "Preparing Run" : "Run Pipeline"}
                    onClick={() => onRun(pipeline)}
                    disabled={isCompiling}
                  >
                    {isCompiling ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Play className="h-4 w-4" />
                    )}
                  </Button>
                )}
                {onViewHistory && (
                  <Button
                    variant="ghost"
                    size="icon"
                    title="View Execution History"
                    onClick={() => onViewHistory(pipeline)}
                  >
                    <History className="h-4 w-4" />
                  </Button>
                )}
                {onDelete && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => onDelete(pipeline.id)}
                    disabled={!canDelete}
                    title="Delete Pipeline"
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                )}
              </div>
            </TableCell>
          </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
