"use client"

import { useState, useEffect, useMemo } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
    Bot,
    Braces,
    ListTree,
    Loader2,
    MessageSquareQuote,
    Plus,
    Search,
    Sparkles,
    Trash2,
    Wrench,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { agentService, adminService, Agent } from "@/services"
import { AgentCard } from "@/components/agent-card"
import { CreateAgentDialog } from "@/components/agents/CreateAgentDialog"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"


const DEFAULT_AGENT_TOOL_INPUT_SCHEMA = {
    type: "object",
    properties: {
        input: {
            anyOf: [
                { type: "string" },
                { type: "object", additionalProperties: true },
            ],
        },
        text: { type: "string" },
        input_text: { type: "string" },
        messages: { type: "array", items: { type: "object" } },
        context: { type: "object", additionalProperties: true },
    },
    additionalProperties: false,
}

type SchemaPlaygroundMode = "essential" | "fields" | "example" | "json"
type SchemaFieldType = "string" | "number" | "boolean" | "object" | "array"

type SchemaFieldDraft = {
    id: string
    name: string
    type: SchemaFieldType
    required: boolean
    description: string
}

const DEFAULT_ESSENTIAL_FIELD_ORDER = ["input", "text", "input_text", "messages", "context"] as const

const ESSENTIAL_FIELD_DEFS: Record<(typeof DEFAULT_ESSENTIAL_FIELD_ORDER)[number], { label: string; description: string; schema: Record<string, unknown> }> = {
    input: {
        label: "Primary Input",
        description: "Flexible payload that accepts text or structured data.",
        schema: {
            anyOf: [
                { type: "string" },
                { type: "object", additionalProperties: true },
            ],
        },
    },
    text: {
        label: "Text",
        description: "Single plain-text prompt.",
        schema: { type: "string" },
    },
    input_text: {
        label: "Input Text",
        description: "Alias field for plain text input.",
        schema: { type: "string" },
    },
    messages: {
        label: "Messages",
        description: "Conversation transcript array.",
        schema: { type: "array", items: { type: "object" } },
    },
    context: {
        label: "Context",
        description: "Extra structured values for the exported tool.",
        schema: { type: "object", additionalProperties: true },
    },
}

const SCHEMA_MODE_OPTIONS: Array<{
    id: SchemaPlaygroundMode
    label: string
    description: string
    icon: React.ElementType
}> = [
    {
        id: "essential",
        label: "Essential",
        description: "Toggle the common agent input shapes.",
        icon: Sparkles,
    },
    {
        id: "fields",
        label: "Fields",
        description: "Define top-level fields row by row.",
        icon: ListTree,
    },
    {
        id: "example",
        label: "Example",
        description: "Paste a sample payload and infer a schema.",
        icon: MessageSquareQuote,
    },
    {
        id: "json",
        label: "JSON",
        description: "Edit the raw schema directly.",
        icon: Braces,
    },
]

function createFieldDraft(overrides: Partial<SchemaFieldDraft> = {}): SchemaFieldDraft {
    return {
        id: Math.random().toString(36).slice(2, 10),
        name: "",
        type: "string",
        required: false,
        description: "",
        ...overrides,
    }
}

function normalizeFieldType(raw: unknown): SchemaFieldType {
    if (raw === "number" || raw === "integer") return "number"
    if (raw === "boolean") return "boolean"
    if (raw === "object") return "object"
    if (raw === "array") return "array"
    return "string"
}

function inferSchemaFromExample(value: unknown): Record<string, unknown> {
    if (Array.isArray(value)) {
        return {
            type: "array",
            items: value.length > 0 ? inferSchemaFromExample(value[0]) : { type: "string" },
        }
    }
    if (value === null) {
        return { type: "string" }
    }
    if (typeof value === "object") {
        const properties: Record<string, unknown> = {}
        const required: string[] = []
        for (const [key, entry] of Object.entries(value as Record<string, unknown>)) {
            properties[key] = inferSchemaFromExample(entry)
            required.push(key)
        }
        return {
            type: "object",
            properties,
            required,
            additionalProperties: false,
        }
    }
    if (typeof value === "number") return { type: "number" }
    if (typeof value === "boolean") return { type: "boolean" }
    return { type: "string" }
}

