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
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import {
    Wrench,
    Plus,
    RefreshCw,
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
    Filter,
    Search,
    Layers,
    Info,
    Server,
} from "lucide-react"
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
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet"
import { JsonViewer } from "@/components/ui/JsonViewer"
import { cn } from "@/lib/utils"
import { TOOL_BUCKETS, TOOL_SUBTYPES, filterTools, getToolBucket, getSubtypeLabel } from "@/lib/tool-types"

const IMPLEMENTATION_ICONS: Record<ToolImplementationType, React.ElementType> = {
    internal: Cog,
    http: Globe,
    rag_retrieval: Database,
    function: Code,
    custom: Wrench,
    artifact: Package,
    mcp: Server,
}

function StatusBadge({ status }: { status: ToolStatus }) {
    const config: Record<ToolStatus, { variant: "default" | "secondary" | "destructive" | "outline"; icon: React.ElementType }> = {
        draft: { variant: "outline", icon: Clock },
        published: { variant: "default", icon: Check },
        deprecated: { variant: "secondary", icon: AlertCircle },
        disabled: { variant: "destructive", icon: AlertCircle },
    }
    const { variant, icon: Icon } = config[status] || { variant: "outline", icon: Clock }
    return (
        <Badge variant={variant} className="gap-1">
            <Icon className="h-3 w-3" />
            {status}
        </Badge>
    )
}

function BucketBadge({ bucket }: { bucket: ToolTypeBucket }) {
    const meta = TOOL_BUCKETS.find((b) => b.id === bucket)
    return (
        <Badge variant="secondary" className="gap-1">
            <Layers className="h-3 w-3" />
            {meta?.label || bucket}
        </Badge>
    )
}

function ImplementationBadge({ type }: { type: ToolImplementationType }) {
    const Icon = IMPLEMENTATION_ICONS[type] || Wrench
    return (
        <Badge variant="outline" className="gap-1">
            <Icon className="h-3 w-3" />
            {getSubtypeLabel(type)}
        </Badge>
    )
}

