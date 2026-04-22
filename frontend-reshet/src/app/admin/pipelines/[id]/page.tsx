"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter, useParams, useSearchParams } from "next/navigation"
import { useOrganization } from "@/contexts/OrganizationContext"
import { ragAdminService, VisualPipeline, CompileResult, PipelineStepExecution, PipelineToolBinding } from "@/services"
import type { NodeCatalogItem, NodeAuthoringSpec } from "@/services/graph-authoring"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
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
import { HeaderConfigEditor } from "@/components/builder"
import { formatHttpErrorMessage } from "@/services/http"
import { PromptMentionInput } from "@/components/shared/PromptMentionInput"
import { PromptMentionJsonEditor, fillPromptMentionJsonToken } from "@/components/shared/PromptMentionJsonEditor"
import { PromptModal } from "@/components/shared/PromptModal"
import { usePromptMentionModal } from "@/components/shared/usePromptMentionModal"
import { fillMentionInValue } from "@/lib/prompt-mentions"

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
    const { currentOrganization } = useOrganization()
    const router = useRouter()
    const params = useParams()
    const searchParams = useSearchParams()
    const pipelineId = params.id as string
    const jobIdParam = searchParams.get("jobId")
    const toolSettingsParam = searchParams.get("toolSettings") === "1"
    const isNew = pipelineId === "new"

    const [loading, setLoading] = useState(true)
    const [pipeline, setPipeline] = useState<VisualPipeline | null>(null)
    const [catalog, setCatalog] = useState<NodeCatalogItem[] | null>(null)
    const [operatorSpecs, setOperatorSpecs] = useState<Record<string, NodeAuthoringSpec>>({})

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
    const [toolBinding, setToolBinding] = useState<PipelineToolBinding | null>(null)
    const [toolBindingLoading, setToolBindingLoading] = useState(false)
    const [toolBindingSaving, setToolBindingSaving] = useState(false)
    const [actionError, setActionError] = useState<string | null>(null)
    const [toolName, setToolName] = useState("")
    const [toolDescription, setToolDescription] = useState("")
    const [toolInputSchemaText, setToolInputSchemaText] = useState('{\n  "type": "object",\n  "properties": {},\n  "additionalProperties": false\n}')
    const promptMentionModal = usePromptMentionModal<
        | { kind: "description"; mentionIndex: number }
        | { kind: "schema"; tokenRange: { from: number; to: number } }
    >()

    // Sync runningJobId with URL param if it's missing (e.g. after hydration)
    useEffect(() => {
        if (jobIdParam) {
            setRunningJobId(jobIdParam)
        }
    }, [jobIdParam])


    // Fetch all data needed for the editor
    const loadToolBinding = useCallback(async (targetPipelineId: string) => {
        setToolBindingLoading(true)
        try {
            const binding = await ragAdminService.getPipelineToolBinding(targetPipelineId, currentOrganization?.id)
            setToolBinding(binding)
            setToolName(binding.tool_name || "")
            setToolDescription(binding.description || "")
            setToolInputSchemaText(JSON.stringify(binding.input_schema || {}, null, 2))
        } catch (error) {
            console.error("Failed to fetch pipeline tool binding", error)
            setToolBinding(null)
        } finally {
            setToolBindingLoading(false)
        }
    }, [currentOrganization?.id])

    useEffect(() => {
        if (!currentOrganization) return

        const fetchData = async () => {
            setLoading(true)
            try {
                // Always fetch catalog and specs
                const catalogRes = await ragAdminService.getOperatorCatalog(currentOrganization.id)
                setCatalog(catalogRes.operators || [])
                const operatorIds = (catalogRes.operators || []).map((item) => item.type)
                const specsRes = await ragAdminService.listOperatorSpecs(operatorIds, currentOrganization.id)
                setOperatorSpecs(specsRes.specs || {})

                // If editing existing pipeline, fetch it
                if (!isNew) {
                    const pipelinesRes = await ragAdminService.listVisualPipelines(currentOrganization.id, { view: "full", limit: 100 })
                    let foundPipeline = pipelinesRes.items.find(p => p.id === pipelineId)

                    // If not found, it might be an executable_pipeline_id
                    if (!foundPipeline) {
                        try {
                            const execPipeline = await ragAdminService.getExecutablePipeline(pipelineId, currentOrganization.id)
                            if (execPipeline?.visual_pipeline_id) {
                                foundPipeline = pipelinesRes.items.find(p => p.id === execPipeline.visual_pipeline_id)
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
                            const spec = specsRes.specs?.[n.operator]
                            return {
                                id: n.id,
                                type: n.category,
                                position: n.position,
                                data: {
                                    operator: n.operator,
                                    category: n.category,
                                    displayName: spec?.title || n.operator,
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
                        await loadToolBinding(foundPipeline.id)
                    } else {
                        // Pipeline not found, redirect to list
                        router.push("/admin/pipelines")
                        return
                    }
                }
            } catch (error) {
                console.error("Failed to fetch data", error)
                setActionError("Failed to load pipeline data.")
            } finally {
                setLoading(false)
            }
        }

        fetchData()
    }, [currentOrganization, currentOrganization?.id, loadToolBinding, pipelineId, isNew, router])

    // Polling for execution steps
    useEffect(() => {
        if (!runningJobId) return

        let isMounted = true
        const poll = async () => {
            try {
                const [stepsRes, jobRes] = await Promise.all([
                    ragAdminService.getJobSteps(runningJobId, currentOrganization?.id),
                    ragAdminService.getPipelineJob(runningJobId, currentOrganization?.id)
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
    }, [runningJobId, currentOrganization?.id])

    const handleRunPipeline = async (inputParams: Record<string, Record<string, unknown>>) => {
        if (!compileResult?.executable_pipeline_id) return
        try {
            const res = await ragAdminService.createPipelineJob({
                executable_pipeline_id: compileResult.executable_pipeline_id,
                input_params: inputParams
            }, currentOrganization?.id)
            setActionError(null)

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
            setActionError(formatHttpErrorMessage(e, "Failed to start job."))
            throw e
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
        setActionError(null)
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
                    currentOrganization?.id
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
                    currentOrganization?.id
                )
                // Refresh pipeline data
                const pipelinesRes = await ragAdminService.listVisualPipelines(currentOrganization?.id, { view: "full", limit: 100 })
                const updatedPipeline = pipelinesRes.items.find(p => p.id === pipeline.id)
                if (updatedPipeline) {
                    setPipeline(updatedPipeline)
                    setCompileResult(null)
                    await loadToolBinding(updatedPipeline.id)
                }
            }
        } catch (error) {
            console.error("Failed to save pipeline", error)
            setActionError(formatHttpErrorMessage(error, "Failed to save pipeline."))
        } finally {
            setSaving(false)
        }
    }

    const handleCompile = async () => {
        if (!pipeline) return

        setCompiling(true)
        setCompileResult(null)
        setActionError(null)
        try {
            const result = await ragAdminService.compilePipeline(
                pipeline.id,
                currentOrganization?.id
            )
            setCompileResult(result)
            await loadToolBinding(pipeline.id)
            setShowCompileDialog(true)
        } catch (error) {
            console.error("Failed to compile pipeline", error)
        } finally {
            setCompiling(false)
        }
    }

    const handleSaveToolBinding = useCallback(async (enabled: boolean) => {
        if (!pipeline) {
            alert("Save the pipeline before enabling tool mode.")
            return
        }

        let parsedInputSchema: Record<string, unknown> | undefined
        try {
            parsedInputSchema = JSON.parse(toolInputSchemaText)
        } catch {
            alert("Tool input schema must be valid JSON.")
            return
        }

        setToolBindingSaving(true)
        try {
            const binding = await ragAdminService.updatePipelineToolBinding(
                pipeline.id,
                {
                    enabled,
                    tool_name: toolName,
                    description: toolDescription,
                    input_schema: parsedInputSchema,
                },
                currentOrganization?.id
            )
            setToolBinding(binding)
            setToolName(binding.tool_name || "")
            setToolDescription(binding.description || "")
            setToolInputSchemaText(JSON.stringify(binding.input_schema || {}, null, 2))
        } catch (error) {
            console.error("Failed to update pipeline tool binding", error)
            alert("Failed to update tool settings")
        } finally {
            setToolBindingSaving(false)
        }
    }, [currentOrganization?.id, pipeline, toolDescription, toolInputSchemaText, toolName])

    const ensureExecutableForRun = useCallback(async (): Promise<CompileResult | null> => {
        if (compileResult?.executable_pipeline_id) {
            return compileResult
        }
        if (!pipeline) {
            return null
        }
        try {
            const versionsRes = await ragAdminService.listPipelineVersions(pipeline.id, currentOrganization?.id)
            const versions = versionsRes.versions || []
            const latest = versions.find((v) => v.is_valid) || versions[0]
            if (!latest) {
                setActionError("No executable pipeline found. Compile the pipeline first.")
                return null
            }
            if (pipeline.updated_at && latest.created_at && new Date(pipeline.updated_at).getTime() > new Date(latest.created_at).getTime()) {
                setActionError("Pipeline draft changed since the latest executable was created. Compile the pipeline again before running it.")
                return null
            }
            const resolved: CompileResult = {
                success: true,
                executable_pipeline_id: latest.id,
                version: latest.version,
                errors: [],
                warnings: [],
            }
            setCompileResult(resolved)
            setActionError(null)
            return resolved
        } catch (error) {
            console.error("Failed to resolve latest compiled pipeline version", error)
            setActionError(formatHttpErrorMessage(error, "Failed to resolve the latest executable pipeline."))
            return null
        }
    }, [compileResult, pipeline, currentOrganization?.id])

    const handleOpenRunDialog = useCallback(async () => {
        const resolved = await ensureExecutableForRun()
        if (!resolved?.executable_pipeline_id) {
            return
        }
        setIsRunDialogOpen(true)
    }, [ensureExecutableForRun])

    const handlePromptFill = useCallback(async (_promptId: string, content: string) => {
        const context = promptMentionModal.context
        if (!context) return
        if (context.kind === "description") {
            setToolDescription((current) => fillMentionInValue(current, context.mentionIndex, content))
            return
        }
        setToolInputSchemaText((current) => fillPromptMentionJsonToken(current, context.tokenRange, content))
    }, [promptMentionModal.context])

    if (loading) {
        return (
            <div className="flex flex-col h-full w-full">
                <AdminPageHeader>
                    <Skeleton className="h-6 w-48" />
                    <Skeleton className="h-9 w-32" />
                </AdminPageHeader>
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
            <AdminPageHeader className="z-40">
                    <div className="flex items-center gap-3">
                        <CustomBreadcrumb
                            items={[
                                { label: "Pipelines", href: "/admin/pipelines" },
                                { label: isNew ? "New Pipeline" : pipelineName || "Edit Pipeline", active: true },
                            ]}
                        />
                    </div>
                    <div className="flex items-center gap-2">
                        <HeaderConfigEditor
                            name={pipelineName}
                            description={pipelineDescription}
                            onNameChange={setPipelineName}
                            onDescriptionChange={setPipelineDescription}
                            nameLabel="Pipeline name"
                            descriptionLabel="Description"
                            namePlaceholder="Pipeline name"
                            descriptionPlaceholder="What this pipeline ingests or retrieves."
                            triggerLabel="Edit details"
                            defaultOpen={isNew || toolSettingsParam}
                        >
                            {!isNew && (
                                <div className="space-y-3 border-t border-border/50 pt-4">
                                    <div className="flex items-center justify-between gap-3">
                                        <div>
                                            <div className="text-xs font-medium text-foreground/80">Use as tool</div>
                                            <div className="text-[11px] text-muted-foreground/70">
                                                Create a tool binding owned by this pipeline.
                                            </div>
                                        </div>
                                        <label className="flex items-center gap-2 text-xs text-foreground/80">
                                            <input
                                                type="checkbox"
                                                checked={toolBinding?.enabled || false}
                                                onChange={(event) => void handleSaveToolBinding(event.target.checked)}
                                                disabled={toolBindingSaving || toolBindingLoading}
                                            />
                                            Enabled
                                        </label>
                                    </div>

                                    {(toolBinding?.enabled || toolSettingsParam) && (
                                        <>
                                            <div className="space-y-2">
                                                <span className="text-xs font-medium text-foreground/80">Tool name</span>
                                                <Input
                                                    value={toolName}
                                                    onChange={(event) => setToolName(event.target.value)}
                                                    className="border-border/60 bg-muted/20"
                                                    placeholder="Agent-facing tool name"
                                                    disabled={toolBindingLoading}
                                                />
                                                {toolBinding?.tool_id ? (
                                                    <div className="text-[11px] text-muted-foreground/70">
                                                        Tool ID: <span className="font-mono">{toolBinding.tool_id}</span>
                                                    </div>
                                                ) : null}
                                            </div>
                                            <div className="space-y-2">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-xs font-medium text-foreground/80">Tool description</span>
                                                    <span className="text-[11px] text-muted-foreground/70">
                                                        Status: {toolBindingLoading ? "loading" : (toolBinding?.status || "draft")}
                                                    </span>
                                                </div>
                                                <PromptMentionInput
                                                    value={toolDescription}
                                                    onChange={setToolDescription}
                                                    className="min-h-20 border-border/60 bg-muted/20"
                                                    placeholder="Describe when the agent should call this pipeline tool."
                                                    surface="pipeline.tool_binding.description"
                                                    onMentionClick={(promptId, mentionIndex) =>
                                                        promptMentionModal.openPromptMentionModal(promptId, { kind: "description", mentionIndex })
                                                    }
                                                />
                                            </div>
                                            <div className="space-y-2">
                                                <span className="text-xs font-medium text-foreground/80">Tool input schema (JSON)</span>
                                                <PromptMentionJsonEditor
                                                    value={toolInputSchemaText}
                                                    onChange={setToolInputSchemaText}
                                                    className="min-h-52 font-mono text-xs border-border/60 bg-muted/20"
                                                    height="208px"
                                                    surface="pipeline.tool_binding.input_schema.description"
                                                    onMentionClick={(promptId, tokenRange) =>
                                                        promptMentionModal.openPromptMentionModal(promptId, { kind: "schema", tokenRange })
                                                    }
                                                />
                                            </div>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="w-full"
                                                onClick={() => void handleSaveToolBinding(true)}
                                                disabled={toolBindingSaving || toolBindingLoading}
                                            >
                                                {toolBindingSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                                Save Tool Settings
                                            </Button>
                                        </>
                                    )}
                                </div>
                            )}
                        </HeaderConfigEditor>
                        {!isNew ? (
                            <Badge variant="outline" className={cn(
                                "h-8 rounded-md border px-3 text-xs font-medium capitalize shadow-none",
                                pipelineType === "retrieval"
                                    ? "border-purple-200 bg-purple-500/10 text-purple-700"
                                    : "border-blue-200 bg-blue-500/10 text-blue-700"
                            )}>
                                    {pipelineType}
                            </Badge>
                        ) : (
                            <div className="flex h-8 items-center gap-1 rounded-md border border-border/50 bg-muted/40 p-0.5">
                                <Button
                                    variant={pipelineType === "ingestion" ? "secondary" : "ghost"}
                                    size="sm"
                                    className={cn(
                                        "h-7 rounded-sm px-3 text-xs shadow-none",
                                        pipelineType === "ingestion" ? "bg-background" : "text-muted-foreground"
                                    )}
                                    onClick={() => setPipelineType("ingestion")}
                                >
                                    Ingestion
                                </Button>
                                <Button
                                    variant={pipelineType === "retrieval" ? "secondary" : "ghost"}
                                    size="sm"
                                    className={cn(
                                        "h-7 rounded-sm px-3 text-xs shadow-none",
                                        pipelineType === "retrieval" ? "bg-background" : "text-muted-foreground"
                                    )}
                                    onClick={() => setPipelineType("retrieval")}
                                >
                                    Retrieval
                                </Button>
                            </div>
                        )}
                        <div className="mx-1 h-6 w-px bg-border" />
                        {actionError && (
                            <span className="max-w-[360px] truncate text-xs text-destructive" title={actionError}>
                                {actionError}
                            </span>
                        )}
                        {!isNew && pipeline && (
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-8 rounded-md text-xs shadow-none"
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
                        <Button size="sm" onClick={handleSave} disabled={saving} className="h-8 rounded-md text-xs shadow-none">
                            {saving ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <Save className="h-4 w-4 mr-2" />
                            )}
                            Save
                        </Button>
                    </div>
            </AdminPageHeader>

            <div className="flex-1 overflow-hidden ml-1 mr-2 mb-2 relative ">
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
                    onRun={handleOpenRunDialog}
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
                        <Button variant="outline" onClick={handleOpenRunDialog}>Run Pipeline</Button>
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
            <PromptModal
                promptId={promptMentionModal.promptId}
                open={promptMentionModal.open}
                onOpenChange={promptMentionModal.handleOpenChange}
                onFill={handlePromptFill}
            />
        </div>
    )
}
