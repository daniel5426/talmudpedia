"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useTenant } from "@/contexts/TenantContext"
import { ragAdminService, VisualPipeline, CompileResult } from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { PipelinesTable } from "@/components/rag/PipelinesTable"
import { PipelineHistoryDialog } from "@/components/rag/PipelineHistoryDialog"
import { usePermissions } from "@/hooks/usePermission"
import {
  Plus,
  RefreshCw,
  Loader2,
} from "lucide-react"
import { PipelineJob } from "@/services"
import { RunPipelineDialog } from "@/components/pipeline/RunPipelineDialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu"
import {
  Database,
  Search,
  ChevronDown,
} from "lucide-react"

export default function PipelinesPage() {
  const { currentTenant } = useTenant()
  const router = useRouter()
  const { canDelete } = usePermissions()

  const [loading, setLoading] = useState(true)
  const [pipelines, setPipelines] = useState<VisualPipeline[]>([])

  const [selectedPipelineHistory, setSelectedPipelineHistory] = useState<VisualPipeline | null>(null)
  const [pipelineHistoryJobs, setPipelineHistoryJobs] = useState<PipelineJob[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const [runTarget, setRunTarget] = useState<VisualPipeline | null>(null)
  const [runCompileResult, setRunCompileResult] = useState<CompileResult | null>(null)
  const [isRunDialogOpen, setIsRunDialogOpen] = useState(false)
  const [runningJobs, setRunningJobs] = useState<Record<string, { jobId: string; status: string; progress?: number }>>({})
  const [runningCompileId, setRunningCompileId] = useState<string | null>(null)

  const [isCreating, setIsCreating] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const pipelinesRes = await ragAdminService.listVisualPipelines(currentTenant?.slug)
      setPipelines(pipelinesRes.pipelines)
    } catch (error) {
      console.error("Failed to fetch pipelines data", error)
    } finally {
      setLoading(false)
    }
  }, [currentTenant?.slug])

  const handleViewHistory = async (pipeline: VisualPipeline) => {
    setSelectedPipelineHistory(pipeline)
    setPipelineHistoryJobs([])
    setLoadingHistory(true)
    try {
      const res = await ragAdminService.listPipelineJobs({
        visual_pipeline_id: pipeline.id,
        limit: 50
      }, currentTenant?.slug)
      setPipelineHistoryJobs(res.jobs)
    } catch (error) {
      console.error("Failed to fetch history", error)
    } finally {
      setLoadingHistory(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleDelete = async (pipelineId: string) => {
    if (!confirm("Are you sure you want to delete this pipeline?")) return
    try {
      await ragAdminService.deleteVisualPipeline(pipelineId, currentTenant?.slug)
      fetchData()
    } catch (error) {
      console.error("Failed to delete pipeline", error)
    }
  }

  const handleRunPipeline = async (pipeline: VisualPipeline) => {
    if (!currentTenant) return
    setRunTarget(pipeline)
    setRunCompileResult(null)
    setRunningCompileId(pipeline.id)
    try {
      const result = await ragAdminService.compilePipeline(pipeline.id, currentTenant.slug)
      setRunCompileResult(result)
      if (result.success) {
        setIsRunDialogOpen(true)
      } else {
        alert("Pipeline compilation failed. Please fix errors in the builder.")
      }
    } catch (error) {
      console.error("Failed to compile pipeline", error)
      alert("Failed to compile pipeline")
    } finally {
      setRunningCompileId(null)
    }
  }

  const handleQuickCreate = async (type: "ingestion" | "retrieval") => {
    if (!currentTenant) return
    setIsCreating(true)
    try {
      const res = await ragAdminService.createVisualPipeline({
        name: `New ${type.charAt(0).toUpperCase() + type.slice(1)} Pipeline`,
        pipeline_type: type,
        nodes: [],
        edges: [],
      }, currentTenant.slug)
      router.push(`/admin/pipelines/${res.id}`)
    } catch (error) {
      console.error("Failed to create pipeline", error)
      alert("Failed to create pipeline")
    } finally {
      setIsCreating(false)
    }
  }

  const handleSubmitRun = async (inputParams: Record<string, Record<string, unknown>>) => {
    if (!runTarget || !runCompileResult?.executable_pipeline_id) return
    try {
      const res = await ragAdminService.createPipelineJob({
        executable_pipeline_id: runCompileResult.executable_pipeline_id,
        input_params: inputParams,
      }, currentTenant?.slug)
      setRunningJobs((prev) => ({
        ...prev,
        [runTarget.id]: {
          jobId: res.job_id,
          status: "running",
          progress: 5,
        },
      }))
    } catch (error) {
      console.error("Failed to run pipeline", error)
      alert("Failed to start pipeline job")
    }
  }

  useEffect(() => {
    if (!currentTenant?.slug) return
    const jobEntries = Object.entries(runningJobs)
    if (jobEntries.length === 0) return

    let isMounted = true
    const poll = async () => {
      await Promise.all(jobEntries.map(async ([pipelineId, job]) => {
        try {
          const [jobRes, stepsRes] = await Promise.all([
            ragAdminService.getPipelineJob(job.jobId, currentTenant.slug),
            ragAdminService.getJobSteps(job.jobId, currentTenant.slug),
          ])
          if (!isMounted) return
          const terminalStatuses = ["completed", "failed", "cancelled"]
          if (terminalStatuses.includes(jobRes.status)) {
            setRunningJobs((prev) => {
              const next = { ...prev }
              delete next[pipelineId]
              return next
            })
            return
          }
          const steps = stepsRes.steps || []
          const total = steps.length
          const done = steps.filter((step) => ["completed", "failed", "skipped"].includes(step.status)).length
          const progress = total > 0 ? Math.min(100, Math.max(5, Math.round((done / total) * 100))) : 5
          setRunningJobs((prev) => ({
            ...prev,
            [pipelineId]: {
              jobId: job.jobId,
              status: jobRes.status,
              progress,
            },
          }))
        } catch (error) {
          console.error("Failed to poll pipeline job", error)
        }
      }))
    }

    poll()
    const interval = setInterval(poll, 2000)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [runningJobs, currentTenant?.slug])

  return (
    <div className="flex flex-col h-full w-full">
      <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <CustomBreadcrumb
            items={[
              { label: "RAG Management", href: "/admin/rag" },
              { label: "Pipelines", active: true },
            ]}
          />
        </div>
      </header>
      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <div className="space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-[400px] w-full" />
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-lg font-semibold">Visual Pipelines</h2>
                <p className="text-sm text-muted-foreground">
                  Drag-and-drop RAG pipeline configurations
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={fetchData}>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Refresh
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button size="sm" disabled={isCreating}>
                      {isCreating ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Plus className="h-4 w-4 mr-2" />
                      )}
                      New Pipeline
                      <ChevronDown className="h-4 w-4 ml-1 opacity-50" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <DropdownMenuLabel>Choose Pipeline Type</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="flex flex-col items-start gap-1 py-3 cursor-pointer"
                      onClick={() => handleQuickCreate("ingestion")}
                    >
                      <div className="flex items-center gap-2 font-semibold text-blue-600">
                        <Database className="h-4 w-4" />
                        <span>Ingestion Pipeline</span>
                      </div>
                      <span className="text-[10px] text-muted-foreground leading-tight">
                        Load, chunk, and index data into vector storage.
                      </span>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      className="flex flex-col items-start gap-1 py-3 cursor-pointer"
                      onClick={() => handleQuickCreate("retrieval")}
                    >
                      <div className="flex items-center gap-2 font-semibold text-purple-600">
                        <Search className="h-4 w-4" />
                        <span>Retrieval Pipeline</span>
                      </div>
                      <span className="text-[10px] text-muted-foreground leading-tight">
                        Query, search, and rerank documents.
                      </span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>

            <Card>
              <PipelinesTable
                pipelines={pipelines}
                onDelete={handleDelete}
                onViewHistory={handleViewHistory}
                canDelete={canDelete("pipeline")}
                onRun={handleRunPipeline}
                runningJobs={runningJobs}
                runningCompileId={runningCompileId}
              />
            </Card>
          </div>
        )}
      </div>

      <PipelineHistoryDialog
        pipeline={selectedPipelineHistory}
        jobs={pipelineHistoryJobs}
        isLoading={loadingHistory}
        allPipelines={pipelines}
        onClose={() => setSelectedPipelineHistory(null)}
      />

      <RunPipelineDialog
        open={isRunDialogOpen}
        onOpenChange={setIsRunDialogOpen}
        onRun={handleSubmitRun}
        compileResult={runCompileResult}
      />
    </div>
  )
}