function buildSchemaFromFields(fields: SchemaFieldDraft[]): Record<string, unknown> {
    const properties: Record<string, unknown> = {}
    const required: string[] = []

    for (const field of fields) {
        const key = field.name.trim()
        if (!key) continue

        const propertySchema: Record<string, unknown> =
            field.type === "object"
                ? { type: "object", additionalProperties: true }
                : field.type === "array"
                  ? { type: "array", items: { type: "string" } }
                  : { type: field.type }

        if (field.description.trim()) {
            propertySchema.description = field.description.trim()
        }

        properties[key] = propertySchema
        if (field.required) required.push(key)
    }

    return {
        type: "object",
        properties,
        ...(required.length > 0 ? { required } : {}),
        additionalProperties: false,
    }
}

function buildSchemaFromEssentialSelection(selectedKeys: string[]): Record<string, unknown> {
    const properties: Record<string, unknown> = {}
    for (const key of selectedKeys) {
        const def = ESSENTIAL_FIELD_DEFS[key as keyof typeof ESSENTIAL_FIELD_DEFS]
        if (!def) continue
        properties[key] = def.schema
    }
    return {
        type: "object",
        properties,
        additionalProperties: false,
    }
}

function schemaToFieldDrafts(schema: unknown): SchemaFieldDraft[] {
    if (!schema || typeof schema !== "object") return [createFieldDraft()]
    const properties = (schema as Record<string, unknown>).properties
    const required = new Set(Array.isArray((schema as Record<string, unknown>).required) ? ((schema as Record<string, unknown>).required as string[]) : [])
    if (!properties || typeof properties !== "object") return [createFieldDraft()]
    const drafts = Object.entries(properties as Record<string, Record<string, unknown>>).map(([name, propertySchema]) =>
        createFieldDraft({
            name,
            type: normalizeFieldType(propertySchema?.type),
            required: required.has(name),
            description: typeof propertySchema?.description === "string" ? propertySchema.description : "",
        })
    )
    return drafts.length > 0 ? drafts : [createFieldDraft()]
}

function schemaToEssentialSelection(schema: unknown): string[] {
    if (!schema || typeof schema !== "object") return [...DEFAULT_ESSENTIAL_FIELD_ORDER]
    const properties = (schema as Record<string, unknown>).properties
    if (!properties || typeof properties !== "object") return [...DEFAULT_ESSENTIAL_FIELD_ORDER]
    return DEFAULT_ESSENTIAL_FIELD_ORDER.filter((key) => key in (properties as Record<string, unknown>))
}