function CreateToolDialog({ onCreated }: { onCreated: () => void }) {
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const [open, setOpen] = useState(false)
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
        agentService.listOperators().then(setArtifacts).catch(console.error)
    }, [])

    const handleImplementationChange = (type: ToolImplementationType) => {
        let nextConfig: Record<string, unknown> = { type }
        if (type === "http") {
            nextConfig = { type, method: "POST", url: "", headers: {} }
            setHeadersText("{}")
        }
        if (type === "mcp") {
            nextConfig = { type, server_url: "", tool_name: "" }
        }
        if (type === "function") {
            nextConfig = { type, function_name: "" }
        }
        if (type === "artifact") {
            nextConfig = { type, artifact_id: "", artifact_version: "1.0.0" }
        }
        setForm((prev) => ({ ...prev, implementation_type: type, implementation_config: nextConfig }))
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
            setOpen(false)
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
            onCreated()
        } catch (error) {
            console.error("Failed to create tool", error)
        } finally {
            setLoading(false)
        }
    }

    const implementationConfig = (form.implementation_config || {}) as Record<string, any>

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button size="sm">
                    <Plus className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                    New Tool
                </Button>
            </DialogTrigger>
            <DialogContent dir={direction} className="max-w-lg">
                <DialogHeader>
                    <DialogTitle className={isRTL ? "text-right" : "text-left"}>Define New Tool</DialogTitle>
                    <DialogDescription className={isRTL ? "text-right" : "text-left"}>
                        Create a callable capability contract for agents.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4 max-h-[60vh] overflow-auto">
                    <div className="space-y-2">
                        <Label htmlFor="name">Name</Label>
                        <Input
                            id="name"
                            placeholder="Web Search"
                            value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="slug">Slug (unique identifier)</Label>
                        <Input
                            id="slug"
                            placeholder="web-search"
                            value={form.slug}
                            onChange={(e) => setForm({ ...form, slug: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="implementation">Implementation Type</Label>
                        <Select
                            value={form.implementation_type}
                            onValueChange={(v) => handleImplementationChange(v as ToolImplementationType)}
                        >
                            <SelectTrigger className="w-full">
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
                            <Label>Select Artifact</Label>
                            <Select onValueChange={handleArtifactChange}>
                                <SelectTrigger className="w-full">
                                    <SelectValue placeholder="Select an artifact..." />
                                </SelectTrigger>
                                <SelectContent>
                                    {artifacts.filter(a => a.type.startsWith("artifact:")).map(a => (
                                        <SelectItem key={a.type} value={a.type}>
                                            <div className="flex items-center gap-2">
                                                <Package className="h-4 w-4" />
                                                <span>{a.display_name}</span>
                                            </div>
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    )}

                    {form.implementation_type === "http" && (
                        <div className="space-y-2">
                            <Label>HTTP Configuration</Label>
                            <div className="grid gap-2">
                                <Input
                                    placeholder="https://api.example.com/endpoint"
                                    value={implementationConfig.url || ""}
                                    onChange={(e) => setForm({
                                        ...form,
                                        implementation_config: { ...implementationConfig, url: e.target.value }
                                    })}
                                />
                                <Select
                                    value={implementationConfig.method || "POST"}
                                    onValueChange={(value) => setForm({
                                        ...form,
                                        implementation_config: { ...implementationConfig, method: value }
                                    })}
                                >
                                    <SelectTrigger className="w-full">
                                        <SelectValue placeholder="Method" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(m => (
                                            <SelectItem key={m} value={m}>{m}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
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
                        <div className="space-y-2">
                            <Label>MCP Configuration</Label>
                            <div className="grid gap-2">
                                <Input
                                    placeholder="https://mcp.example.com"
                                    value={implementationConfig.server_url || ""}
                                    onChange={(e) => setForm({
                                        ...form,
                                        implementation_config: { ...implementationConfig, server_url: e.target.value }
                                    })}
                                />
                                <Input
                                    placeholder="tool_name"
                                    value={implementationConfig.tool_name || ""}
                                    onChange={(e) => setForm({
                                        ...form,
                                        implementation_config: { ...implementationConfig, tool_name: e.target.value }
                                    })}
                                />
                            </div>
                        </div>
                    )}

                    {form.implementation_type === "function" && (
                        <div className="space-y-2">
                            <Label>Function Configuration</Label>
                            <Input
                                placeholder="function_name"
                                value={implementationConfig.function_name || ""}
                                onChange={(e) => setForm({
                                    ...form,
                                    implementation_config: { ...implementationConfig, function_name: e.target.value }
                                })}
                            />
                        </div>
                    )}

                    <div className="space-y-2">
                        <Label htmlFor="description">Description</Label>
                        <Textarea
                            id="description"
                            placeholder="Search the web for current information..."
                            value={form.description}
                            onChange={(e) => setForm({ ...form, description: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Input Schema (JSON)</Label>
                        <Textarea
                            className="font-mono text-xs"
                            rows={4}
                            value={JSON.stringify(form.input_schema, null, 2)}
                            onChange={(e) => {
                                try {
                                    setForm({ ...form, input_schema: JSON.parse(e.target.value) })
                                } catch { }
                            }}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Output Schema (JSON)</Label>
                        <Textarea
                            className="font-mono text-xs"
                            rows={4}
                            value={JSON.stringify(form.output_schema, null, 2)}
                            onChange={(e) => {
                                try {
                                    setForm({ ...form, output_schema: JSON.parse(e.target.value) })
                                } catch { }
                            }}
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                    <Button onClick={handleCreate} disabled={!form.name || !form.slug || !form.description || loading}>
                        {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                        Create
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

export default function ToolsPage() {
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const [tools, setTools] = useState<ToolDefinition[]>([])
    const [loading, setLoading] = useState(true)
    const [statusFilter, setStatusFilter] = useState<ToolStatus | "all">("all")
    const [bucketFilter, setBucketFilter] = useState<ToolTypeBucket | "all">("all")
    const [subtypeFilter, setSubtypeFilter] = useState<ToolImplementationType | "all">("all")
    const [query, setQuery] = useState("")
    const [selectedTool, setSelectedTool] = useState<ToolDefinition | null>(null)

    const fetchTools = useCallback(async () => {
        setLoading(true)
        try {
            const status = statusFilter === "all" ? undefined : statusFilter
            const bucket = bucketFilter === "all" ? undefined : bucketFilter
            const response = await toolsService.listTools(undefined, status, bucket)
            setTools(response.tools)
        } catch (error) {
            console.error("Failed to fetch tools", error)
        } finally {
            setLoading(false)
        }
    }, [statusFilter, bucketFilter])

    useEffect(() => {
        fetchTools()
    }, [fetchTools])

    const filteredTools = useMemo(() => filterTools(tools, {
        query,
        status: statusFilter,
        bucket: bucketFilter,
        subtype: subtypeFilter,
    }), [tools, query, statusFilter, bucketFilter, subtypeFilter])

    const bucketCounts = useMemo(() => {
        const counts: Record<string, number> = {}
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

    const implementationConfig = selectedTool ? (selectedTool as any)?.config_schema?.implementation : null
    const executionConfig = selectedTool ? (selectedTool as any)?.config_schema?.execution : null

    return (
        <div className="flex flex-col h-full w-full" dir={direction}>
            <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
                <div className="flex items-center gap-3">
                    <CustomBreadcrumb items={[
                        { label: "Tools Registry", href: "/admin/tools", active: true },
                    ]} />
                </div>
                <div className="flex items-center gap-2">
                    <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as ToolStatus | "all")}>
                        <SelectTrigger className="h-9 w-[140px]">
                            <SelectValue placeholder="Filter" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All Status</SelectItem>
                            <SelectItem value="draft">Draft</SelectItem>
                            <SelectItem value="published">Published</SelectItem>
                            <SelectItem value="deprecated">Deprecated</SelectItem>
                            <SelectItem value="disabled">Disabled</SelectItem>
                        </SelectContent>
                    </Select>
                    <Button variant="outline" size="sm" className="h-9" onClick={fetchTools}>
                        <RefreshCw className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                        Refresh
                    </Button>
                    <CreateToolDialog onCreated={fetchTools} />
                </div>
            </header>

            <div className="flex-1 overflow-auto p-4 space-y-4">
                {loading ? (
                    <div className="space-y-4">
                        {[...Array(3)].map((_, i) => (
                            <Skeleton key={i} className="h-20 w-full" />
                        ))}
                    </div>
                ) : tools.length === 0 ? (
                    <Card>
                        <CardContent className="py-12 text-center">
                            <Wrench className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                            <h3 className="text-lg font-semibold mb-2">No Tools Defined</h3>
                            <p className="text-muted-foreground mb-4">
                                Define callable capabilities for your agents.
                            </p>
                            <CreateToolDialog onCreated={fetchTools} />
                        </CardContent>
                    </Card>
                ) : (
                    <>
                        <div className="grid gap-3 md:grid-cols-4">
                            {TOOL_BUCKETS.map((bucket) => (
                                <Card key={bucket.id} className="border-border/60">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-sm font-semibold flex items-center gap-2">
                                            <Layers className="h-4 w-4 text-muted-foreground" />
                                            {bucket.label}
                                        </CardTitle>
                                        <CardDescription className="text-xs">
                                            {bucket.description}
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent className="pt-0">
                                        <div className="text-2xl font-bold">{bucketCounts[bucket.id] || 0}</div>
                                    </CardContent>
                                </Card>
                            ))}
                        </div>

                        <Card className="border-border/60">
                            <CardContent className="p-3 flex flex-wrap gap-2 items-center">
                                <div className="flex items-center gap-2 flex-1 min-w-[220px]">
                                    <Search className="h-4 w-4 text-muted-foreground" />
                                    <Input
                                        placeholder="Search tools..."
                                        value={query}
                                        onChange={(e) => setQuery(e.target.value)}
                                        className="h-9"
                                    />
                                </div>
                                <div className="flex items-center gap-2">
                                    <Filter className="h-4 w-4 text-muted-foreground" />
                                    <Select value={bucketFilter} onValueChange={(v) => setBucketFilter(v as ToolTypeBucket | "all")}>
                                        <SelectTrigger className="h-9 w-[160px]">
                                            <SelectValue placeholder="Bucket" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="all">All Buckets</SelectItem>
                                            {TOOL_BUCKETS.map((bucket) => (
                                                <SelectItem key={bucket.id} value={bucket.id}>{bucket.label}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Select value={subtypeFilter} onValueChange={(v) => setSubtypeFilter(v as ToolImplementationType | "all")}>
                                        <SelectTrigger className="h-9 w-[180px]">
                                            <SelectValue placeholder="Subtype" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="all">All Subtypes</SelectItem>
                                            {TOOL_SUBTYPES.map((subtype) => (
                                                <SelectItem key={subtype.id} value={subtype.id}>{subtype.label}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </CardContent>
                        </Card>

                        <div className="grid gap-3">
                            {filteredTools.map((tool) => (
                                <Card key={tool.id} className="border-border/60 hover:border-border transition cursor-pointer" onClick={() => setSelectedTool(tool)}>
                                    <CardContent className="p-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                                        <div className="space-y-1">
                                            <div className="flex items-center gap-2">
                                                <span className="font-semibold">{tool.name}</span>
                                                <BucketBadge bucket={getToolBucket(tool)} />
                                                <ImplementationBadge type={tool.implementation_type} />
                                                <StatusBadge status={tool.status} />
                                            </div>
                                            <div className="text-xs text-muted-foreground font-mono">{tool.slug}</div>
                                            <div className="text-xs text-muted-foreground line-clamp-2">{tool.description}</div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Badge variant="outline" className="text-xs">v{tool.version}</Badge>
                                            <Button variant="ghost" size="icon" onClick={(e) => {
                                                e.stopPropagation()
                                                setSelectedTool(tool)
                                            }}>
                                                <Info className="h-4 w-4" />
                                            </Button>
                                            {tool.status === "draft" && (
                                                <Button variant="outline" size="sm" onClick={(e) => {
                                                    e.stopPropagation()
                                                    handlePublish(tool.id)
                                                }}>
                                                    <Check className="h-3 w-3 mr-1" />
                                                    Publish
                                                </Button>
                                            )}
                                            {tool.status === "draft" && (
                                                <Button variant="ghost" size="icon" onClick={(e) => {
                                                    e.stopPropagation()
                                                    handleDelete(tool.id)
                                                }}>
                                                    <Trash2 className="h-4 w-4 text-destructive" />
                                                </Button>
                                            )}
                                        </div>
                                    </CardContent>
                                </Card>
                            ))}
                        </div>
                    </>
                )}
            </div>

            <Sheet open={!!selectedTool} onOpenChange={(open) => !open && setSelectedTool(null)}>
                <SheetContent side="right" className="w-full sm:max-w-lg">
                    <SheetHeader>
                        <SheetTitle>{selectedTool?.name}</SheetTitle>
                        <SheetDescription>{selectedTool?.description}</SheetDescription>
                    </SheetHeader>
                    {selectedTool && (
                        <div className="px-4 pb-6 space-y-4 overflow-y-auto">
                            <div className="flex flex-wrap gap-2">
                                <BucketBadge bucket={getToolBucket(selectedTool)} />
                                <ImplementationBadge type={selectedTool.implementation_type} />
                                <StatusBadge status={selectedTool.status} />
                                <Badge variant="outline">v{selectedTool.version}</Badge>
                            </div>
                            <div className="text-xs text-muted-foreground font-mono">{selectedTool.slug}</div>

                            <div className="space-y-2">
                                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Input Schema</div>
                                <JsonViewer value={selectedTool.input_schema} maxHeight="200px" />
                            </div>
                            <div className="space-y-2">
                                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Output Schema</div>
                                <JsonViewer value={selectedTool.output_schema} maxHeight="200px" />
                            </div>
                            <div className="space-y-2">
                                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Implementation Config</div>
                                <JsonViewer value={implementationConfig || {}} maxHeight="200px" />
                            </div>
                            <div className="space-y-2">
                                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Execution Config</div>
                                <JsonViewer value={executionConfig || {}} maxHeight="200px" />
                            </div>
                        </div>
                    )}
                </SheetContent>
            </Sheet>
        </div>
    )
}
