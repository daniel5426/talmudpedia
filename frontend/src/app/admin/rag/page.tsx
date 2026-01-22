"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { useDirection } from "@/components/direction-provider"
import { useTenant } from "@/contexts/TenantContext"
import { usePermissions } from "@/hooks/usePermission"
import { orgUnitsService, OrgUnit } from "@/services/org-units"
import {
  ragAdminService,
  RAGStats,
  RAGIndex,
  RAGJob,
  JobProgress,
  VisualPipeline,
  PipelineJob
} from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import {
  Database,
  Edit,
  Layers,
  CheckCircle2,
  XCircle,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  Scissors,
  Activity,
  Upload,
  Workflow,
  ExternalLink
} from "lucide-react"
import Link from "next/link"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
function StatCard({
  title,
  value,
  icon: Icon,
  description
}: {
  title: string
  value: number | string
  icon: React.ElementType
  description?: string
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </CardContent>
    </Card>
  )
}

function JobStatusBadge({ status }: { status: string }) {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    completed: "default",
    running: "secondary",
    pending: "outline",
    failed: "destructive",
    cancelled: "outline",
    queued: "outline"
  }

  const icons: Record<string, React.ReactNode> = {
    completed: <CheckCircle2 className={cn("h-3 w-3", isRTL ? "ml-1" : "mr-1")} />,
    running: <Loader2 className={cn("h-3 w-3 animate-spin", isRTL ? "ml-1" : "mr-1")} />,
    failed: <XCircle className={cn("h-3 w-3", isRTL ? "ml-1" : "mr-1")} />,
    queued: <Activity className={cn("h-3 w-3", isRTL ? "ml-1" : "mr-1")} />,
  }

  return (
    <Badge variant={variants[status] || "outline"} className="capitalize">
      {icons[status]}
      {status}
    </Badge>
  )
}

function LiveJobCard({ jobId, onComplete }: { jobId: string; onComplete?: () => void }) {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const [progress, setProgress] = useState<JobProgress | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const ws = ragAdminService.createJobWebSocket(jobId)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === "ping") return
        setProgress(data)

        if (data.status === "completed" || data.status === "failed") {
          onComplete?.()
        }
      } catch (e) {
        console.error("Failed to parse WebSocket message", e)
      }
    }

    ws.onerror = () => {
      ragAdminService.getJobProgress(jobId).then(setProgress).catch(console.error)
    }

    return () => {
      ws.close()
    }
  }, [jobId, onComplete])

  if (!progress) {
    return (
      <Card className={cn("border-l-4 border-l-blue-500", isRTL ? "text-right" : "text-left")}>
        <CardContent className="pt-4">
          <div className={cn("flex items-center gap-2", isRTL ? "flex-row-reverse" : "flex-row")}>
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm">Connecting to job {jobId.slice(0, 8)}...</span>
          </div>
        </CardContent>
      </Card>
    )
  }

  const borderColor = {
    completed: "border-l-green-500",
    running: "border-l-blue-500",
    failed: "border-l-red-500",
    pending: "border-l-gray-400",
    queued: "border-l-yellow-500"
  }[progress.status] || "border-l-gray-400"

  return (
    <Card className={cn(`border-l-4 ${borderColor}`, isRTL ? "text-right" : "text-left")}>
      <CardContent className="pt-4 space-y-3">
        <div className={cn("flex items-center justify-between", isRTL ? "flex-row-reverse" : "flex-row")}>
          <div className={cn("flex items-center gap-2", isRTL ? "flex-row-reverse" : "flex-row")}>
            <span className="font-medium text-sm">Job {progress.job_id.slice(0, 8)}</span>
            <JobStatusBadge status={progress.status} />
          </div>
          <Badge variant="outline" className="text-xs">
            {progress.current_stage}
          </Badge>
        </div>

        <Progress value={progress.percent_complete} className="h-2" />

        <div className="grid grid-cols-4 gap-2 text-xs text-muted-foreground">
          <div className={isRTL ? "text-right" : "text-left"}>
            <span className="block font-medium text-foreground">{progress.processed_documents}</span>
            Documents
          </div>
          <div className={isRTL ? "text-right" : "text-left"}>
            <span className="block font-medium text-foreground">{progress.total_chunks}</span>
            Chunks
          </div>
          <div className={isRTL ? "text-right" : "text-left"}>
            <span className="block font-medium text-foreground">{progress.upserted_chunks}</span>
            Upserted
          </div>
          <div className={isRTL ? "text-right" : "text-left"}>
            <span className="block font-medium text-foreground">{progress.failed_chunks}</span>
            Failed
          </div>
        </div>

        {progress.error_message && (
          <p className={cn("text-xs text-destructive", isRTL ? "text-right" : "text-left")}>{progress.error_message}</p>
        )}
      </CardContent>
    </Card>
  )
}

