"use client"

import { useEffect, useState, useCallback, useMemo } from "react"
import { useRouter } from "next/navigation"
import { useDirection } from "@/components/direction-provider"
import {
    toolsService,
    ToolDefinition,
    ToolImplementationType,
    ToolStatus,
    CreateToolRequest,
    ToolTypeBucket,
} from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { SearchInput } from "@/components/ui/search-input"
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
import { PromptMentionInput } from "@/components/shared/PromptMentionInput"
import { PromptMentionJsonEditor, fillPromptMentionJsonToken } from "@/components/shared/PromptMentionJsonEditor"
import { PromptModal } from "@/components/shared/PromptModal"
import { usePromptMentionModal } from "@/components/shared/usePromptMentionModal"
import { buildArtifactDetailHref, buildArtifactNewHref } from "@/components/admin/artifacts/artifactRoutes"
import { cn } from "@/lib/utils"
import { TOOL_BUCKETS, TOOL_SUBTYPES, filterTools, getToolBucket, getSubtypeLabel } from "@/lib/tool-types"
import { fillMentionInValue } from "@/lib/prompt-mentions"

/* ───────────────────────────── Constants ───────────────────────────── */

const IMPLEMENTATION_ICONS: Record<ToolImplementationType, React.ElementType> = {
    internal: Cog,
    http: Globe,
    rag_pipeline: Database,
    agent_call: Bot,
    function: Code,
    custom: Wrench,
    artifact: Package,
    mcp: Server,
}

const TOOL_CREATE_SUBTYPES = TOOL_SUBTYPES.filter((subtype) => subtype.id !== "artifact" && subtype.id !== "rag_pipeline")

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

type CreateToolIntent = "manual" | "artifact" | "pipeline" | "agent"

const CREATE_TOOL_OPTIONS: Array<{
    id: CreateToolIntent
    title: string
    description: string
    actionLabel: string
    icon: React.ElementType
    disabled?: boolean
}> = [
    {
        id: "manual",
        title: "Integration / Manual Tool",
        description: "Create a registry-managed HTTP, MCP, function, agent-call, or custom tool from `/tools`.",
        actionLabel: "Create Here",
        icon: Wrench,
    },
    {
        id: "artifact",
        title: "Artifact Tool",
        description: "Create a `tool_impl` artifact and let the bound tool row sync from the artifact domain.",
        actionLabel: "Open Artifact Editor",
        icon: Package,
    },
    {
        id: "pipeline",
        title: "Pipeline Tool",
        description: "Create or open a pipeline, then enable `Use as tool` from the pipeline editor.",
        actionLabel: "Open Pipelines",
        icon: Database,
    },
    {
        id: "agent",
        title: "Agent / Workflow Tool",
        description: "Export a published agent as an owner-managed `agent_call` tool from the agents surface.",
        actionLabel: "Open Agents",
        icon: Bot,
    },
]