function ExportAgentToolDialog({
    open,
    agents,
    onOpenChange,
}: {
    open: boolean
    agents: Agent[]
    onOpenChange: (open: boolean) => void
}) {
    const router = useRouter()
    const [selectedAgentId, setSelectedAgentId] = useState("")
    const [name, setName] = useState("")
    const [description, setDescription] = useState("")
    const [schemaMode, setSchemaMode] = useState<SchemaPlaygroundMode>("essential")
    const [inputSchemaText, setInputSchemaText] = useState(JSON.stringify(DEFAULT_AGENT_TOOL_INPUT_SCHEMA, null, 2))
    const [schemaEditorError, setSchemaEditorError] = useState<string | null>(null)
    const [essentialSelection, setEssentialSelection] = useState<string[]>([...DEFAULT_ESSENTIAL_FIELD_ORDER])
    const [fieldDrafts, setFieldDrafts] = useState<SchemaFieldDraft[]>(schemaToFieldDrafts(DEFAULT_AGENT_TOOL_INPUT_SCHEMA))
    const [examplePayloadText, setExamplePayloadText] = useState('{\n  "text": "Summarize this sugya",\n  "context": {\n    "tractate": "Berakhot"\n  }\n}')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const selectedAgent = useMemo(
        () => agents.find((agent) => agent.id === selectedAgentId) ?? null,
        [agents, selectedAgentId]
    )

    useEffect(() => {
        if (!open) {
            return
        }
        if (!selectedAgentId && agents.length > 0) {
            setSelectedAgentId(agents[0].id)
        }
    }, [agents, open, selectedAgentId])

    useEffect(() => {
        if (!open || !selectedAgent) {
            return
        }
        setName(`${selectedAgent.name} Tool`)
        setDescription(selectedAgent.description || `Delegates to agent ${selectedAgent.name}.`)
        setSchemaMode("essential")
        setInputSchemaText(JSON.stringify(DEFAULT_AGENT_TOOL_INPUT_SCHEMA, null, 2))
        setSchemaEditorError(null)
        setEssentialSelection([...DEFAULT_ESSENTIAL_FIELD_ORDER])
        setFieldDrafts(schemaToFieldDrafts(DEFAULT_AGENT_TOOL_INPUT_SCHEMA))
        setExamplePayloadText('{\n  "text": "Summarize this sugya",\n  "context": {\n    "tractate": "Berakhot"\n  }\n}')
        setError(null)
    }, [open, selectedAgent])

    const applySchemaObject = (nextSchema: Record<string, unknown>) => {
        setInputSchemaText(JSON.stringify(nextSchema, null, 2))
        setSchemaEditorError(null)
    }

    const handleSchemaModeChange = (mode: SchemaPlaygroundMode) => {
        setSchemaMode(mode)
        try {
            const parsed = JSON.parse(inputSchemaText)
            setFieldDrafts(schemaToFieldDrafts(parsed))
            setEssentialSelection(schemaToEssentialSelection(parsed))
            setSchemaEditorError(null)
        } catch {
            if (mode !== "json") {
                setSchemaEditorError("Current JSON schema cannot be mapped cleanly into this mode.")
            }
        }
    }

    const toggleEssentialField = (fieldKey: string) => {
        setEssentialSelection((current) => {
            const next = current.includes(fieldKey) ? current.filter((key) => key !== fieldKey) : [...current, fieldKey]
            applySchemaObject(buildSchemaFromEssentialSelection(next))
            return next
        })
    }

    const updateFieldDraft = (fieldId: string, patch: Partial<SchemaFieldDraft>) => {
        setFieldDrafts((current) => {
            const next = current.map((field) => (field.id === fieldId ? { ...field, ...patch } : field))
            applySchemaObject(buildSchemaFromFields(next))
            return next
        })
    }

    const addFieldDraft = () => {
        setFieldDrafts((current) => {
            const next = [...current, createFieldDraft()]
            applySchemaObject(buildSchemaFromFields(next))
            return next
        })
    }

    const removeFieldDraft = (fieldId: string) => {
        setFieldDrafts((current) => {
            const next = current.filter((field) => field.id !== fieldId)
            const normalized = next.length > 0 ? next : [createFieldDraft()]
            applySchemaObject(buildSchemaFromFields(normalized))
            return normalized
        })
    }

    const generateSchemaFromExample = () => {
        try {
            const parsedExample = JSON.parse(examplePayloadText)
            const nextSchema = inferSchemaFromExample(parsedExample)
            applySchemaObject(nextSchema)
            setFieldDrafts(schemaToFieldDrafts(nextSchema))
            setEssentialSelection(schemaToEssentialSelection(nextSchema))
        } catch {
            setSchemaEditorError("Example payload must be valid JSON before generating a schema.")
        }
    }

    const handleSubmit = async () => {
        if (!selectedAgentId) {
            setError("Select an agent to export.")
            return
        }

        let parsedInputSchema: Record<string, unknown>
        try {
            parsedInputSchema = JSON.parse(inputSchemaText)
        } catch {
            setError("Input schema must be valid JSON.")
            return
        }

        setLoading(true)
        setError(null)
        try {
            await agentService.exportAgentTool(selectedAgentId, {
                name: name.trim() || undefined,
                description: description.trim() || undefined,
                input_schema: parsedInputSchema,
            })
            onOpenChange(false)
            router.push("/admin/tools")
        } catch (err) {
            console.error("Failed to export agent tool", err)
            setError("Failed to export agent as a tool.")
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[960px] max-h-[88vh] overflow-hidden">
                <DialogHeader>
                    <DialogTitle>Export Agent As Tool</DialogTitle>
                    <DialogDescription>
                        Create or refresh an owner-managed `agent_call` tool for an agent. Ongoing edits stay in the agents surface.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-2 overflow-y-auto pr-2 max-h-[calc(88vh-11rem)]">
                    <div className="space-y-2">
                        <Label htmlFor="export-agent-select">Agent</Label>
                        <select
                            id="export-agent-select"
                            value={selectedAgentId}
                            onChange={(event) => setSelectedAgentId(event.target.value)}
                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        >
                            {agents.length === 0 ? (
                                <option value="">No agents available</option>
                            ) : (
                                agents.map((agent) => (
                                    <option key={agent.id} value={agent.id}>
                                        {agent.name}
                                    </option>
                                ))
                            )}
                        </select>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                            <Label htmlFor="export-tool-name">Tool Name</Label>
                            <Input id="export-tool-name" value={name} onChange={(event) => setName(event.target.value)} />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="export-tool-description">Description</Label>
                            <Input id="export-tool-description" value={description} onChange={(event) => setDescription(event.target.value)} />
                        </div>
                    </div>

                    <div className="rounded-2xl border border-border/60 bg-muted/[0.18] p-4">
                        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                            <div>
                                <Label htmlFor="export-tool-input-schema">Input Schema Playground</Label>
                                <p className="mt-1 text-xs text-muted-foreground">
                                    Try four schema-writing styles. They all feed the same exported tool schema.
                                </p>
                            </div>
                            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                                {SCHEMA_MODE_OPTIONS.map((mode) => {
                                    const Icon = mode.icon
                                    const isActive = schemaMode === mode.id
                                    return (
                                        <button
                                            key={mode.id}
                                            type="button"
                                            onClick={() => handleSchemaModeChange(mode.id)}
                                            className={cn(
                                                "rounded-xl border px-3 py-2 text-left transition-colors",
                                                isActive
                                                    ? "border-foreground/20 bg-background shadow-sm"
                                                    : "border-border/60 bg-transparent hover:bg-background/70"
                                            )}
                                        >
                                            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
                                                <Icon className="h-4 w-4" />
                                                {mode.label}
                                            </div>
                                            <div className="text-[11px] leading-4 text-muted-foreground">{mode.description}</div>
                                        </button>
                                    )
                                })}
                            </div>
                        </div>

                        {schemaMode === "essential" && (
                            <div className="space-y-3">
                                <div className="text-xs text-muted-foreground">
                                    Best for quick setup. Toggle the common agent input shapes and export immediately.
                                </div>
                                <div className="grid gap-3 md:grid-cols-2">
                                    {DEFAULT_ESSENTIAL_FIELD_ORDER.map((fieldKey) => {
                                        const definition = ESSENTIAL_FIELD_DEFS[fieldKey]
                                        const selected = essentialSelection.includes(fieldKey)
                                        return (
                                            <button
                                                key={fieldKey}
                                                type="button"
                                                onClick={() => toggleEssentialField(fieldKey)}
                                                className={cn(
                                                    "rounded-xl border p-3 text-left transition-colors",
                                                    selected
                                                        ? "border-emerald-400/50 bg-emerald-500/10"
                                                        : "border-border/60 bg-background/60 hover:bg-background"
                                                )}
                                            >
                                                <div className="mb-1 text-sm font-medium text-foreground">{definition.label}</div>
                                                <div className="text-xs leading-5 text-muted-foreground">{definition.description}</div>
                                                <div className="mt-3 text-[11px] font-medium text-foreground/70">
                                                    {selected ? "Included" : "Tap to include"}
                                                </div>
                                            </button>
                                        )
                                    })}
                                </div>
                            </div>
                        )}

                        {schemaMode === "fields" && (
                            <div className="space-y-3">
                                <div className="text-xs text-muted-foreground">
                                    Best for form-like tools. Define top-level fields without writing JSON by hand.
                                </div>
                                <div className="space-y-3">
                                    {fieldDrafts.map((field) => (
                                        <div key={field.id} className="rounded-xl border border-border/60 bg-background/70 p-3">
                                            <div className="grid gap-3 md:grid-cols-[minmax(0,1.2fr)_140px_120px_40px] md:items-start">
                                                <div className="space-y-2">
                                                    <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Field Name</Label>
                                                    <Input
                                                        value={field.name}
                                                        onChange={(event) => updateFieldDraft(field.id, { name: event.target.value })}
                                                        placeholder="query"
                                                    />
                                                </div>
                                                <div className="space-y-2">
                                                    <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Type</Label>
                                                    <select
                                                        value={field.type}
                                                        onChange={(event) => updateFieldDraft(field.id, { type: event.target.value as SchemaFieldType })}
                                                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                                    >
                                                        <option value="string">string</option>
                                                        <option value="number">number</option>
                                                        <option value="boolean">boolean</option>
                                                        <option value="object">object</option>
                                                        <option value="array">array</option>
                                                    </select>
                                                </div>
                                                <label className="flex h-10 items-center gap-2 rounded-md border border-border/60 bg-background px-3 text-sm text-foreground mt-7 md:mt-0 md:self-end">
                                                    <input
                                                        type="checkbox"
                                                        checked={field.required}
                                                        onChange={(event) => updateFieldDraft(field.id, { required: event.target.checked })}
                                                    />
                                                    Required
                                                </label>
                                                <Button
                                                    type="button"
                                                    variant="ghost"
                                                    size="icon"
                                                    className="mt-7 md:mt-0 md:self-end"
                                                    onClick={() => removeFieldDraft(field.id)}
                                                    aria-label={`Remove field ${field.name || field.id}`}
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            </div>
                                            <div className="mt-3 space-y-2">
                                                <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Description</Label>
                                                <Input
                                                    value={field.description}
                                                    onChange={(event) => updateFieldDraft(field.id, { description: event.target.value })}
                                                    placeholder="What this field means to the agent"
                                                />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                                <Button type="button" variant="outline" onClick={addFieldDraft} className="gap-2">
                                    <Plus className="h-4 w-4" />
                                    Add Field
                                </Button>
                            </div>
                        )}

                        {schemaMode === "example" && (
                            <div className="space-y-3">
                                <div className="text-xs text-muted-foreground">
                                    Best for fast prototyping. Paste a realistic example payload and derive the schema from it.
                                </div>
                                <Textarea
                                    className="min-h-[220px] font-mono text-xs bg-background/70"
                                    value={examplePayloadText}
                                    onChange={(event) => setExamplePayloadText(event.target.value)}
                                    placeholder='{"text":"Summarize this sugya","context":{"tractate":"Berakhot"}}'
                                />
                                <Button type="button" variant="outline" onClick={generateSchemaFromExample} className="gap-2">
                                    <Sparkles className="h-4 w-4" />
                                    Generate Schema From Example
                                </Button>
                            </div>
                        )}

                        {schemaMode === "json" && (
                            <div className="space-y-3">
                                <div className="text-xs text-muted-foreground">
                                    Best for advanced control. Edit the exact JSON schema sent during export.
                                </div>
                                <Textarea
                                    id="export-tool-input-schema"
                                    className="min-h-[260px] font-mono text-xs bg-background/70"
                                    value={inputSchemaText}
                                    onChange={(event) => {
                                        setInputSchemaText(event.target.value)
                                        setSchemaEditorError(null)
                                    }}
                                />
                            </div>
                        )}

                        <div className="mt-4 rounded-xl border border-dashed border-border/70 bg-background/50 p-3">
                            <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                                Live Schema Preview
                            </div>
                            <Textarea
                                className="min-h-[180px] font-mono text-xs bg-transparent"
                                value={inputSchemaText}
                                readOnly
                            />
                        </div>
                    </div>

                    {schemaEditorError ? (
                        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-sm text-amber-700">
                            {schemaEditorError}
                        </div>
                    ) : null}

                    {error ? (
                        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                            {error}
                        </div>
                    ) : null}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                        Cancel
                    </Button>
                    <Button onClick={handleSubmit} disabled={loading || agents.length === 0} className="gap-2">
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wrench className="h-4 w-4" />}
                        Export Tool
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

function AgentCardSkeleton() {
    return (
        <div className="rounded-xl border border-border/50 bg-card p-5 space-y-4">
            <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                    <Skeleton className="h-10 w-10 rounded-lg" />
                    <div className="space-y-1.5">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-3 w-20" />
                    </div>
                </div>
                <Skeleton className="h-7 w-7 rounded-md" />
            </div>
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-3/4" />
            <div className="flex items-center justify-between pt-2">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-8 w-16 rounded-md" />
            </div>
        </div>
    )
}

export default function AgentsPage() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const [agents, setAgents] = useState<Agent[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [searchQuery, setSearchQuery] = useState("")
    const [agentMetrics, setAgentMetrics] = useState<Record<string, { threads: number; runs: number; failureRate: number; threadTrend: { date: string; value: number }[] }>>({})
    const isCreateDialogOpen = searchParams.get("create") === "1"
    const isExportDialogOpen = searchParams.get("mode") === "export-tool"

    useEffect(() => {
        loadAgents()
    }, [])

    const loadAgents = async () => {
        try {
            setIsLoading(true)
            const [data, stats] = await Promise.all([
                agentService.listAgents(),
                adminService.getStatsSummary("agents", 14),
            ])
            setAgents(data.agents)
            const nextMetrics: Record<string, { threads: number; runs: number; failureRate: number; threadTrend: { date: string; value: number }[] }> = {}
            for (const item of stats.agents?.agents || []) {
                nextMetrics[item.id] = {
                    threads: item.thread_count,
                    runs: item.run_count,
                    failureRate: item.run_count > 0 ? (item.failed_count / item.run_count) * 100 : 0,
                    threadTrend: item.threads_by_day || [],
                }
            }
            setAgentMetrics(nextMetrics)
            setError(null)
        } catch (err) {
            console.error("Failed to load agents:", err)
            setError("Failed to load agents. Please try again later.")
        } finally {
            setIsLoading(false)
        }
    }

    const filteredAgents = useMemo(() => {
        const q = searchQuery.toLowerCase().trim()
        if (!q) return agents
        return agents.filter(agent =>
            agent.name.toLowerCase().includes(q) ||
            agent.slug?.toLowerCase().includes(q)
        )
    }, [agents, searchQuery])

    const handleDelete = async (agent: Agent) => {
        if (!window.confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return
        try {
            await agentService.deleteAgent(agent.id)
            await loadAgents()
        } catch (err) {
            console.error("Failed to delete agent:", err)
            setError("Failed to delete agent. Please try again.")
        }
    }

    const setCreateDialogOpen = (open: boolean) => {
        if (open) {
            router.push("/admin/agents?create=1")
            return
        }
        router.replace("/admin/agents")
    }

    const setExportDialogOpen = (open: boolean) => {
        if (open) {
            router.push("/admin/agents?mode=export-tool")
            return
        }
        router.replace("/admin/agents")
    }

    return (
        <div className="flex w-full flex-col h-screen bg-background overflow-hidden">
            {/* Header */}
            <AdminPageHeader>
                <CustomBreadcrumb items={[
                    { label: "Agents", href: "/admin/agents", active: true },
                ]} />
                <div className="flex items-center gap-2">
                    <div className="relative w-64">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
                        <Input
                            placeholder="Search agents..."
                            className="h-8 pl-8 bg-muted/30 border-border/50 text-sm placeholder:text-muted-foreground/50"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            disabled={isLoading}
                        />
                    </div>
                    <Button
                        size="sm"
                        className="h-8 gap-1.5"
                        onClick={() => setCreateDialogOpen(true)}
                        disabled={isLoading}
                    >
                        <Plus className="h-3.5 w-3.5" />
                        New Agent
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        className="h-8 gap-1.5"
                        onClick={() => setExportDialogOpen(true)}
                        disabled={isLoading}
                    >
                        <Wrench className="h-3.5 w-3.5" />
                        Export As Tool
                    </Button>
                </div>
            </AdminPageHeader>

            {/* Content */}
            <main className="flex-1 overflow-y-auto p-4" data-admin-page-scroll>
                {error && (
                    <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive flex items-center justify-between">
                        <span>{error}</span>
                        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={loadAgents}>
                            Try Again
                        </Button>
                    </div>
                )}

                {isLoading ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {Array.from({ length: 6 }).map((_, i) => (
                            <AgentCardSkeleton key={i} />
                        ))}
                    </div>
                ) : filteredAgents.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-24 px-4 text-center">
                        <div className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-4">
                            <Bot className="h-6 w-6 text-muted-foreground/40" />
                        </div>
                        <h3 className="text-sm font-medium text-foreground mb-1">
                            {searchQuery ? "No agents match your search" : "No agents yet"}
                        </h3>
                        <p className="text-sm text-muted-foreground/70 max-w-[300px] mb-5">
                            {searchQuery
                                ? "Try a different search term."
                                : "Create your first AI agent to get started."}
                        </p>
                        {!searchQuery && (
                            <Button
                                size="sm"
                                variant="outline"
                                className="gap-1.5"
                                onClick={() => setCreateDialogOpen(true)}
                            >
                                <Plus className="h-3.5 w-3.5" />
                                Create Agent
                            </Button>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 p-2">
                        {filteredAgents.map((agent) => (
                            <AgentCard
                                key={agent.id}
                                agent={agent}
                                metrics={agentMetrics[agent.id]}
                                onOpen={(a) => router.push(`/admin/agents/${a.id}/builder`)}
                                onPlayground={(a) => router.push(`/admin/agents/playground?agentId=${a.id}`)}
                                onDelete={handleDelete}
                            />
                        ))}
                    </div>
                )}
            </main>

            <CreateAgentDialog open={isCreateDialogOpen} onOpenChange={setCreateDialogOpen} />
            <ExportAgentToolDialog open={isExportDialogOpen} onOpenChange={setExportDialogOpen} agents={agents} />
        </div>
    )
}