function CreateIndexDialog({ onCreated, tenantSlug, orgUnits }: { onCreated: () => void, tenantSlug?: string, orgUnits: OrgUnit[] }) {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [ownerId, setOwnerId] = useState("")
  const [loading, setLoading] = useState(false)

  const handleCreate = async () => {
    if (!name) return
    setLoading(true)
    try {
      await ragAdminService.createIndex({
        name,
        display_name: displayName || name,
        owner_id: ownerId || undefined
      }, tenantSlug)
      setOpen(false)
      setName("")
      setDisplayName("")
      setOwnerId("")
      onCreated()
    } catch (error) {
      console.error("Failed to create index", error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
          New Index
        </Button>
      </DialogTrigger>
      <DialogContent dir={direction}>
        <DialogHeader>
          <DialogTitle className={isRTL ? "text-right" : "text-left"}>Create Vector Index</DialogTitle>
          <DialogDescription className={isRTL ? "text-right" : "text-left"}>
            Create a new vector index for storing document embeddings.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="name" className={isRTL ? "text-right block" : "text-left block"}>Index Name</Label>
            <Input
              id="name"
              placeholder="my-index"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={isRTL ? "text-right" : "text-left"}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="displayName" className={isRTL ? "text-right block" : "text-left block"}>Display Name (optional)</Label>
            <Input
              id="displayName"
              placeholder="My Index"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className={isRTL ? "text-right" : "text-left"}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ownerId" className={isRTL ? "text-right block" : "text-left block"}>Owner Unit (optional)</Label>
            <select
              id="ownerId"
              className={cn("w-full h-10 px-3 rounded-md border border-input bg-background text-sm", isRTL ? "text-right" : "text-left")}
              value={ownerId}
              onChange={(e) => setOwnerId(e.target.value)}
              dir={direction}
            >
              <option value="">Select Owner Unit...</option>
              {orgUnits.map(u => <option key={u.id} value={u.id}>{u.name} ({u.type})</option>)}
            </select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleCreate} disabled={!name || loading}>
            {loading && <Loader2 className={cn("h-4 w-4 animate-spin", isRTL ? "ml-2" : "mr-2")} />}
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ChunkPreviewDialog() {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const [open, setOpen] = useState(false)
  const [text, setText] = useState("")
  const [chunkSize, setChunkSize] = useState(650)
  const [chunkOverlap, setChunkOverlap] = useState(50)
  const [chunks, setChunks] = useState<Array<{ id: string; text: string; token_count: number }>>([])
  const [loading, setLoading] = useState(false)

  const handlePreview = async () => {
    if (!text) return
    setLoading(true)
    try {
      const result = await ragAdminService.chunkPreview({
        text,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap
      })
      setChunks(result.chunks)
    } catch (error) {
      console.error("Failed to preview chunks", error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Scissors className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
          Chunk Preview
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-hidden flex flex-col" dir={direction}>
        <DialogHeader>
          <DialogTitle className={isRTL ? "text-right" : "text-left"}>Chunking Preview</DialogTitle>
          <DialogDescription className={isRTL ? "text-right" : "text-left"}>
            Test how your text will be split into chunks with the current settings.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4 flex-1 overflow-auto">
          <div className="space-y-2">
            <Label htmlFor="previewText" className={isRTL ? "text-right block" : "text-left block"}>Text to chunk</Label>
            <Textarea
              id="previewText"
              placeholder="Paste your text here..."
              value={text}
              onChange={(e) => setText(e.target.value)}
              className={cn("min-h-[100px]", isRTL ? "text-right" : "text-left")}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="chunkSize" className={isRTL ? "text-right block" : "text-left block"}>Chunk Size (tokens)</Label>
              <Input
                id="chunkSize"
                type="number"
                value={chunkSize}
                onChange={(e) => setChunkSize(Number(e.target.value))}
                className={isRTL ? "text-right" : "text-left"}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="chunkOverlap" className={isRTL ? "text-right block" : "text-left block"}>Chunk Overlap (tokens)</Label>
              <Input
                id="chunkOverlap"
                type="number"
                value={chunkOverlap}
                onChange={(e) => setChunkOverlap(Number(e.target.value))}
                className={isRTL ? "text-right" : "text-left"}
              />
            </div>
          </div>
          <Button onClick={handlePreview} disabled={!text || loading}>
            {loading && <Loader2 className={cn("h-4 w-4 animate-spin", isRTL ? "ml-2" : "mr-2")} />}
            Preview Chunks
          </Button>
          {chunks.length > 0 && (
            <div className="space-y-2">
              <Label className={isRTL ? "text-right block" : "text-left block"}>Result: {chunks.length} chunks</Label>
              <div className="space-y-2 max-h-[300px] overflow-auto">
                {chunks.map((chunk, i) => (
                  <Card key={chunk.id}>
                    <CardHeader className="py-2 px-3">
                      <div className={cn("flex justify-between items-center", isRTL ? "flex-row-reverse" : "flex-row")}>
                        <CardTitle className="text-sm">Chunk {i + 1}</CardTitle>
                        <Badge variant="outline">{chunk.token_count} tokens</Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="py-2 px-3">
                      <p className={cn("text-sm text-muted-foreground whitespace-pre-wrap", isRTL ? "text-right" : "text-left")}>
                        {chunk.text.slice(0, 200)}
                        {chunk.text.length > 200 && "..."}
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default function RAGAdminPage() {
  const { currentTenant } = useTenant()
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const { canDelete } = usePermissions()
  const [stats, setStats] = useState<RAGStats | null>(null)
  const [indices, setIndices] = useState<RAGIndex[]>([])
  const [jobs, setJobs] = useState<RAGJob[]>([])
  const [pipelines, setPipelines] = useState<VisualPipeline[]>([])
  const [pipelineJobs, setPipelineJobs] = useState<PipelineJob[]>([])
  const [operatorCatalog, setOperatorCatalog] = useState<any>(null)
  const [orgUnits, setOrgUnits] = useState<OrgUnit[]>([])
  const [loading, setLoading] = useState(true)
  const [activeJobIds, setActiveJobIds] = useState<string[]>([])

  const fetchData = useCallback(async () => {
    try {
      const [statsData, indicesData, jobsData, unitsData, pipelinesData, pipelineJobsData, catalogData] = await Promise.all([
        ragAdminService.getStats(currentTenant?.slug),
        ragAdminService.listIndices(currentTenant?.slug),
        ragAdminService.listJobs(1, 10, undefined, currentTenant?.slug),
        currentTenant ? orgUnitsService.listOrgUnits(currentTenant.slug) : Promise.resolve([]),
        ragAdminService.listVisualPipelines(currentTenant?.slug),
        ragAdminService.listPipelineJobs(undefined, currentTenant?.slug),
        ragAdminService.getOperatorCatalog()
      ])
      setStats(statsData)
      setIndices(indicesData.indices)
      setJobs(jobsData.items)
      setOrgUnits(unitsData)
      setPipelines(pipelinesData.pipelines)
      setPipelineJobs(pipelineJobsData.jobs)
      setOperatorCatalog(catalogData)
    } catch (error) {
      console.error("Failed to fetch RAG data", error)
    } finally {
      setLoading(false)
    }
  }, [currentTenant])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleJobComplete = useCallback(() => {
    fetchData()
  }, [fetchData])

  const handleDeleteIndex = async (name: string) => {
    if (!confirm(`Are you sure you want to delete index "${name}"? This cannot be undone.`)) return
    try {
      await ragAdminService.deleteIndex(name, currentTenant?.slug)
      fetchData()
    } catch (error) {
      console.error("Failed to delete index", error)
    }
  }

  return (
    <div className="flex flex-col h-full w-full" dir={direction}>
      <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb items={[
              { label: "Dashboard", href: "/admin/dashboard" },
              { label: "RAG Management", href: "/admin/rag", active: true },
            ]} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href="/admin/pipelines">
              <Workflow className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
              Pipeline Builder
            </Link>
          </Button>
          <Button size="sm" asChild>
            <Link href="/admin/pipelines?mode=create">
              <Plus className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
              New Pipeline
            </Link>
          </Button>
        </div>
      </header>
      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
            <Skeleton className="h-[400px] w-full" />
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
              <StatCard
                title="Vector Indices"
                value={stats?.live_indices || 0}
                icon={Database}
                description={currentTenant ? `Indices in ${currentTenant.name}` : "Active vector indices"}
              />
              <StatCard
                title="Total Chunks"
                value={stats?.total_chunks?.toLocaleString() || 0}
                icon={Layers}
                description="Embedded document chunks"
              />
              <StatCard
                title="Pipelines"
                value={stats?.total_pipelines || 0}
                icon={Workflow}
                description={`${stats?.compiled_pipelines || 0} compiled blueprints`}
              />
              <StatCard
                title="Completed Jobs"
                value={stats?.completed_jobs || 0}
                icon={CheckCircle2}
                description="Successful ingestion jobs"
              />
              <StatCard
                title="Failed Jobs"
                value={stats?.failed_jobs || 0}
                icon={XCircle}
                description="Jobs with errors"
              />
            </div>

            <Tabs defaultValue="indices" className="space-y-4" dir={direction}>
              <TabsList>
                <TabsTrigger value="indices">Indices</TabsTrigger>
                <TabsTrigger value="pipelines">Pipelines</TabsTrigger>
                <TabsTrigger value="jobs">Jobs</TabsTrigger>
                <TabsTrigger value="capabilities">Capabilities</TabsTrigger>
              </TabsList>

              <TabsContent value="indices" className="space-y-4">
                <div className="flex justify-between items-center">
                  <h2 className="text-lg font-semibold">Vector Indices</h2>
                  <div className="flex gap-2">
                    <ChunkPreviewDialog />
                    <Button variant="outline" size="sm" onClick={fetchData}>
                      <RefreshCw className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                      Refresh
                    </Button>
                    <CreateIndexDialog onCreated={fetchData} tenantSlug={currentTenant?.slug} orgUnits={orgUnits} />
                  </div>
                </div>
                <Card>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Name</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Dimension</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Vectors</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Owner Unit</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Status</TableHead>
                        <TableHead className={isRTL ? "text-left" : "text-right"}>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {indices.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={6} className="text-center text-muted-foreground">
                            No indices found. Create one to get started.
                          </TableCell>
                        </TableRow>
                      ) : (
                        indices.map((index) => (
                          <TableRow key={index.name}>
                            <TableCell className={cn("font-medium", isRTL ? "text-right" : "text-left")}>{index.display_name}</TableCell>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>{index.dimension}</TableCell>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>{index.total_vectors.toLocaleString()}</TableCell>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>
                              <div className="flex flex-col">
                                <span className="text-xs font-medium">
                                  {orgUnits.find(u => u.id === index.owner_id)?.name || "Default"}
                                </span>
                                <span className="text-[10px] opacity-50 uppercase">
                                  {orgUnits.find(u => u.id === index.owner_id)?.type || "Tenant"}
                                </span>
                              </div>
                            </TableCell>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>
                              <Badge variant={index.status === "active" ? "default" : "secondary"}>
                                {index.status}
                              </Badge>
                            </TableCell>
                            <TableCell className={isRTL ? "text-left" : "text-right"}>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => handleDeleteIndex(index.name)}
                                disabled={!canDelete("index")}
                              >
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </Card>
              </TabsContent>

              <TabsContent value="pipelines" className="space-y-4">
                <div className="flex justify-between items-center">
                  <h2 className="text-lg font-semibold">Visual Pipelines</h2>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={fetchData}>
                      <RefreshCw className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                      Refresh
                    </Button>
                    <Button size="sm" asChild>
                      <Link href="/admin/pipelines?mode=create">
                        <Plus className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                        Create Blueprint
                      </Link>
                    </Button>
                  </div>
                </div>
                <Card>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Name</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Version</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Status</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Updated</TableHead>
                        <TableHead className={isRTL ? "text-left" : "text-right"}>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {pipelines.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={5} className="text-center text-muted-foreground">
                            No pipelines found. Create one in the Pipeline Builder.
                          </TableCell>
                        </TableRow>
                      ) : (
                        pipelines.map((pipeline) => (
                          <TableRow key={pipeline.id}>
                            <TableCell className={cn("font-medium", isRTL ? "text-right" : "text-left")}>
                              <div className="flex flex-col">
                                <span>{pipeline.name}</span>
                                {pipeline.description && <span className="text-xs text-muted-foreground font-normal">{pipeline.description}</span>}
                              </div>
                            </TableCell>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>
                              <Badge variant="outline">v{pipeline.version}</Badge>
                            </TableCell>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>
                              {pipeline.is_published ? (
                                <Badge className="bg-green-500/10 text-green-600 border-green-500/20">Published</Badge>
                              ) : (
                                <Badge variant="secondary">Draft</Badge>
                              )}
                            </TableCell>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>
                              {new Date(pipeline.updated_at).toLocaleDateString()}
                            </TableCell>
                            <TableCell className={isRTL ? "text-left" : "text-right"}>
                              <div className="flex justify-end gap-2">
                                <Button variant="ghost" size="sm" asChild title="Edit Pipeline">
                                  <Link href={`/admin/pipelines?mode=edit&id=${pipeline.id}`}>
                                    <Edit className="h-4 w-4" />
                                  </Link>
                                </Button>
                                <Button variant="ghost" size="sm" asChild title="Open in Builder">
                                  <Link href={`/admin/pipelines?id=${pipeline.id}`}>
                                    <ExternalLink className="h-4 w-4" />
                                  </Link>
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </Card>
              </TabsContent>

              <TabsContent value="jobs" className="space-y-4">
                <div className="flex justify-between items-center">
                  <h2 className="text-lg font-semibold">Job History</h2>
                  <Button variant="outline" size="sm" onClick={fetchData}>
                    <RefreshCw className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                    Refresh
                  </Button>
                </div>

                {activeJobIds.length > 0 && (
                  <div className="space-y-3">
                    <h3 className={cn("text-sm font-medium flex items-center gap-2", isRTL ? "flex-row-reverse" : "flex-row")}>
                      <Activity className="h-4 w-4 text-blue-500" />
                      Active Ingestion Jobs ({activeJobIds.length})
                    </h3>
                    <div className="grid gap-3 md:grid-cols-2">
                      {activeJobIds.map((jobId) => (
                        <LiveJobCard
                          key={jobId}
                          jobId={jobId}
                          onComplete={() => {
                            setActiveJobIds(prev => prev.filter(id => id !== jobId))
                            handleJobComplete()
                          }}
                        />
                      ))}
                    </div>
                  </div>
                )}

                <div className="grid gap-6">
                  <Card>
                    <CardHeader className={cn("pb-2", isRTL ? "text-right" : "text-left")}>
                      <CardTitle className="text-base flex items-center gap-2">
                        <Workflow className="h-4 w-4" />
                        Pipeline Executions
                      </CardTitle>
                      <CardDescription>Recently triggered pipeline jobs</CardDescription>
                    </CardHeader>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Pipeline</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Triggered By</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Status</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Started</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Duration</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {pipelineJobs.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={5} className="text-center text-muted-foreground py-4">
                              No pipeline executions found.
                            </TableCell>
                          </TableRow>
                        ) : (
                          pipelineJobs.map((job) => (
                            <TableRow key={job.id}>
                              <TableCell className={cn("font-medium", isRTL ? "text-right" : "text-left")}>
                                <div className="flex flex-col">
                                  <span className="text-xs font-mono opacity-50">{job.executable_pipeline_id.slice(-8)}</span>
                                  <span>{pipelines.find(p => p.id === job.executable_pipeline_id)?.name || "Pipeline"}</span>
                                </div>
                              </TableCell>
                              <TableCell className={isRTL ? "text-right" : "text-left"}>{job.triggered_by}</TableCell>
                              <TableCell className={isRTL ? "text-right" : "text-left"}>
                                <JobStatusBadge status={job.status} />
                              </TableCell>
                              <TableCell className={isRTL ? "text-right" : "text-left"}>
                                {new Date(job.created_at).toLocaleString()}
                              </TableCell>
                              <TableCell className={isRTL ? "text-right" : "text-left"}>
                                {job.finished_at && job.started_at ?
                                  `${Math.round((new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000)}s`
                                  : "-"}
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </Card>

                  <Card>
                    <CardHeader className={cn("pb-2", isRTL ? "text-right" : "text-left")}>
                      <CardTitle className="text-base flex items-center gap-2">
                        <Layers className="h-4 w-4" />
                        Legacy Ingestion Jobs
                      </CardTitle>
                      <CardDescription>Direct API and manual ingestion history</CardDescription>
                    </CardHeader>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Index</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Source</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Status</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Progress</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Created</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {jobs.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={5} className="text-center text-muted-foreground py-4">
                              No jobs found.
                            </TableCell>
                          </TableRow>
                        ) : (
                          jobs.map((job) => (
                            <TableRow key={job.id}>
                              <TableCell className={cn("font-medium", isRTL ? "text-right" : "text-left")}>{job.index_name}</TableCell>
                              <TableCell className={isRTL ? "text-right" : "text-left"}>{job.source_type}</TableCell>
                              <TableCell className={isRTL ? "text-right" : "text-left"}>
                                <JobStatusBadge status={job.status} />
                              </TableCell>
                              <TableCell className={isRTL ? "text-right" : "text-left"}>
                                {job.upserted_chunks}/{job.total_chunks} chunks
                              </TableCell>
                              <TableCell className={isRTL ? "text-right" : "text-left"}>
                                {new Date(job.created_at).toLocaleDateString()}
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </Card>
                </div>
              </TabsContent>

              <TabsContent value="capabilities" className="space-y-4">
                <div className="grid gap-6">
                  {operatorCatalog && (
                    <>
                      <div className="grid gap-4 md:grid-cols-2">
                        <Card>
                          <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2">
                              <Upload className="h-4 w-4" />
                              Source Operators
                            </CardTitle>
                            <CardDescription>Supported data ingestion sources</CardDescription>
                          </CardHeader>
                          <CardContent>
                            <div className="grid gap-2">
                              {operatorCatalog.source.map((op: any) => (
                                <div key={op.operator_id} className="p-3 border rounded-lg flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{op.display_name}</div>
                                    <div className="text-xs text-muted-foreground">ID: {op.operator_id} | Output: {op.output_type}</div>
                                  </div>
                                  <Badge variant="outline">Source</Badge>
                                </div>
                              ))}
                            </div>
                          </CardContent>
                        </Card>

                        <Card>
                          <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2">
                              <Scissors className="h-4 w-4" />
                              Transform Operators
                            </CardTitle>
                            <CardDescription>Document chunking and processing strategies</CardDescription>
                          </CardHeader>
                          <CardContent>
                            <div className="grid gap-2">
                              {operatorCatalog.transform.map((op: any) => (
                                <div key={op.operator_id} className="p-3 border rounded-lg flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{op.display_name}</div>
                                    <div className="text-xs text-muted-foreground">Input: {op.input_type} | Output: {op.output_type}</div>
                                  </div>
                                  <Badge variant="outline">Transform</Badge>
                                </div>
                              ))}
                            </div>
                          </CardContent>
                        </Card>

                        <Card>
                          <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2">
                              <Layers className="h-4 w-4" />
                              Embedding Providers
                            </CardTitle>
                            <CardDescription>Vector generation models and services</CardDescription>
                          </CardHeader>
                          <CardContent>
                            <div className="grid gap-2">
                              {operatorCatalog.embedding.map((op: any) => (
                                <div key={op.operator_id} className="p-3 border rounded-lg flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{op.display_name}</div>
                                    <div className="text-xs text-muted-foreground">Dimensions: {op.dimension || "Dynamic"}</div>
                                  </div>
                                  <Badge variant="outline">Embedder</Badge>
                                </div>
                              ))}
                            </div>
                          </CardContent>
                        </Card>

                        <Card>
                          <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2">
                              <Database className="h-4 w-4" />
                              Storage Providers
                            </CardTitle>
                            <CardDescription>Vector database integrations</CardDescription>
                          </CardHeader>
                          <CardContent>
                            <div className="grid gap-2">
                              {operatorCatalog.storage.map((op: any) => (
                                <div key={op.operator_id} className="p-3 border rounded-lg flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{op.display_name}</div>
                                    <div className="text-xs text-muted-foreground">Target: {op.input_type}</div>
                                  </div>
                                  <Badge variant="outline">Store</Badge>
                                </div>
                              ))}
                            </div>
                          </CardContent>
                        </Card>
                      </div>

                      <Card>
                        <CardHeader>
                          <CardTitle className="text-base">System Compatibility</CardTitle>
                          <CardDescription>Current platform supported file types</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <div className="flex flex-wrap gap-2">
                            {[".txt", ".md", ".json", ".csv", ".html", ".pdf"].map((ext) => (
                              <Badge key={ext} variant="outline" className="bg-blue-500/5 text-blue-600 border-blue-500/20">
                                {ext}
                              </Badge>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    </>
                  )}
                </div>
              </TabsContent>
            </Tabs>
          </div>
        )}
      </div>
    </div>
  )
}