function CreateToolEntryDialog({
    open,
    onOpenChange,
    onSelect,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    onSelect: (intent: CreateToolIntent) => void
}) {
    const { direction } = useDirection()

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent dir={direction} className="sm:max-w-[720px]">
                <DialogHeader>
                    <DialogTitle>Create Tool</DialogTitle>
                    <DialogDescription>
                        Choose the owning surface first. Only manual tools should be authored directly from the tools registry.
                    </DialogDescription>
                </DialogHeader>
                <div className="grid gap-3 py-2 sm:grid-cols-2">
                    {CREATE_TOOL_OPTIONS.map((option) => {
                        const Icon = option.icon
                        return (
                            <button
                                key={option.id}
                                type="button"
                                disabled={option.disabled}
                                onClick={() => onSelect(option.id)}
                                className={cn(
                                    "rounded-xl border border-border/60 p-4 text-left transition-colors",
                                    option.disabled
                                        ? "cursor-not-allowed opacity-55"
                                        : "hover:border-border hover:bg-muted/30"
                                )}
                            >
                                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg border border-border/60 bg-muted/30 text-muted-foreground/70">
                                    <Icon className="h-5 w-5" />
                                </div>
                                <div className="space-y-1">
                                    <div className="text-sm font-medium text-foreground">{option.title}</div>
                                    <div className="text-xs leading-5 text-muted-foreground/80">{option.description}</div>
                                </div>
                                <div className="mt-4 text-xs font-medium text-foreground/80">{option.actionLabel}</div>
                            </button>
                        )
                    })}
                </div>
            </DialogContent>
        </Dialog>
    )
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
    const promptMentionModal = usePromptMentionModal<
        | { kind: "description"; mentionIndex: number }
        | { kind: "input_schema"; tokenRange: { from: number; to: number } }
        | { kind: "output_schema"; tokenRange: { from: number; to: number } }
    >()
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
    const [headersText, setHeadersText] = useState("{}")
    const [inputSchemaText, setInputSchemaText] = useState('{\n  "type": "object",\n  "properties": {}\n}')
    const [outputSchemaText, setOutputSchemaText] = useState('{\n  "type": "object",\n  "properties": {}\n}')

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
            setInputSchemaText('{\n  "type": "object",\n  "properties": {}\n}')
            setOutputSchemaText('{\n  "type": "object",\n  "properties": {}\n}')
        }
    }, [open])

    const handleImplementationChange = (type: ToolImplementationType) => {
        setForm((prev) => {
            let nextConfig: Record<string, unknown> = { type }
            const nextInputSchema = prev.input_schema
            const nextOutputSchema = prev.output_schema

            if (type === "http") {
                nextConfig = { type, method: "POST", url: "", headers: {} }
                setHeadersText("{}")
            }
            if (type === "mcp") nextConfig = { type, server_url: "", tool_name: "" }
            if (type === "function") nextConfig = { type, function_name: "" }
            if (type === "agent_call") nextConfig = { type, target_agent_slug: "", target_agent_id: "" }

            return {
                ...prev,
                implementation_type: type,
                implementation_config: nextConfig,
                input_schema: nextInputSchema,
                output_schema: nextOutputSchema,
            }
        })
    }

    const handleCreate = async () => {
        if (!form.name || !form.slug || !form.description) return
        setLoading(true)
        try {
            const inputSchema = JSON.parse(inputSchemaText)
            const outputSchema = JSON.parse(outputSchemaText)
            await toolsService.createTool({
                ...form,
                input_schema: inputSchema,
                output_schema: outputSchema,
            })
            onOpenChange(false)
            onCreated()
        } catch (error) {
            console.error("Failed to create tool", error)
        } finally {
            setLoading(false)
        }
    }

    const handlePromptFill = useCallback(async (_promptId: string, content: string) => {
        const context = promptMentionModal.context
        if (!context) return
        if (context.kind === "description") {
            setForm((current) => ({
                ...current,
                description: fillMentionInValue(current.description || "", context.mentionIndex, content),
            }))
            return
        }
        if (context.kind === "input_schema") {
            setInputSchemaText((current) => fillPromptMentionJsonToken(current, context.tokenRange, content))
            return
        }
        setOutputSchemaText((current) => fillPromptMentionJsonToken(current, context.tokenRange, content))
    }, [promptMentionModal.context])

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
                            <PromptMentionInput
                                placeholder="Search the web for current information..."
                                value={form.description}
                                onChange={(description) => setForm({ ...form, description })}
                                surface="tool.description"
                                className="min-h-[56px] border-input bg-background"
                                onMentionClick={(promptId, mentionIndex) =>
                                    promptMentionModal.openPromptMentionModal(promptId, { kind: "description", mentionIndex })
                                }
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
                                        {TOOL_CREATE_SUBTYPES.map((subtype) => (
                                            <SelectItem key={subtype.id} value={subtype.id}>{subtype.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

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
                            <PromptMentionJsonEditor
                                className="font-mono text-xs"
                                height="160px"
                                value={inputSchemaText}
                                onChange={setInputSchemaText}
                                surface="tool.input_schema.description"
                                onMentionClick={(promptId, tokenRange) =>
                                    promptMentionModal.openPromptMentionModal(promptId, { kind: "input_schema", tokenRange })
                                }
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs font-medium text-muted-foreground">Output Schema (JSON)</Label>
                            <PromptMentionJsonEditor
                                className="font-mono text-xs"
                                height="160px"
                                value={outputSchemaText}
                                onChange={setOutputSchemaText}
                                surface="tool.output_schema.description"
                                onMentionClick={(promptId, tokenRange) =>
                                    promptMentionModal.openPromptMentionModal(promptId, { kind: "output_schema", tokenRange })
                                }
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
                            || (form.implementation_type === "agent_call" && !String((implementationConfig.target_agent_slug as string) || "").trim() && !String((implementationConfig.target_agent_id as string) || "").trim())
                        }
                    >
                        {loading && <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />}
                        Create
                    </Button>
                </DialogFooter>
            </DialogContent>
            <PromptModal
                promptId={promptMentionModal.promptId}
                open={promptMentionModal.open}
                onOpenChange={promptMentionModal.handleOpenChange}
                onFill={handlePromptFill}
            />
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
    onOpenEditor,
}: {
    tool: ToolDefinition | null
    open: boolean
    onOpenChange: (open: boolean) => void
    onPublish: (id: string) => void
    onDelete: (id: string) => void
    onOpenEditor: (tool: ToolDefinition) => void
}) {
    if (!tool) return null

    const status = STATUS_CONFIG[tool.status] || STATUS_CONFIG.draft
    const Icon = IMPLEMENTATION_ICONS[tool.implementation_type] || Wrench
    const implementationConfig = tool.implementation_config || {}
    const executionConfig = tool.execution_config || {}
    const canOpenEditor = tool.managed_by === "artifacts" || tool.managed_by === "pipelines" || tool.managed_by === "agents"
    const canPublishFromRegistry = tool.status === "draft" && tool.can_publish_in_registry
    const canDeleteFromRegistry = tool.can_delete_in_registry
    const managerLabel = {
        tools: "Tools",
        artifacts: "Artifacts",
        pipelines: "Pipelines",
        agents: "Agents",
        system: "System",
    }[tool.managed_by]

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
                            <div className="flex items-center justify-between px-4 py-2.5">
                                <span className="text-xs text-muted-foreground/60">Managed By</span>
                                <span className="text-sm">{managerLabel}</span>
                            </div>
                            <div className="flex items-center justify-between px-4 py-2.5">
                                <span className="text-xs text-muted-foreground/60">Ownership</span>
                                <span className="text-sm font-mono text-muted-foreground">{tool.ownership}</span>
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
                    {(canPublishFromRegistry || canOpenEditor || canDeleteFromRegistry) && (
                        <div className="flex gap-2 pt-4 border-t border-border/40">
                            {canPublishFromRegistry && (
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
                            )}
                            {canOpenEditor && (
                                <Button
                                    size="sm"
                                    variant="outline"
                                    className="gap-1.5"
                                    onClick={() => {
                                        onOpenEditor(tool)
                                        onOpenChange(false)
                                    }}
                                >
                                    <ArrowUpRight className="h-3.5 w-3.5" />
                                    Open Editor
                                </Button>
                            )}
                            {canDeleteFromRegistry && (
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
                            )}
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
    const router = useRouter()

    const [tools, setTools] = useState<ToolDefinition[]>([])
    const [loading, setLoading] = useState(true)

    const [activeSection, setActiveSection] = useState<ToolsSection>("all")
    const [statusFilter, setStatusFilter] = useState<ToolStatus | "all">("all")
    const [subtypeFilter, setSubtypeFilter] = useState<ToolImplementationType | "all">("all")
    const [query, setQuery] = useState("")

    const [selectedTool, setSelectedTool] = useState<ToolDefinition | null>(null)
    const [createEntryOpen, setCreateEntryOpen] = useState(false)
    const [createDialogOpen, setCreateDialogOpen] = useState(false)

    const fetchTools = useCallback(async () => {
        setLoading(true)
        try {
            const response = await toolsService.listTools(undefined, undefined, undefined, 0, 100, "summary")
            setTools(response.items || [])
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

    const openToolEditor = useCallback((tool: ToolDefinition) => {
        if (tool.managed_by === "artifacts" && tool.source_object_id) {
            router.push(buildArtifactDetailHref(tool.source_object_id))
            return
        }
        if (tool.managed_by === "pipelines" && tool.source_object_id) {
            router.push(`/admin/pipelines/${tool.source_object_id}?toolSettings=1`)
            return
        }
        if (tool.managed_by === "agents" && tool.source_object_id) {
            router.push(`/admin/agents/${tool.source_object_id}/builder`)
        }
    }, [router])

    const handleCreateIntent = useCallback((intent: CreateToolIntent) => {
        if (intent === "manual") {
            setCreateEntryOpen(false)
            setCreateDialogOpen(true)
            return
        }
        if (intent === "artifact") {
            setCreateEntryOpen(false)
            router.push(buildArtifactNewHref({ kind: "tool_impl" }))
            return
        }
        if (intent === "pipeline") {
            setCreateEntryOpen(false)
            router.push("/admin/pipelines")
            return
        }
        if (intent === "agent") {
            setCreateEntryOpen(false)
            router.push("/admin/agents")
        }
    }, [router])

    const activeFiltersCount = [
        statusFilter !== "all",
        subtypeFilter !== "all",
        query.trim().length > 0,
    ].filter(Boolean).length

    return (
        <div className="flex flex-col h-full w-full" dir={direction}>
            {/* Header */}
            <AdminPageHeader contentClassName="min-h-12 h-auto flex-wrap py-3">
                <CustomBreadcrumb items={[{ label: "Tools Registry", href: "/admin/tools", active: true }]} />
                <div className="flex w-full flex-wrap items-center justify-end gap-2 md:w-auto md:flex-nowrap">
                    <SearchInput
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        size="md"
                        wrapperClassName="min-w-[220px] flex-1 md:w-[280px] md:flex-none"
                        placeholder="Search tools..."
                    />
                    <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as ToolStatus | "all")}>
                        <SelectTrigger className="h-9 w-[130px] text-xs shadow-none">
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
                        <SelectTrigger className="h-9 w-[140px] text-xs shadow-none">
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
                            className="flex h-9 items-center gap-1 px-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
                        >
                            <X className="h-3 w-3" />
                            Clear
                        </button>
                    )}
                    <Button
                        size="sm"
                        className="h-9 gap-1.5"
                        onClick={() => setCreateEntryOpen(true)}
                    >
                        <Plus className="h-3.5 w-3.5" />
                        Create Tool
                    </Button>
                </div>
            </AdminPageHeader>

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
                    {/* Tool list */}
                    <main className="flex-1 overflow-y-auto" data-admin-page-scroll>
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
                                        onClick={() => setCreateEntryOpen(true)}
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
                                        <div
                                            key={tool.id}
                                            role="button"
                                            tabIndex={0}
                                            onClick={() => setSelectedTool(tool)}
                                            onKeyDown={(e) => {
                                                if (e.target !== e.currentTarget) return
                                                if (e.key === "Enter" || e.key === " ") {
                                                    e.preventDefault()
                                                    setSelectedTool(tool)
                                                }
                                            }}
                                            className="group flex items-center gap-4 px-4 py-3.5 w-full text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
                                                        {(tool.managed_by === "artifacts" || tool.managed_by === "pipelines") && (
                                                            <>
                                                                <DropdownMenuItem onClick={() => openToolEditor(tool)}>
                                                                    <ArrowUpRight className="mr-2 h-3.5 w-3.5" />
                                                                    Open Editor
                                                                </DropdownMenuItem>
                                                                <DropdownMenuSeparator />
                                                            </>
                                                        )}
                                                        {(tool.status === "draft" && tool.can_publish_in_registry) || tool.can_delete_in_registry ? (
                                                            <>
                                                                {tool.status === "draft" && tool.can_publish_in_registry && (
                                                                    <DropdownMenuItem onClick={() => handlePublish(tool.id)}>
                                                                        <ArrowUpRight className="mr-2 h-3.5 w-3.5" />
                                                                        Publish
                                                                    </DropdownMenuItem>
                                                                )}
                                                                {tool.can_publish_in_registry && tool.can_delete_in_registry && <DropdownMenuSeparator />}
                                                                {tool.can_delete_in_registry && (
                                                                    <DropdownMenuItem
                                                                        className="text-destructive focus:text-destructive"
                                                                        onClick={() => handleDelete(tool.id)}
                                                                    >
                                                                        <Trash2 className="mr-2 h-3.5 w-3.5" />
                                                                        Delete
                                                                    </DropdownMenuItem>
                                                                )}
                                                            </>
                                                        ) : null}
                                                    </DropdownMenuContent>
                                                </DropdownMenu>
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                    </main>
                </div>
            </div>

            <CreateToolEntryDialog
                open={createEntryOpen}
                onOpenChange={setCreateEntryOpen}
                onSelect={handleCreateIntent}
            />

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
                onOpenEditor={openToolEditor}
            />
        </div>
    )
}
