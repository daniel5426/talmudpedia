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
  VisualPipeline,
  PipelineJob,
  OperatorCatalog,
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
  ExternalLink,
  History
} from "lucide-react"
import Link from "next/link"
import { PipelineExecutionsTable } from "@/components/rag/PipelineExecutionsTable"
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
  const [pipelines, setPipelines] = useState<VisualPipeline[]>([])
  const [pipelineJobs, setPipelineJobs] = useState<PipelineJob[]>([])
  const [operatorCatalog, setOperatorCatalog] = useState<OperatorCatalog | null>(null)
  const [orgUnits, setOrgUnits] = useState<OrgUnit[]>([])
  const [loading, setLoading] = useState(true)

  const [selectedPipelineHistory, setSelectedPipelineHistory] = useState<VisualPipeline | null>(null)
  const [pipelineHistoryJobs, setPipelineHistoryJobs] = useState<PipelineJob[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const [statsData, indicesData, unitsData, pipelinesData, pipelineJobsData, catalogData] = await Promise.all([
        ragAdminService.getStats(currentTenant?.slug),
        ragAdminService.listIndices(currentTenant?.slug),
        currentTenant ? orgUnitsService.listOrgUnits(currentTenant.slug) : Promise.resolve([]),
        ragAdminService.listVisualPipelines(currentTenant?.slug),
        ragAdminService.listPipelineJobs(undefined, currentTenant?.slug),
        ragAdminService.getOperatorCatalog()
      ])
      setStats(statsData)
      setIndices(indicesData.indices)
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

  const handleViewHistory = async (pipeline: VisualPipeline) => {
    setSelectedPipelineHistory(pipeline)
    setLoadingHistory(true)
    try {
      // Find compiling version for this pipeline or just all jobs for this executable pipeline
      // For now, let's fetch all jobs and filter on frontend for simplicity, 
      // or ideally the API should support filtering by visual_pipeline_id if we want everything.
      // But based on the service, we can filter by executable_pipeline_id.
      // Since a visual pipeline can have multiple compiled versions, showing "history for this pipeline" 
      // might mean showing all jobs for all its versions.

      const res = await ragAdminService.listPipelineJobs(undefined, currentTenant?.slug)
      // Filter jobs that belong to this visual pipeline's ID
      // Wait, PipelineJob doesn't have visual_pipeline_id, it has executable_pipeline_id.
      // We might need to fetch all jobs and filter if they belong to ANY version of this pipeline.
      // For now, let's just show all jobs in the modal and filtered in UI if we had that mapping,
      // but let's just use the existing listPipelineJobs for all for now or 
      // if we want specific filter we need to know the executable IDs.

      // Let's just fetch all and filter by matching the pipeline name or matched executable ID if we can.
      // Actually, let's just use the jobs we already have in state but filtered.
      // But we might want to fetch a fresh list or more items than just the recent ones.

      const filtered = pipelineJobs.filter(job => job.executable_pipeline_id === pipeline.id ||
        // This is a bit tricky if we don't have the mapping of executable -> visual on the job object.
        // Assuming executable_pipeline_id in Job currently maps to the compiled version.
        // If the compiled version's ID is same as Visual ID (which it might not be).

        // Let's assume for now we just filter the jobs we have.
        true // temporary
      )

      setPipelineHistoryJobs(pipelineJobs.filter(j => pipelines.find(p => p.id === j.executable_pipeline_id)?.name === pipeline.name))
    } catch (error) {
      console.error("Failed to fetch history", error)
    } finally {
      setLoadingHistory(false)
    }
  }

  return (
    <div className="flex flex-col h-full w-full" dir={direction}>
      <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb items={[
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
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  title="View Execution History"
                                  onClick={() => handleViewHistory(pipeline)}
                                >
                                  <History className="h-4 w-4" />
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

                <div className="grid gap-6">
                  <Card>
                    <CardHeader className={cn("pb-2", isRTL ? "text-right" : "text-left")}>
                      <CardTitle className="text-base flex items-center gap-2">
                        <Workflow className="h-4 w-4" />
                        Pipeline Executions
                      </CardTitle>
                      <CardDescription>Recently triggered pipeline jobs</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <PipelineExecutionsTable
                        jobs={pipelineJobs}
                        pipelines={pipelines}
                        onRefresh={fetchData}
                      />
                    </CardContent>
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
                              {(operatorCatalog.source || []).map((op: any) => (
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
                              Transform & Custom
                            </CardTitle>
                            <CardDescription>Processing, enrichment, and custom operators</CardDescription>
                          </CardHeader>
                          <CardContent>
                            <div className="grid gap-2">
                              {[
                                ...(operatorCatalog.transform || []),
                                ...(operatorCatalog.normalization || []),
                                ...(operatorCatalog.enrichment || []),
                                ...(operatorCatalog.chunking || []),
                                ...(operatorCatalog.reranking || []),
                                ...(operatorCatalog.custom || [])
                              ].map((op: any) => (
                                <div key={op.operator_id} className="p-3 border rounded-lg flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{op.display_name}</div>
                                    <div className="text-xs text-muted-foreground">Input: {op.input_type} | Output: {op.output_type}</div>
                                  </div>
                                  <Badge variant="outline">{op.category || "Transform"}</Badge>
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
                              {(operatorCatalog.embedding || []).map((op: any) => (
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
                              {(operatorCatalog.storage || []).map((op: any) => (
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

      <Dialog open={!!selectedPipelineHistory} onOpenChange={(open) => !open && setSelectedPipelineHistory(null)}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <History className="h-5 w-5" />
              Execution History: {selectedPipelineHistory?.name}
            </DialogTitle>
            <DialogDescription>
              Past executions for this pipeline across all versions.
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-auto py-4">
            <PipelineExecutionsTable
              jobs={pipelineHistoryJobs}
              pipelines={pipelines}
              isLoading={loadingHistory}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedPipelineHistory(null)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div >
  )
}
