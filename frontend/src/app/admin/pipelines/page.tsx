"use client"

import { useEffect, useState, useCallback, useMemo } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useTenant } from "@/contexts/TenantContext"
import { ragAdminService, VisualPipeline, OperatorCatalog, OperatorSpec, CompileResult } from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
  Plus,
  RefreshCw,
  Trash2,
  Edit,
  Play,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  Save,
} from "lucide-react"
import { PipelineBuilder } from "@/components/pipeline"
import { Node, Edge } from "@xyflow/react"
import { cn } from "@/lib/utils"

type ViewMode = "list" | "create" | "edit"

interface PipelineNodeData {
  operator: string
  category: string
  displayName: string
  config: Record<string, unknown>
  inputType: string
  outputType: string
  isConfigured: boolean
  hasErrors: boolean
  // Index signature for ReactFlow compatibility
  [key: string]: unknown
}

export default function PipelinesPage() {
  const { currentTenant } = useTenant()
  const router = useRouter()
  const searchParams = useSearchParams()
  const modeParam = searchParams.get("mode") as ViewMode | null
  const idParam = searchParams.get("id")

  const [viewMode, setViewMode] = useState<ViewMode>("list")
  const [loading, setLoading] = useState(true)
  const [pipelines, setPipelines] = useState<VisualPipeline[]>([])
  const [catalog, setCatalog] = useState<OperatorCatalog | null>(null)
  const [operatorSpecs, setOperatorSpecs] = useState<Record<string, OperatorSpec>>({})
  const [selectedPipeline, setSelectedPipeline] = useState<VisualPipeline | null>(null)

  const [pipelineName, setPipelineName] = useState("")
  const [pipelineDescription, setPipelineDescription] = useState("")
  const [editorNodes, setEditorNodes] = useState<Node<PipelineNodeData>[]>([])
  const [editorEdges, setEditorEdges] = useState<Edge[]>([])

  const [saving, setSaving] = useState(false)
  const [compiling, setCompiling] = useState(false)
  const [compileResult, setCompileResult] = useState<CompileResult | null>(null)
  const [showCompileDialog, setShowCompileDialog] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [pipelinesRes, catalogRes] = await Promise.all([
        ragAdminService.listVisualPipelines(currentTenant?.slug),
        ragAdminService.getOperatorCatalog(),
      ])

      const fetchedPipelines = pipelinesRes.pipelines
      setPipelines(fetchedPipelines)
      setCatalog(catalogRes)

      const specs: Record<string, OperatorSpec> = {}
      const allOperators = [
        ...catalogRes.source,
        ...catalogRes.transform,
        ...catalogRes.embedding,
        ...catalogRes.storage,
      ]
      for (const op of allOperators) {
        try {
          const spec = await ragAdminService.getOperatorSpec(op.operator_id)
          specs[op.operator_id] = spec
        } catch (e) {
          console.error(`Failed to load spec for ${op.operator_id}`, e)
        }
      }
      setOperatorSpecs(specs)
    } catch (error) {
      console.error("Failed to fetch pipelines data", error)
    } finally {
      setLoading(false)
    }
  }, [currentTenant?.slug])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Separate effect to handle view mode based on URL
  useEffect(() => {
    if (loading || !catalog) return

    if (modeParam === "create") {
      handleCreate()
    } else if (modeParam === "edit" && idParam) {
      const pipeline = pipelines.find(p => p.id === idParam)
      if (pipeline) {
        handleEdit(pipeline, catalog)
      }
    } else {
      setViewMode("list")
    }
  }, [modeParam, idParam, loading, catalog, pipelines])

  const handleCreate = () => {
    setPipelineName("")
    setPipelineDescription("")
    setEditorNodes([])
    setEditorEdges([])
    setSelectedPipeline(null)
    setCompileResult(null)
    setViewMode("create")
  }

  const handleEdit = (pipeline: VisualPipeline, currentCatalog?: OperatorCatalog | null) => {
    setSelectedPipeline(pipeline)
    setPipelineName(pipeline.name)
    setPipelineDescription(pipeline.description || "")

    const activeCatalog = currentCatalog || catalog

    const nodes: Node<PipelineNodeData>[] = pipeline.nodes.map((n) => {
      const catalogItem = activeCatalog?.[n.category as keyof OperatorCatalog]?.find(
        (item) => item.operator_id === n.operator
      )
      return {
        id: n.id,
        type: n.category,
        position: n.position,
        data: {
          operator: n.operator,
          category: n.category,
          displayName: catalogItem?.display_name || n.operator,
          config: n.config,
          inputType: catalogItem?.input_type || "none",
          outputType: catalogItem?.output_type || "none",
          isConfigured: true,
          hasErrors: false,
        },
      }
    })

    const edges: Edge[] = pipeline.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
    }))

    setEditorNodes(nodes)
    setEditorEdges(edges)
    setCompileResult(null)
    setViewMode("edit")
  }

  const setViewModeWithUrl = (mode: ViewMode, id?: string) => {
    const params = new URLSearchParams()
    if (mode !== "list") params.set("mode", mode)
    if (id) params.set("id", id)
    const queryString = params.toString()
    router.push(`/admin/pipelines${queryString ? `?${queryString}` : ""}`)
    setViewMode(mode)
  }

  const handleDelete = async (pipelineId: string) => {
    if (!confirm("Are you sure you want to delete this pipeline?")) return
    try {
      await ragAdminService.deleteVisualPipeline(pipelineId, currentTenant?.slug)
      fetchData()
    } catch (error) {
      console.error("Failed to delete pipeline", error)
    }
  }

  const handleSaveGraph = useCallback(
    (nodes: Node<PipelineNodeData>[], edges: Edge[]) => {
      setEditorNodes(nodes)
      setEditorEdges(edges)
    },
    []
  )

  const handleSave = async () => {
    if (!pipelineName.trim()) {
      alert("Please enter a pipeline name")
      return
    }

    setSaving(true)
    try {
      const nodesPayload = editorNodes.map((n) => ({
        id: n.id,
        category: n.data.category,
        operator: n.data.operator,
        position: n.position,
        config: n.data.config,
      }))

      const edgesPayload = editorEdges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
      }))

      if (viewMode === "create") {
        await ragAdminService.createVisualPipeline(
          {
            name: pipelineName,
            description: pipelineDescription,
            nodes: nodesPayload,
            edges: edgesPayload,
          },
          currentTenant?.slug
        )
      } else if (selectedPipeline) {
        await ragAdminService.updateVisualPipeline(
          selectedPipeline.id,
          {
            name: pipelineName,
            description: pipelineDescription,
            nodes: nodesPayload,
            edges: edgesPayload,
          },
          currentTenant?.slug
        )
      }

      setViewModeWithUrl("list")
      fetchData()
    } catch (error) {
      console.error("Failed to save pipeline", error)
      alert("Failed to save pipeline")
    } finally {
      setSaving(false)
    }
  }

  const handleCompile = async () => {
    if (!selectedPipeline) return

    setCompiling(true)
    setCompileResult(null)
    try {
      const result = await ragAdminService.compilePipeline(
        selectedPipeline.id,
        currentTenant?.slug
      )
      setCompileResult(result)
      setShowCompileDialog(true)
      if (result.success) {
        fetchData()
      }
    } catch (error) {
      console.error("Failed to compile pipeline", error)
    } finally {
      setCompiling(false)
    }
  }

  const renderList = () => (
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
          <Button size="sm" onClick={() => setViewModeWithUrl("create")}>
            <Plus className="h-4 w-4 mr-2" />
            New Pipeline
          </Button>
        </div>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Version</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Updated</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pipelines.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  No pipelines found. Create one to get started.
                </TableCell>
              </TableRow>
            ) : (
              pipelines.map((pipeline) => (
                <TableRow key={pipeline.id}>
                  <TableCell className="font-medium">{pipeline.name}</TableCell>
                  <TableCell className="text-muted-foreground max-w-[200px] truncate">
                    {pipeline.description || "-"}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">v{pipeline.version}</Badge>
                  </TableCell>
                  <TableCell>
                    {pipeline.is_published ? (
                      <Badge className="bg-green-500/10 text-green-600 border-green-500/20">
                        <CheckCircle2 className="h-3 w-3 mr-1" />
                        Published
                      </Badge>
                    ) : (
                      <Badge variant="secondary">
                        <Edit className="h-3 w-3 mr-1" />
                        Draft
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(pipeline.updated_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setViewModeWithUrl("edit", pipeline.id)}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDelete(pipeline.id)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  )

  const renderEditor = () => {
    if (!catalog) return null

    return (
      <div className="flex flex-col h-full bg-muted/20">
        <div className="flex-1 overflow-hidden relative">
          <PipelineBuilder
            catalog={catalog as any}
            operatorSpecs={operatorSpecs as any}
            initialNodes={editorNodes as any}
            initialEdges={editorEdges}
            onSave={handleSaveGraph as any}
          />
        </div>

        <Dialog open={showCompileDialog} onOpenChange={setShowCompileDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {compileResult?.success ? (
                  <>
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                    Compilation Successful
                  </>
                ) : (
                  <>
                    <XCircle className="h-5 w-5 text-destructive" />
                    Compilation Failed
                  </>
                )}
              </DialogTitle>
              <DialogDescription>
                {compileResult?.success
                  ? `Pipeline v${compileResult.version} compiled successfully.`
                  : "Please fix the errors below and try again."}
              </DialogDescription>
            </DialogHeader>

            {compileResult && !compileResult.success && (
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {compileResult.errors.map((err, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 p-2 rounded-md bg-destructive/10 text-destructive text-sm"
                  >
                    <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                    <div>
                      <span className="font-medium">[{err.code}]</span> {err.message}
                      {err.node_id && (
                        <span className="text-xs opacity-75 ml-1">
                          (Node: {err.node_id})
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {compileResult?.warnings && compileResult.warnings.length > 0 && (
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {compileResult.warnings.map((warn, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 p-2 rounded-md bg-yellow-500/10 text-yellow-600 text-sm"
                  >
                    <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>{warn.message}</span>
                  </div>
                ))}
              </div>
            )}

            <DialogFooter>
              <Button onClick={() => setShowCompileDialog(false)}>Close</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full w-full">
      <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb
              items={[
                { label: "Dashboard", href: "/admin/dashboard" },
                { label: "RAG Management", href: "/admin/rag" },
                { label: "Pipeline Builder", href: "/admin/pipelines", active: viewMode === "list" },
                ...(viewMode === "create" ? [{ label: "New Pipeline", active: true }] : []),
                ...(viewMode === "edit" ? [{ label: pipelineName || "Edit Pipeline", active: true }] : []),
              ]}
            />
          </div>
        </div>
        {!loading && viewMode !== "list" && (
          <div className="flex items-center gap-2">
            <Input
              value={pipelineName}
              onChange={(e) => setPipelineName(e.target.value)}
              placeholder="Pipeline name"
              className="w-48 h-9"
            />
            <Input
              value={pipelineDescription}
              onChange={(e) => setPipelineDescription(e.target.value)}
              placeholder="Description (optional)"
              className="w-64 h-9 hidden md:block" // Hide on small screens to save space
            />
            <div className="w-px h-6 bg-border mx-1" />
            {viewMode === "edit" && selectedPipeline && (
              <Button
                variant="outline"
                size="sm"
                className="h-9"
                onClick={handleCompile}
                disabled={compiling}
              >
                {compiling ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                Compile
              </Button>
            )}
            <Button size="sm" onClick={handleSave} disabled={saving} className="h-9">
              {saving ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              Save
            </Button>
          </div>
        )}
      </header>
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="p-4 space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-[400px] w-full" />
          </div>
        ) : viewMode === "list" ? (
          <div className="p-4">{renderList()}</div>
        ) : (
          renderEditor()
        )}
      </div>
    </div>
  )
}
