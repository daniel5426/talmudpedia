"use client"

import { useEffect, useState, useCallback } from "react"
import { useDirection } from "@/components/direction-provider"
import { useTenant } from "@/contexts/TenantContext"
import {
    toolsService,
    agentService,
    AgentOperatorSpec,
    ToolDefinition,
    ToolImplementationType,
    ToolStatus,
    CreateToolRequest,
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
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

const IMPLEMENTATION_ICONS: Record<ToolImplementationType, React.ElementType> = {
    internal: Cog,
    http: Globe,
    rag_retrieval: Database,
    function: Code,
    custom: Wrench,
    artifact: Package,
}

const IMPLEMENTATION_LABELS: Record<ToolImplementationType, string> = {
    internal: "Internal",
    http: "HTTP Endpoint",
    rag_retrieval: "RAG Retrieval",
    function: "Python Function",
    custom: "Custom",
    artifact: "Agent Artifact",
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

function ImplementationBadge({ type }: { type: ToolImplementationType }) {
    const Icon = IMPLEMENTATION_ICONS[type] || Wrench
    return (
        <Badge variant="secondary" className="gap-1">
            <Icon className="h-3 w-3" />
            {IMPLEMENTATION_LABELS[type] || type}
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
    })
    const [artifacts, setArtifacts] = useState<AgentOperatorSpec[]>([])

    useEffect(() => {
        agentService.listOperators().then(setArtifacts).catch(console.error)
    }, [])

    const handleArtifactChange = (artifactId: string) => {
        const artifact = artifacts.find(a => a.type === artifactId)
        if (!artifact) return

        setForm(prev => ({
            ...prev,
            name: prev.name || artifact.display_name,
            slug: prev.slug || artifact.type.replace("artifact:", ""),
            description: prev.description || artifact.description,
            input_schema: artifact.config_schema, // Artifact config becomes tool input? 
            // Wait, Artifact "config_schema" is static config. "ui" has input/output types.
            // Artifacts usually expect 'state' but might have specific inputs if adapted.
            // For now, let's map config_schema to input_schema as a starting point.
            output_schema: {},
            artifact_id: artifact.type, // Using type string as ID for now
            artifact_version: "1.0.0" // Placeholder
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
            })
            onCreated()
        } catch (error) {
            console.error("Failed to create tool", error)
        } finally {
            setLoading(false)
        }
    }

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
                            onValueChange={(v) => setForm({ ...form, implementation_type: v as ToolImplementationType })}
                        >
                            <SelectTrigger className="w-full">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {Object.entries(IMPLEMENTATION_LABELS).map(([key, label]) => (
                                    <SelectItem key={key} value={key}>{label}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    {form.implementation_type === "artifact" && (
                        <div className="space-y-2">
                            <Label>Select Artifact</Label>
                            <Select
                                onValueChange={handleArtifactChange}
                            >
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
    const { currentTenant } = useTenant()
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const [tools, setTools] = useState<ToolDefinition[]>([])
    const [loading, setLoading] = useState(true)
    const [statusFilter, setStatusFilter] = useState<ToolStatus | "all">("all")

    const fetchTools = useCallback(async () => {
        setLoading(true)
        try {
            const status = statusFilter === "all" ? undefined : statusFilter
            const response = await toolsService.listTools(undefined, status)
            setTools(response.tools)
        } catch (error) {
            console.error("Failed to fetch tools", error)
        } finally {
            setLoading(false)
        }
    }, [statusFilter])

    useEffect(() => {
        fetchTools()
    }, [fetchTools])

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

    const draftTools = tools.filter(t => t.status === "draft")
    const publishedTools = tools.filter(t => t.status !== "draft")

    return (
        <div className="flex flex-col h-full w-full" dir={direction}>
            <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <CustomBreadcrumb items={[
                            { label: "Tools Registry", href: "/admin/tools", active: true },
                        ]} />
                    </div>
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
                        </SelectContent>
                    </Select>
                    <Button variant="outline" size="sm" className="h-9" onClick={fetchTools}>
                        <RefreshCw className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                        Refresh
                    </Button>
                    <CreateToolDialog onCreated={fetchTools} />
                </div>
            </header>

            <div className="flex-1 overflow-auto p-4">
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
                    <Tabs defaultValue="all" dir={direction}>
                        <TabsList>
                            <TabsTrigger value="all">All ({tools.length})</TabsTrigger>
                            <TabsTrigger value="draft">Draft ({draftTools.length})</TabsTrigger>
                            <TabsTrigger value="published">Published ({publishedTools.length})</TabsTrigger>
                        </TabsList>

                        <TabsContent value="all" className="mt-4">
                            <ToolsTable tools={tools} onDelete={handleDelete} onPublish={handlePublish} isRTL={isRTL} />
                        </TabsContent>
                        <TabsContent value="draft" className="mt-4">
                            <ToolsTable tools={draftTools} onDelete={handleDelete} onPublish={handlePublish} isRTL={isRTL} />
                        </TabsContent>
                        <TabsContent value="published" className="mt-4">
                            <ToolsTable tools={publishedTools} onDelete={handleDelete} onPublish={handlePublish} isRTL={isRTL} />
                        </TabsContent>
                    </Tabs>
                )}
            </div>
        </div>
    )
}

function ToolsTable({
    tools,
    onDelete,
    onPublish,
    isRTL
}: {
    tools: ToolDefinition[]
    onDelete: (id: string) => void
    onPublish: (id: string) => void
    isRTL: boolean
}) {
    if (tools.length === 0) {
        return (
            <Card>
                <CardContent className="py-8 text-center text-muted-foreground">
                    No tools in this category.
                </CardContent>
            </Card>
        )
    }

    return (
        <Card>
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Name</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Type</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Version</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Status</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Updated</TableHead>
                        <TableHead className={isRTL ? "text-left" : "text-right"}>Actions</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {tools.map((tool) => (
                        <TableRow key={tool.id}>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>
                                <div className="flex flex-col">
                                    <span className="font-medium">{tool.name}</span>
                                    <span className="text-xs text-muted-foreground font-mono">{tool.slug}</span>
                                    <span className="text-xs text-muted-foreground mt-1 line-clamp-1">{tool.description}</span>
                                </div>
                            </TableCell>
                            <TableCell>
                                <ImplementationBadge type={tool.implementation_type} />
                            </TableCell>
                            <TableCell>
                                <Badge variant="outline">v{tool.version}</Badge>
                            </TableCell>
                            <TableCell>
                                <StatusBadge status={tool.status} />
                            </TableCell>
                            <TableCell className="text-muted-foreground text-sm">
                                {new Date(tool.updated_at).toLocaleDateString()}
                            </TableCell>
                            <TableCell className={isRTL ? "text-left" : "text-right"}>
                                <div className="flex items-center justify-end gap-1">
                                    {tool.status === "draft" && (
                                        <Button variant="outline" size="sm" onClick={() => onPublish(tool.id)}>
                                            <Check className="h-3 w-3 mr-1" />
                                            Publish
                                        </Button>
                                    )}
                                    {tool.status === "draft" && (
                                        <Button variant="ghost" size="icon" onClick={() => onDelete(tool.id)}>
                                            <Trash2 className="h-4 w-4 text-destructive" />
                                        </Button>
                                    )}
                                </div>
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </Card>
    )
}
