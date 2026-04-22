"use client"

import { useEffect, useState, useCallback } from "react"
import { useDirection } from "@/components/direction-provider"
import { useOrganization } from "@/contexts/OrganizationContext"
import { usePermissions } from "@/hooks/usePermission"
import { organizationUnitsService, OrgUnit } from "@/services/org-units"
import {
  ragAdminService,
  RAGStats,
  RAGIndex,
  VisualPipeline,
  PipelineJob,
} from "@/services"
import type { NodeCatalogItem } from "@/services/graph-authoring"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import {
  Database,
  Layers,
  CheckCircle2,
  XCircle,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  Scissors,
  Upload,
  Workflow,
  History
} from "lucide-react"
import Link from "next/link"
import { PipelinesTable } from "@/components/rag/PipelinesTable"
import { PipelineHistoryDialog } from "@/components/rag/PipelineHistoryDialog"
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
import { PipelineExecutionsTable } from "@/components/rag/PipelineExecutionsTable"
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



function CreateIndexDialog({ onCreated, organizationId, orgUnits }: { onCreated: () => void, organizationId?: string, orgUnits: OrgUnit[] }) {
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
      }, organizationId)
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
  const { currentOrganization } = useOrganization()
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const { canDelete } = usePermissions()
  const [stats, setStats] = useState<RAGStats | null>(null)
  const [indices, setIndices] = useState<RAGIndex[]>([])
  const [pipelines, setPipelines] = useState<VisualPipeline[]>([])
  const [pipelineJobs, setPipelineJobs] = useState<PipelineJob[]>([])
  const [operatorCatalog, setOperatorCatalog] = useState<NodeCatalogItem[] | null>(null)
  const [orgUnits, setOrgUnits] = useState<OrgUnit[]>([])
  const [loading, setLoading] = useState(true)

  const [selectedPipelineHistory, setSelectedPipelineHistory] = useState<VisualPipeline | null>(null)
  const [pipelineHistoryJobs, setPipelineHistoryJobs] = useState<PipelineJob[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const [statsData, indicesData, unitsData, pipelinesData, pipelineJobsData, catalogData] = await Promise.all([
        ragAdminService.getStats(currentOrganization?.id),
        ragAdminService.listIndices(currentOrganization?.id),
        currentOrganization ? organizationUnitsService.listOrgUnits(currentOrganization.id) : Promise.resolve([]),
        ragAdminService.listVisualPipelines(currentOrganization?.id, { view: "summary", limit: 100 }),
        ragAdminService.listPipelineJobs(undefined, currentOrganization?.id),
        ragAdminService.getOperatorCatalog()
      ])
      setStats(statsData)
      setIndices(indicesData.indices)
      setOrgUnits(unitsData)
      setPipelines(pipelinesData.items)
      setPipelineJobs(pipelineJobsData.jobs)

      setOperatorCatalog(catalogData.operators || [])
    } catch (error) {
      console.error("Failed to fetch RAG data", error)
    } finally {
      setLoading(false)
    }
  }, [currentOrganization])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleDeleteIndex = async (name: string) => {
    if (!confirm(`Are you sure you want to delete index "${name}"? This cannot be undone.`)) return
    try {
      await ragAdminService.deleteIndex(name, currentOrganization?.id)
      fetchData()
    } catch (error) {
      console.error("Failed to delete index", error)
    }
  }

  const handleViewHistory = async (pipeline: VisualPipeline) => {
    setSelectedPipelineHistory(pipeline)
    setPipelineHistoryJobs([]) // Clear previous jobs to avoid showing stale state
    setLoadingHistory(true)
    try {
      const res = await ragAdminService.listPipelineJobs({
        visual_pipeline_id: pipeline.id,
        limit: 50
      }, currentOrganization?.id)
      setPipelineHistoryJobs(res.jobs)
    } catch (error) {
      console.error("Failed to fetch history", error)
    } finally {
      setLoadingHistory(false)
    }
  }

  return (
    <div className="flex flex-col h-full w-full" dir={direction}>
      <AdminPageHeader>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb items={[
              { label: "RAG Management", href: "/admin/rag", active: true },
            ]} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href="/admin/rag/knowledge-stores">
              <Database className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
              Knowledge Stores
            </Link>
          </Button>
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
      </AdminPageHeader>
      <div className="flex-1 overflow-auto p-4" data-admin-page-scroll>
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
                description={currentOrganization ? `Indices in ${currentOrganization.name}` : "Active vector indices"}
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
                    <CreateIndexDialog onCreated={fetchData} organizationId={currentOrganization?.id} orgUnits={orgUnits} />
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
                                  {orgUnits.find(u => u.id === index.owner_id)?.type || "Organization"}
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
                                disabled={!canDelete("pipelines")}
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
                  <PipelinesTable
                    pipelines={pipelines}
                    onViewHistory={handleViewHistory}
                    showDescription={false}
                  />
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
                              {operatorCatalog.filter((op) => op.category === "source").map((op) => (
                                <div key={op.type} className="p-3 border rounded-lg flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{op.title}</div>
                                    <div className="text-xs text-muted-foreground">ID: {op.type} | Output: {op.output_type}</div>
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
                                ...operatorCatalog.filter((op) => ["transform", "normalization", "enrichment", "chunking", "reranking", "custom"].includes(op.category)),
                              ].map((op) => (
                                <div key={op.type} className="p-3 border rounded-lg flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{op.title}</div>
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
                              {operatorCatalog.filter((op) => op.category === "embedding").map((op) => (
                                <div key={op.type} className="p-3 border rounded-lg flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{op.title}</div>
                                    <div className="text-xs text-muted-foreground">Output: {op.output_type}</div>
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
                              {operatorCatalog.filter((op) => op.category === "storage").map((op) => (
                                <div key={op.type} className="p-3 border rounded-lg flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{op.title}</div>
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

      <PipelineHistoryDialog
        pipeline={selectedPipelineHistory}
        jobs={pipelineHistoryJobs}
        isLoading={loadingHistory}
        allPipelines={pipelines}
        onClose={() => setSelectedPipelineHistory(null)}
      />
    </div >
  )
}
