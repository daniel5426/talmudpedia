"use client"

import { useEffect, useState, useCallback, useMemo } from "react"
import { useDirection } from "@/components/direction-provider"
import {
    toolsService,
    agentService,
    AgentOperatorSpec,
    ToolDefinition,
    ToolImplementationType,
    ToolStatus,
    CreateToolRequest,
    ToolTypeBucket,
} from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import {
    Wrench,
    Plus,
    Trash2,
    Loader2,
    Globe,
    Database,
    Code,
    Cog,
    Check,
    Clock,
    AlertCircle,
    Package,
    Search,
    Server,
    Bot,
    MoreHorizontal,
    ChevronRight,
    ArrowUpRight,
    X,
} from "lucide-react"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet"
import { JsonViewer } from "@/components/ui/JsonViewer"
import { cn } from "@/lib/utils"
import { TOOL_BUCKETS, TOOL_SUBTYPES, filterTools, getToolBucket, getSubtypeLabel } from "@/lib/tool-types"
import { RetrievalPipelineSelect } from "@/components/shared/RetrievalPipelineSelect"

/* ───────────────────────────── Constants ───────────────────────────── */

const IMPLEMENTATION_ICONS: Record<ToolImplementationType, React.ElementType> = {
    internal: Cog,
    http: Globe,
    rag_retrieval: Database,
    agent_call: Bot,
    function: Code,
    custom: Wrench,
    artifact: Package,
    mcp: Server,
}

const STATUS_CONFIG: Record<ToolStatus, { color: string; label: string }> = {
    published: { color: "bg-emerald-500", label: "Published" },
    draft: { color: "bg-zinc-400", label: "Draft" },
    deprecated: { color: "bg-amber-500", label: "Deprecated" },
    disabled: { color: "bg-red-500", label: "Disabled" },
}

type ToolsSection = "all" | ToolTypeBucket

const NAV_ITEMS: Array<{ key: ToolsSection; label: string; icon: React.ElementType }> = [
    { key: "all", label: "All Tools", icon: Wrench },
    { key: "built_in", label: "Built-in", icon: Cog },
    { key: "mcp", label: "MCP", icon: Server },
    { key: "artifact", label: "Artifact", icon: Package },
    { key: "custom", label: "Custom", icon: Code },
]

const DEFAULT_RETRIEVAL_INPUT_SCHEMA: Record<string, unknown> = {
    type: "object",
    properties: {
        query: { type: "string", description: "Search query text" },
        top_k: { type: "integer", minimum: 1, maximum: 50 },
        filters: { type: "object" },
    },
    required: ["query"],
    additionalProperties: false,
}

const DEFAULT_RETRIEVAL_OUTPUT_SCHEMA: Record<string, unknown> = {
    type: "object",
    properties: {
        query: { type: "string" },
        pipeline_id: { type: "string" },
        results: { type: "array", items: { type: "object" } },
        count: { type: "integer" },
    },
    required: ["results"],
    additionalProperties: true,
}

/* ───────────────────────────── Create Tool Dialog ─────────────────── */

