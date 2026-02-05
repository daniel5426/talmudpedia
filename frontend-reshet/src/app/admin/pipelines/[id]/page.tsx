"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter, useParams, useSearchParams } from "next/navigation"
import { useTenant } from "@/contexts/TenantContext"
import { ragAdminService, VisualPipeline, OperatorCatalog, OperatorSpec, CompileResult, PipelineStepExecution } from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import {
    Play,
    CheckCircle2,
    XCircle,
    AlertCircle,
    Loader2,
    Save,
} from "lucide-react"
import { PipelineBuilder } from "@/components/pipeline"
import { RunPipelineDialog } from "@/components/pipeline/RunPipelineDialog"
import { Node, Edge } from "@xyflow/react"

interface PipelineNodeData {
    operator: string
    category: string
    displayName: string
    config: Record<string, unknown>
    inputType: string
    outputType: string
    isConfigured: boolean
    hasErrors: boolean
    [key: string]: unknown
}

export default function PipelineEditorPage() {
    const { currentTenant } = useTenant()
    const router = useRouter()
    const params = useParams()
    const searchParams = useSearchParams()
    const pipelineId = params.id as string
    const jobIdParam = searchParams.get("jobId")
    const isNew = pipelineId === "new"

    const [loading, setLoading] = useState(true)
    const [pipeline, setPipeline] = useState<VisualPipeline | null>(null)
    const [catalog, setCatalog] = useState<OperatorCatalog | null>(null)
    const [operatorSpecs, setOperatorSpecs] = useState<Record<string, OperatorSpec>>({})

    const [pipelineName, setPipelineName] = useState("")
    const [pipelineDescription, setPipelineDescription] = useState("")
    const [pipelineType, setPipelineType] = useState<"ingestion" | "retrieval">("ingestion")
    const [editorNodes, setEditorNodes] = useState<Node<PipelineNodeData>[]>([])
    const [editorEdges, setEditorEdges] = useState<Edge[]>([])



    const [saving, setSaving] = useState(false)
    const [compiling, setCompiling] = useState(false)
    const [compileResult, setCompileResult] = useState<CompileResult | null>(null)
    const [showCompileDialog, setShowCompileDialog] = useState(false)
    const [isRunDialogOpen, setIsRunDialogOpen] = useState(false)
    const [runningJobId, setRunningJobId] = useState<string | null>(jobIdParam)
    const [executionSteps, setExecutionSteps] = useState<Record<string, PipelineStepExecution> | undefined>(undefined)

    // Sync runningJobId with URL param if it's missing (e.g. after hydration)
    useEffect(() => {
        if (jobIdParam) {
            setRunningJobId(jobIdParam)
        }
    }, [jobIdParam])


    // Fetch all data needed for the editor
    useEffect(() => {
        if (!currentTenant) return

        const fetchData = async () => {
            setLoading(true)
            try {
                // Always fetch catalog and specs
                const [catalogRes, specsRes] = await Promise.all([
                    ragAdminService.getOperatorCatalog(currentTenant.slug),
                    ragAdminService.listOperatorSpecs(currentTenant.slug),
                ])
                setCatalog(catalogRes)
                setOperatorSpecs(specsRes)

                // If editing existing pipeline, fetch it
                if (!isNew) {
                    const pipelinesRes = await ragAdminService.listVisualPipelines(currentTenant.slug)
                    let foundPipeline = pipelinesRes.pipelines.find(p => p.id === pipelineId)

                    // If not found, it might be an executable_pipeline_id
                    if (!foundPipeline) {
                        try {
                            const execPipeline = await ragAdminService.getExecutablePipeline(pipelineId, currentTenant.slug)
                            if (execPipeline?.visual_pipeline_id) {
                                foundPipeline = pipelinesRes.pipelines.find(p => p.id === execPipeline.visual_pipeline_id)
                            }
                        } catch (e) {
                            console.error("Failed to fetch executable pipeline", e)
                        }
                    }

                    if (foundPipeline) {
                        setPipeline(foundPipeline)
                        setPipelineName(foundPipeline.name)
                        setPipelineDescription(foundPipeline.description || "")
                        setPipelineType((foundPipeline as any).pipeline_type || "ingestion")

                        // Convert pipeline data to editor format
                        const nodes: Node<PipelineNodeData>[] = foundPipeline.nodes.map((n: any) => {
                            // Use specsRes for reliable input/output type resolution (handles custom operators)
                            const spec = specsRes[n.operator]
                            return {
                                id: n.id,
                                type: n.category,
                                position: n.position,
                                data: {
                                    operator: n.operator,
                                    category: n.category,
                                    displayName: spec?.display_name || n.operator,
                                    config: n.config,
                                    inputType: spec?.input_type || "none",
                                    outputType: spec?.output_type || "none",
                                    isConfigured: true,
                                    hasErrors: false,
                                },
                            }
                        })


                        const edges: Edge[] = foundPipeline.edges.map((e: any) => ({
                            id: e.id,
                            source: e.source,
                            target: e.target,
                        }))

                        setEditorNodes(nodes)
                        setEditorEdges(edges)
                    } else {
                        // Pipeline not found, redirect to list
                        router.push("/admin/pipelines")
                        return
                    }
                }
            } catch (error) {
                console.error("Failed to fetch data", error)
            } finally {
                setLoading(false)
            }
        }

        fetchData()
    }, [currentTenant, currentTenant?.slug, pipelineId, isNew, router])

    // Polling for execution steps
    useEffect(() => {
        if (!runningJobId) return

        let isMounted = true
        const poll = async () => {
            try {
                const [stepsRes, jobRes] = await Promise.all([
                    ragAdminService.getJobSteps(runningJobId, currentTenant?.slug),
                    ragAdminService.getPipelineJob(runningJobId, currentTenant?.slug)
                ])

                if (isMounted) {
                    const stepsMap = stepsRes.steps.reduce((acc, s) => ({ ...acc, [s.step_id]: s }), {} as Record<string, PipelineStepExecution>)
                    setExecutionSteps(prev => ({
                        ...(prev || {}),
                        ...stepsMap
                    }))

                    if (["completed", "failed", "cancelled"].includes(jobRes.status)) {
                        // Job finished, but we stay in execution mode to show results
                        // Polling continues for now (could be optimized)
                    }
                }
            } catch (error) {
                console.error("Failed to poll execution steps", error)
            }
        }

        poll() // Initial call
        const interval = setInterval(poll, 2000)
        return () => {
            isMounted = false
            clearInterval(interval)
        }
    }, [runningJobId, currentTenant?.slug])

    const handleRunPipeline = async (inputParams: Record<string, Record<string, unknown>>) => {
        if (!compileResult?.executable_pipeline_id) return
        try {
            const res = await ragAdminService.createPipelineJob({
                executable_pipeline_id: compileResult.executable_pipeline_id,
                input_params: inputParams
            }, currentTenant?.slug)

            // Update URL with jobId for persistence
            const newUrl = `${window.location.pathname}?jobId=${res.job_id}`
            window.history.pushState({}, "", newUrl)

            // Start polling
            setRunningJobId(res.job_id)

            // Optimistically set the source nodes to running so they start spinning immediately
            const startNodeIds = editorNodes
                .filter(node => !editorEdges.some(e => e.target === node.id))
                .map(node => node.id)

            const initialSteps = startNodeIds.reduce((acc, nodeId) => ({
                ...acc,
                [nodeId]: {
                    status: 'running',
                    step_id: nodeId,
                    id: 'optimistic',
                    job_id: res.job_id,
                    operator_id: editorNodes.find(n => n.id === nodeId)?.data.operator || '',
                    metadata: {},
                    execution_order: 0,
                    created_at: new Date().toISOString()
                } as PipelineStepExecution
            }), {})
            setExecutionSteps(initialSteps)

            // alert("Pipeline job started!") // Remove alert to be less intrusive
        } catch (e) {
            console.error("Failed to start job", e)
            alert("Failed to start job")
        }
    }

    const handleSaveGraph = useCallback(
        (nodes: Node<PipelineNodeData>[], edges: Edge[]) => {
            setEditorNodes(nodes)
            setEditorEdges(edges)
        },
        []
    )

    const handleExitExecutionMode = useCallback(() => {
        setRunningJobId(null)
        setExecutionSteps(undefined)
        // Clear jobId from URL ensuring searchParams update
        router.replace(window.location.pathname, { scroll: false })
    }, [router])

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

            if (isNew) {
                const created = await ragAdminService.createVisualPipeline(
                    {
                        name: pipelineName,
                        description: pipelineDescription,
                        pipeline_type: pipelineType,
                        nodes: nodesPayload,
                        edges: edgesPayload,
                    },
                    currentTenant?.slug
                )
                // Navigate to edit mode of the created pipeline
                router.push(`/admin/pipelines/${created.id}`)
            } else if (pipeline) {
                await ragAdminService.updateVisualPipeline(
                    pipeline.id,
                    {
                        name: pipelineName,
                        description: pipelineDescription,
                        pipeline_type: pipelineType,
                        nodes: nodesPayload,
                        edges: edgesPayload,
                    },
                    currentTenant?.slug
                )
                // Refresh pipeline data
                const pipelinesRes = await ragAdminService.listVisualPipelines(currentTenant?.slug)
                const updatedPipeline = pipelinesRes.pipelines.find(p => p.id === pipeline.id)
                if (updatedPipeline) {
                    setPipeline(updatedPipeline)
                }
            }
        } catch (error) {
            console.error("Failed to save pipeline", error)
            alert("Failed to save pipeline")
        } finally {
            setSaving(false)
        }
    }

    const handleCompile = async () => {
        if (!pipeline) return

        setCompiling(true)
        setCompileResult(null)
        try {
            const result = await ragAdminService.compilePipeline(
                pipeline.id,
                currentTenant?.slug
            )
            setCompileResult(result)
            setShowCompileDialog(true)
        } catch (error) {
            console.error("Failed to compile pipeline", error)
        } finally {
            setCompiling(false)
        }
    }

    if (loading) {
        return (
            <div className="flex flex-col h-full w-full">
                <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
                    <Skeleton className="h-6 w-48" />
                    <Skeleton className="h-9 w-32" />
                </header>
                <div className="flex-1 flex items-center justify-center">
                    <div className="flex flex-col items-center gap-4">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                        <p className="text-muted-foreground">Loading pipeline...</p>
                    </div>
                </div>
            </div>
        )
    }

    if (!catalog) return null

    return (
        <div className="flex flex-col h-full w-full">
            <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
                <div className="flex items-center gap-3">
                    <CustomBreadcrumb
                        items={[
                            { label: "RAG Management", href: "/admin/rag" },
                            { label: "Pipelines", href: "/admin/pipelines" },
                            { label: isNew ? "New Pipeline" : pipelineName || "Edit Pipeline", active: true },
                        ]}
                    />
                </div>
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
                        className="w-64 h-9 hidden md:block"
                    />
                    {!isNew ? (
                        <div className="flex items-center px-2 py-1 bg-muted/50 rounded-md border border-border/50">
                            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mr-2">Type</span>
                            <Badge variant="outline" className={cn(
                                "h-5 text-[9px] px-1.5 uppercase font-bold border-none",
                                pipelineType === "retrieval" ? "bg-purple-500/10 text-purple-600" : "bg-blue-500/10 text-blue-600"
                            )}>
                                {pipelineType}
                            </Badge>
                        </div>
                    ) : (
                        <div className="flex bg-muted/50 p-1 rounded-md h-9 items-center">
                            <Button
                                variant={pipelineType === "ingestion" ? "secondary" : "ghost"}
                                size="sm"
                                className="h-7 text-[10px] px-2 rounded-sm"
                                onClick={() => setPipelineType("ingestion")}
                            >
                                Ingestion
                            </Button>
                            <Button
                                variant={pipelineType === "retrieval" ? "secondary" : "ghost"}
                                size="sm"
                                className="h-7 text-[10px] px-2 rounded-sm"
                                onClick={() => setPipelineType("retrieval")}
                            >
                                Retrieval
                            </Button>
                        </div>
                    )}
                    <div className="w-px h-6 bg-border mx-1" />
                    {!isNew && pipeline && (
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
            </header>

            <div className="flex-1 overflow-hidden relative bg-muted/20">
                <PipelineBuilder
                    catalog={catalog as any}
                    operatorSpecs={operatorSpecs as any}
                    initialNodes={editorNodes as any}
                    initialEdges={editorEdges}
                    pipelineType={pipelineType}
                    onChange={handleSaveGraph as any}
                    onSave={handleSave}
                    onAddCustomOperator={() => {
                        if (confirm("You are about to leave the pipeline editor. Unsaved changes may be lost.")) {
                            router.push("/admin/rag/operators?mode=create")
                        }
                    }}
                    onCompile={handleCompile}
                    onRun={() => setIsRunDialogOpen(true)}
                    isSaving={saving}
                    isCompiling={compiling}
                    executionSteps={executionSteps}
                    isExecutionMode={!!runningJobId}
                    onExitExecutionMode={handleExitExecutionMode}
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
                        <Button variant="outline" onClick={() => setIsRunDialogOpen(true)}>Run Pipeline</Button>
                        <Button onClick={() => setShowCompileDialog(false)}>Close</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <RunPipelineDialog
                open={isRunDialogOpen}
                onOpenChange={setIsRunDialogOpen}
                onRun={handleRunPipeline}
                compileResult={compileResult}
            />
        </div>
    )
}