function CreateToolDialog({
    open,
    onOpenChange,
    onCreated,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    onCreated: () => void
}) {
    const { direction } = useDirection()
    const [loading, setLoading] = useState(false)
    const [form, setForm] = useState<CreateToolRequest>({
        name: "",
        slug: "",
        description: "",
        input_schema: { type: "object", properties: {} },
        output_schema: { type: "object", properties: {} },
        implementation_type: "http",
        implementation_config: { type: "http", method: "POST", url: "" },
        execution_config: {},
    })
    const [artifacts, setArtifacts] = useState<AgentOperatorSpec[]>([])
    const [headersText, setHeadersText] = useState("{}")

    useEffect(() => {
        if (open) {
            agentService.listOperators().then(setArtifacts).catch(console.error)
        }
    }, [open])

    useEffect(() => {
        if (open) {
            setForm({
                name: "",
                slug: "",
                description: "",
                input_schema: { type: "object", properties: {} },
                output_schema: { type: "object", properties: {} },
                implementation_type: "http",
                implementation_config: { type: "http", method: "POST", url: "" },
                execution_config: {},
            })
            setHeadersText("{}")
        }
    }, [open])

    const handleImplementationChange = (type: ToolImplementationType) => {
        setForm((prev) => {
            let nextConfig: Record<string, unknown> = { type }
            let nextInputSchema = prev.input_schema
            let nextOutputSchema = prev.output_schema

            if (type === "http") {
                nextConfig = { type, method: "POST", url: "", headers: {} }
                setHeadersText("{}")
            }
            if (type === "mcp") nextConfig = { type, server_url: "", tool_name: "" }
            if (type === "function") nextConfig = { type, function_name: "" }
            if (type === "rag_retrieval") {
                nextConfig = { type, pipeline_id: "" }
                nextInputSchema = DEFAULT_RETRIEVAL_INPUT_SCHEMA
                nextOutputSchema = DEFAULT_RETRIEVAL_OUTPUT_SCHEMA
            }
            if (type === "agent_call") nextConfig = { type, target_agent_slug: "", target_agent_id: "" }
            if (type === "artifact") nextConfig = { type, artifact_id: "", artifact_version: "1.0.0" }

            return {
                ...prev,
                implementation_type: type,
                implementation_config: nextConfig,
                input_schema: nextInputSchema,
                output_schema: nextOutputSchema,
            }
        })
    }

    const handleArtifactChange = (artifactId: string) => {
        const artifact = artifacts.find(a => a.type === artifactId)
        if (!artifact) return
        setForm(prev => ({
            ...prev,
            name: prev.name || artifact.display_name,
            slug: prev.slug || artifact.type.replace("artifact:", ""),
            description: prev.description || artifact.description,
            input_schema: artifact.config_schema,
            output_schema: {},
            artifact_id: artifact.type,
            artifact_version: "1.0.0",
            implementation_type: "artifact",
            implementation_config: {
                type: "artifact",
                artifact_id: artifact.type,
                artifact_version: "1.0.0",
            }
        }))
    }

    const handleCreate = async () => {
        if (!form.name || !form.slug || !form.description) return
        setLoading(true)
        try {
            await toolsService.createTool(form)
            onOpenChange(false)
            onCreated()
        } catch (error) {
            console.error("Failed to create tool", error)
        } finally {
            setLoading(false)
        }
    }

    const implementationConfig = (form.implementation_config || {}) as Record<string, any>

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent dir={direction} className="sm:max-w-[560px]">
                <DialogHeader>
                    <DialogTitle>Create Tool</DialogTitle>
                    <DialogDescription>
                        Define a callable capability contract for agents.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-2 max-h-[60vh] overflow-auto">
                    {/* Identity */}
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label className="text-xs font-medium text-muted-foreground">Name</Label>
                            <Input
                                placeholder="Web Search"
                                value={form.name}
                                onChange={(e) => setForm({ ...form, name: e.target.value })}
                                className="h-9"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs font-medium text-muted-foreground">Slug</Label>
                            <Input
                                placeholder="web-search"
                                value={form.slug}
                                onChange={(e) => setForm({ ...form, slug: e.target.value })}
                                className="h-9 font-mono text-sm"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs font-medium text-muted-foreground">Description</Label>
                            <Textarea
                                placeholder="Search the web for current information..."
                                value={form.description}
                                onChange={(e) => setForm({ ...form, description: e.target.value })}
                                rows={2}
                            />
                        </div>
                    </div>

                    {/* Implementation */}
                    <div className="pt-2 border-t border-border/40">
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <Label className="text-xs font-medium text-muted-foreground">Implementation Type</Label>
                                <Select
                                    value={form.implementation_type}
                                    onValueChange={(v) => handleImplementationChange(v as ToolImplementationType)}
                                >
                                    <SelectTrigger className="h-9">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {TOOL_SUBTYPES.map((subtype) => (
                                            <SelectItem key={subtype.id} value={subtype.id}>{subtype.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            {form.implementation_type === "artifact" && (
                                <div className="space-y-2">
                                    <Label className="text-xs font-medium text-muted-foreground">Select Artifact</Label>
                                    <Select onValueChange={handleArtifactChange}>
                                        <SelectTrigger className="h-9">
                                            <SelectValue placeholder="Select an artifact..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {artifacts.filter(a => a.type.startsWith("artifact:")).map(a => (
                                                <SelectItem key={a.type} value={a.type}>
                                                    {a.display_name}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            )}

                            {form.implementation_type === "http" && (
                                <div className="space-y-3">
                                    <div className="space-y-2">
                                        <Label className="text-xs font-medium text-muted-foreground">Endpoint URL</Label>
                                        <Input
                                            placeholder="https://api.example.com/endpoint"
                                            value={implementationConfig.url || ""}
                                            onChange={(e) => setForm({
                                                ...form,
                                                implementation_config: { ...implementationConfig, url: e.target.value }
                                            })}
                                            className="h-9 font-mono text-sm"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label className="text-xs font-medium text-muted-foreground">Method</Label>
                                        <Select
                                            value={implementationConfig.method || "POST"}
                                            onValueChange={(value) => setForm({
                                                ...form,
                                                implementation_config: { ...implementationConfig, method: value }
                                            })}
                                        >
                                            <SelectTrigger className="h-9">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(m => (
                                                    <SelectItem key={m} value={m}>{m}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label className="text-xs font-medium text-muted-foreground">Headers (JSON)</Label>
                                        <Textarea
                                            className="font-mono text-xs"
                                            rows={3}
                                            value={headersText}
                                            onChange={(e) => {
                                                const next = e.target.value
                                                setHeadersText(next)
                                                try {
                                                    const parsed = JSON.parse(next)
                                                    setForm({
                                                        ...form,
                                                        implementation_config: { ...implementationConfig, headers: parsed }
                                                    })
                                                } catch { }
                                            }}
                                            placeholder='{ "Authorization": "Bearer ..." }'
                                        />
                                    </div>
                                </div>
                            )}

                            {form.implementation_type === "mcp" && (
                                <div className="space-y-3">
                                    <div className="space-y-2">
                                        <Label className="text-xs font-medium text-muted-foreground">Server URL</Label>
                                        <Input
                                            placeholder="https://mcp.example.com"
                                            value={implementationConfig.server_url || ""}
                                            onChange={(e) => setForm({
                                                ...form,
                                                implementation_config: { ...implementationConfig, server_url: e.target.value }
                                            })}
                                            className="h-9 font-mono text-sm"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label className="text-xs font-medium text-muted-foreground">Tool Name</Label>
                                        <Input
                                            placeholder="tool_name"
                                            value={implementationConfig.tool_name || ""}
                                            onChange={(e) => setForm({
                                                ...form,
                                                implementation_config: { ...implementationConfig, tool_name: e.target.value }
                                            })}
                                            className="h-9 font-mono text-sm"
                                        />
                                    </div>
                                </div>
                            )}

                            {form.implementation_type === "function" && (
                                <div className="space-y-2">
                                    <Label className="text-xs font-medium text-muted-foreground">Function Name</Label>
                                    <Input
                                        placeholder="function_name"
                                        value={implementationConfig.function_name || ""}
                                        onChange={(e) => setForm({
                                            ...form,
                                            implementation_config: { ...implementationConfig, function_name: e.target.value }
                                        })}
                                        className="h-9 font-mono text-sm"
                                    />
                                </div>
                            )}

                            {form.implementation_type === "rag_retrieval" && (
                                <div className="space-y-2">
                                    <Label className="text-xs font-medium text-muted-foreground">Retrieval Pipeline</Label>
                                    <RetrievalPipelineSelect
                                        value={String(implementationConfig.pipeline_id || "")}
                                        onChange={(value) => setForm({
                                            ...form,
                                            implementation_config: { ...implementationConfig, pipeline_id: value }
                                        })}
                                    />
                                </div>
                            )}

                            {form.implementation_type === "agent_call" && (
                                <div className="space-y-3">
                                    <div className="space-y-2">
                                        <Label className="text-xs font-medium text-muted-foreground">Target Agent Slug</Label>
                                        <Input
                                            placeholder="target_agent_slug"
                                            value={String(implementationConfig.target_agent_slug || "")}
                                            onChange={(e) => setForm({
                                                ...form,
                                                implementation_config: { ...implementationConfig, target_agent_slug: e.target.value }
                                            })}
                                            className="h-9 font-mono text-sm"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label className="text-xs font-medium text-muted-foreground">Target Agent ID (optional)</Label>
                                        <Input
                                            placeholder="target_agent_id"
                                            value={String(implementationConfig.target_agent_id || "")}
                                            onChange={(e) => setForm({
                                                ...form,
                                                implementation_config: { ...implementationConfig, target_agent_id: e.target.value }
                                            })}
                                            className="h-9 font-mono text-sm"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label className="text-xs font-medium text-muted-foreground">Timeout (seconds)</Label>
                                        <Input
                                            placeholder="60"
                                            value={String((form.execution_config as Record<string, unknown> | undefined)?.timeout_s || "")}
                                            onChange={(e) => setForm({
                                                ...form,
                                                execution_config: {
                                                    ...(form.execution_config || {}),
                                                    timeout_s: e.target.value ? Number(e.target.value) : undefined,
                                                },
                                            })}
                                            className="h-9 font-mono text-sm"
                                        />
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Schemas */}
                    <div className="pt-2 border-t border-border/40 space-y-4">
                        <div className="space-y-2">
                            <Label className="text-xs font-medium text-muted-foreground">Input Schema (JSON)</Label>
                            <Textarea
                                className="font-mono text-xs"
                                rows={4}
                                value={JSON.stringify(form.input_schema, null, 2)}
                                onChange={(e) => {
                                    try { setForm({ ...form, input_schema: JSON.parse(e.target.value) }) } catch { }
                                }}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs font-medium text-muted-foreground">Output Schema (JSON)</Label>
                            <Textarea
                                className="font-mono text-xs"
                                rows={4}
                                value={JSON.stringify(form.output_schema, null, 2)}
                                onChange={(e) => {
                                    try { setForm({ ...form, output_schema: JSON.parse(e.target.value) }) } catch { }
                                }}
                            />
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button
                        onClick={handleCreate}
                        disabled={
                            !form.name
                            || !form.slug
                            || !form.description
                            || loading
                            || (form.implementation_type === "rag_retrieval" && !String((implementationConfig.pipeline_id as string) || "").trim())
                            || (form.implementation_type === "agent_call" && !String((implementationConfig.target_agent_slug as string) || "").trim() && !String((implementationConfig.target_agent_id as string) || "").trim())
                        }
                    >
                        {loading && <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />}
                        Create
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

/* ───────────────────────────── Tool Detail Sheet ──────────────────── */

function ToolDetailSheet({
    tool,
    open,
    onOpenChange,
    onPublish,
    onDelete,
}: {
    tool: ToolDefinition | null
    open: boolean
    onOpenChange: (open: boolean) => void
    onPublish: (id: string) => void
    onDelete: (id: string) => void
}) {
    if (!tool) return null

    const status = STATUS_CONFIG[tool.status] || STATUS_CONFIG.draft
    const Icon = IMPLEMENTATION_ICONS[tool.implementation_type] || Wrench
    const implementationConfig = (tool as any)?.config_schema?.implementation
    const executionConfig = (tool as any)?.config_schema?.execution

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
                <SheetHeader className="pb-0">
                    <div className="flex items-start gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/30 text-muted-foreground/70">
                            <Icon className="h-5 w-5" />
                        </div>
                        <div className="flex-1 min-w-0">
                            <SheetTitle className="text-base">{tool.name}</SheetTitle>
                            <SheetDescription className="line-clamp-2 mt-0.5">{tool.description}</SheetDescription>
                        </div>
                    </div>
                </SheetHeader>

                <div className="px-4 pb-6 space-y-6 mt-4">
                    {/* Meta */}
                    <div className="rounded-lg border border-border/50">
                        <div className="divide-y divide-border/30">
                            <div className="flex items-center justify-between px-4 py-2.5">
                                <span className="text-xs text-muted-foreground/60">Status</span>
                                <span className="flex items-center gap-1.5">
                                    <span className={`h-1.5 w-1.5 rounded-full ${status.color}`} />
                                    <span className="text-sm font-medium">{status.label}</span>
                                </span>
                            </div>
                            <div className="flex items-center justify-between px-4 py-2.5">
                                <span className="text-xs text-muted-foreground/60">Slug</span>
                                <span className="text-sm font-mono text-muted-foreground">{tool.slug}</span>
                            </div>
                            <div className="flex items-center justify-between px-4 py-2.5">
                                <span className="text-xs text-muted-foreground/60">Type</span>
                                <span className="text-sm">{getSubtypeLabel(tool.implementation_type)}</span>
                            </div>
                            <div className="flex items-center justify-between px-4 py-2.5">
                                <span className="text-xs text-muted-foreground/60">Bucket</span>
                                <span className="text-sm">{TOOL_BUCKETS.find(b => b.id === getToolBucket(tool))?.label || getToolBucket(tool)}</span>
                            </div>
                            <div className="flex items-center justify-between px-4 py-2.5">
                                <span className="text-xs text-muted-foreground/60">Version</span>
                                <span className="text-sm font-mono">v{tool.version}</span>
                            </div>
                        </div>
                    </div>

                    {/* Schemas */}
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <h3 className="text-xs font-medium text-muted-foreground/60 uppercase tracking-wider">Input Schema</h3>
                            <JsonViewer value={tool.input_schema} maxHeight="200px" />
                        </div>
                        <div className="space-y-2">
                            <h3 className="text-xs font-medium text-muted-foreground/60 uppercase tracking-wider">Output Schema</h3>
                            <JsonViewer value={tool.output_schema} maxHeight="200px" />
                        </div>
                        <div className="space-y-2">
                            <h3 className="text-xs font-medium text-muted-foreground/60 uppercase tracking-wider">Implementation Config</h3>
                            <JsonViewer value={implementationConfig || {}} maxHeight="200px" />
                        </div>
                        <div className="space-y-2">
                            <h3 className="text-xs font-medium text-muted-foreground/60 uppercase tracking-wider">Execution Config</h3>
                            <JsonViewer value={executionConfig || {}} maxHeight="200px" />
                        </div>
                    </div>

                    {/* Actions */}
                    {tool.status === "draft" && (
                        <div className="flex gap-2 pt-4 border-t border-border/40">
                            <Button
                                size="sm"
                                onClick={() => {
                                    onPublish(tool.id)
                                    onOpenChange(false)
                                }}
                                className="gap-1.5"
                            >
                                <ArrowUpRight className="h-3.5 w-3.5" />
                                Publish
                            </Button>
                            <Button
                                size="sm"
                                variant="outline"
                                className="text-destructive hover:text-destructive gap-1.5"
                                onClick={() => {
                                    onDelete(tool.id)
                                    onOpenChange(false)
                                }}
                            >
                                <Trash2 className="h-3.5 w-3.5" />
                                Delete
                            </Button>
                        </div>
                    )}
                </div>
            </SheetContent>
        </Sheet>
    )
}

/* ───────────────────────────── Skeleton Rows ──────────────────────── */

function ToolRowSkeleton() {
    return (
        <div className="flex items-center gap-4 px-4 py-3.5 border-b border-border/50">
            <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
            <div className="flex-1 space-y-1.5">
                <Skeleton className="h-4 w-44" />
                <Skeleton className="h-3 w-28" />
            </div>
            <Skeleton className="h-3 w-16 hidden md:block" />
            <Skeleton className="h-3 w-12" />
        </div>
    )
}

/* ───────────────────────────── Main Component ─────────────────────── */

export default function ToolsPage() {
    const { direction } = useDirection()
    const isRTL = direction === "rtl"

    const [tools, setTools] = useState<ToolDefinition[]>([])
    const [loading, setLoading] = useState(true)

    const [activeSection, setActiveSection] = useState<ToolsSection>("all")
    const [statusFilter, setStatusFilter] = useState<ToolStatus | "all">("all")
    const [subtypeFilter, setSubtypeFilter] = useState<ToolImplementationType | "all">("all")
    const [query, setQuery] = useState("")

    const [selectedTool, setSelectedTool] = useState<ToolDefinition | null>(null)
    const [createDialogOpen, setCreateDialogOpen] = useState(false)

    const fetchTools = useCallback(async () => {
        setLoading(true)
        try {
            const response = await toolsService.listTools()
            setTools(response.tools || [])
        } catch (error) {
            console.error("Failed to fetch tools", error)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchTools()
    }, [fetchTools])

    const filteredTools = useMemo(() => filterTools(tools, {
        query,
        status: statusFilter,
        bucket: activeSection === "all" ? "all" : activeSection,
        subtype: subtypeFilter,
    }), [tools, query, statusFilter, activeSection, subtypeFilter])

    const bucketCounts = useMemo(() => {
        const counts: Record<string, number> = { all: tools.length }
        TOOL_BUCKETS.forEach((bucket) => { counts[bucket.id] = 0 })
        tools.forEach((tool) => {
            const bucket = getToolBucket(tool)
            counts[bucket] = (counts[bucket] || 0) + 1
        })
        return counts
    }, [tools])

    const handleDelete = async (id: string) => {
        if (!confirm("Are you sure you want to delete this tool?")) return
        try {
            await toolsService.deleteTool(id)
            fetchTools()
        } catch (error) {
            console.error("Failed to delete tool", error)
        }
    }

    const handlePublish = async (id: string) => {
        if (!confirm("Publishing will make this tool immutable. Continue?")) return
        try {
            await toolsService.publishTool(id)
            fetchTools()
        } catch (error) {
            console.error("Failed to publish tool", error)
        }
    }

    const activeFiltersCount = [
        statusFilter !== "all",
        subtypeFilter !== "all",
        query.trim().length > 0,
    ].filter(Boolean).length

    return (
        <div className="flex flex-col h-full w-full" dir={direction}>
            {/* Header */}
            <header className="h-12 shrink-0 bg-background px-4 flex items-center justify-between border-b border-border/40">
                <CustomBreadcrumb items={[{ label: "Tools Registry", href: "/admin/tools", active: true }]} />
                <Button
                    size="sm"
                    className="h-8 gap-1.5"
                    onClick={() => setCreateDialogOpen(true)}
                >
                    <Plus className="h-3.5 w-3.5" />
                    New Tool
                </Button>
            </header>

            {/* Body: sidebar nav + content */}
            <div className="flex-1 flex overflow-hidden">
                {/* Sidebar nav */}
                <nav className="w-48 shrink-0 border-r border-border/40 p-3 overflow-y-auto hidden sm:flex flex-col">
                    <div className="space-y-0.5">
                        {NAV_ITEMS.map((item) => {
                            const Icon = item.icon
                            const isActive = activeSection === item.key
                            const count = bucketCounts[item.key] ?? 0
                            return (
                                <button
                                    key={item.key}
                                    onClick={() => setActiveSection(item.key)}
                                    className={cn(
                                        "flex items-center gap-2.5 w-full rounded-md px-2.5 py-1.5 text-sm transition-colors text-left",
                                        isActive
                                            ? "bg-muted/60 text-foreground font-medium"
                                            : "text-muted-foreground hover:text-foreground hover:bg-muted/30"
                                    )}
                                >
                                    <Icon className="h-3.5 w-3.5 shrink-0" />
                                    <span className="flex-1">{item.label}</span>
                                    <span className={cn(
                                        "text-xs tabular-nums",
                                        isActive ? "text-foreground/60" : "text-muted-foreground/50"
                                    )}>
                                        {count}
                                    </span>
                                </button>
                            )
                        })}
                    </div>

                </nav>

                {/* Mobile section picker */}
                <div className="sm:hidden shrink-0 border-b border-border/40 px-4 py-2 flex gap-1 overflow-x-auto">
                    {NAV_ITEMS.map((item) => (
                        <button
                            key={item.key}
                            onClick={() => setActiveSection(item.key)}
                            className={cn(
                                "px-3 py-1.5 rounded-md text-xs whitespace-nowrap transition-colors",
                                activeSection === item.key
                                    ? "bg-muted/60 text-foreground font-medium"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            {item.label}
                        </button>
                    ))}
                </div>

                {/* Content area */}
                <div className="flex-1 flex flex-col overflow-hidden">
                    {/* Filters bar */}
                    <div className="shrink-0 border-b border-border/40 px-4 py-3 flex items-center gap-3">
                        <div className="relative flex-1 max-w-md">
                            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
                            <Input
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                className="h-9 pl-8 bg-muted/30 border-border/50 text-sm placeholder:text-muted-foreground/50"
                                placeholder="Search tools..."
                            />
                        </div>
                        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as ToolStatus | "all")}>
                            <SelectTrigger className="h-9 w-[130px] text-xs">
                                <SelectValue placeholder="Status" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All Status</SelectItem>
                                <SelectItem value="draft">Draft</SelectItem>
                                <SelectItem value="published">Published</SelectItem>
                                <SelectItem value="deprecated">Deprecated</SelectItem>
                                <SelectItem value="disabled">Disabled</SelectItem>
                            </SelectContent>
                        </Select>
                        <Select value={subtypeFilter} onValueChange={(v) => setSubtypeFilter(v as ToolImplementationType | "all")}>
                            <SelectTrigger className="h-9 w-[140px] text-xs">
                                <SelectValue placeholder="Type" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All Types</SelectItem>
                                {TOOL_SUBTYPES.map((subtype) => (
                                    <SelectItem key={subtype.id} value={subtype.id}>{subtype.label}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {activeFiltersCount > 0 && (
                            <button
                                onClick={() => {
                                    setStatusFilter("all")
                                    setSubtypeFilter("all")
                                    setQuery("")
                                }}
                                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                            >
                                <X className="h-3 w-3" />
                                Clear
                            </button>
                        )}
                    </div>

                    {/* Tool list */}
                    <main className="flex-1 overflow-y-auto">
                        {loading ? (
                            <div>
                                {Array.from({ length: 8 }).map((_, i) => (
                                    <ToolRowSkeleton key={i} />
                                ))}
                            </div>
                        ) : filteredTools.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-24 px-4 text-center">
                                <div className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-4">
                                    <Wrench className="h-6 w-6 text-muted-foreground/40" />
                                </div>
                                <h3 className="text-sm font-medium text-foreground mb-1">
                                    {query || statusFilter !== "all" || subtypeFilter !== "all"
                                        ? "No tools match your filters"
                                        : "No tools yet"}
                                </h3>
                                <p className="text-sm text-muted-foreground/70 max-w-[300px] mb-5">
                                    {query || statusFilter !== "all" || subtypeFilter !== "all"
                                        ? "Try adjusting your search or filters."
                                        : "Create your first tool to get started."}
                                </p>
                                {!(query || statusFilter !== "all" || subtypeFilter !== "all") && (
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        className="gap-1.5"
                                        onClick={() => setCreateDialogOpen(true)}
                                    >
                                        <Plus className="h-3.5 w-3.5" />
                                        Create Tool
                                    </Button>
                                )}
                            </div>
                        ) : (
                            <div className="divide-y divide-border/40">
                                {filteredTools.map((tool) => {
                                    const status = STATUS_CONFIG[tool.status] || STATUS_CONFIG.draft
                                    const Icon = IMPLEMENTATION_ICONS[tool.implementation_type] || Wrench
                                    const bucketMeta = TOOL_BUCKETS.find(b => b.id === getToolBucket(tool))

                                    return (
                                        <button
                                            key={tool.id}
                                            onClick={() => setSelectedTool(tool)}
                                            className="group flex items-center gap-4 px-4 py-3.5 w-full text-left transition-colors hover:bg-muted/40"
                                        >
                                            {/* Tool icon */}
                                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/30 text-muted-foreground/70 group-hover:border-border group-hover:bg-muted/50 transition-colors">
                                                <Icon className="h-4 w-4" />
                                            </div>

                                            {/* Name + slug */}
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm font-medium text-foreground truncate">
                                                        {tool.name}
                                                    </span>
                                                    <span className="flex items-center gap-1.5 shrink-0">
                                                        <span className={`h-1.5 w-1.5 rounded-full ${status.color}`} />
                                                        <span className="text-xs text-muted-foreground/70">
                                                            {status.label}
                                                        </span>
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-2 mt-0.5">
                                                    <span className="text-xs text-muted-foreground/60 font-mono truncate">
                                                        {tool.slug}
                                                    </span>
                                                    {bucketMeta && (
                                                        <>
                                                            <span className="text-muted-foreground/30">&middot;</span>
                                                            <span className="text-xs text-muted-foreground/60">
                                                                {bucketMeta.label}
                                                            </span>
                                                        </>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Implementation type */}
                                            <span className="hidden md:block text-xs text-muted-foreground/60 shrink-0">
                                                {getSubtypeLabel(tool.implementation_type)}
                                            </span>

                                            {/* Version */}
                                            <span className="hidden lg:block text-xs text-muted-foreground/50 font-mono shrink-0 w-10 text-right">
                                                v{tool.version}
                                            </span>

                                            {/* Actions */}
                                            <div
                                                onClick={(e) => e.stopPropagation()}
                                                className="shrink-0"
                                            >
                                                <DropdownMenu>
                                                    <DropdownMenuTrigger asChild>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground"
                                                        >
                                                            <MoreHorizontal className="h-4 w-4" />
                                                        </Button>
                                                    </DropdownMenuTrigger>
                                                    <DropdownMenuContent align="end" className="w-40">
                                                        <DropdownMenuItem onClick={() => setSelectedTool(tool)}>
                                                            <ChevronRight className="mr-2 h-3.5 w-3.5" />
                                                            View Details
                                                        </DropdownMenuItem>
                                                        {tool.status === "draft" && (
                                                            <>
                                                                <DropdownMenuItem onClick={() => handlePublish(tool.id)}>
                                                                    <ArrowUpRight className="mr-2 h-3.5 w-3.5" />
                                                                    Publish
                                                                </DropdownMenuItem>
                                                                <DropdownMenuSeparator />
                                                                <DropdownMenuItem
                                                                    className="text-destructive focus:text-destructive"
                                                                    onClick={() => handleDelete(tool.id)}
                                                                >
                                                                    <Trash2 className="mr-2 h-3.5 w-3.5" />
                                                                    Delete
                                                                </DropdownMenuItem>
                                                            </>
                                                        )}
                                                    </DropdownMenuContent>
                                                </DropdownMenu>
                                            </div>
                                        </button>
                                    )
                                })}
                            </div>
                        )}
                    </main>
                </div>
            </div>

            {/* Create dialog */}
            <CreateToolDialog
                open={createDialogOpen}
                onOpenChange={setCreateDialogOpen}
                onCreated={fetchTools}
            />

            {/* Detail sheet */}
            <ToolDetailSheet
                tool={selectedTool}
                open={!!selectedTool}
                onOpenChange={(open) => !open && setSelectedTool(null)}
                onPublish={handlePublish}
                onDelete={handleDelete}
            />
        </div>
    )
}
