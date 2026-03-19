"use client"

import { useEffect, useMemo, useState } from "react"
import { ChevronDown, ChevronRight, Loader2, Plus, Trash2, Wrench } from "lucide-react"
import { useRouter } from "next/navigation"

import { Button } from "@/components/ui/button"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { agentService, Agent } from "@/services"

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

type SchemaMode = "outline" | "drilldown" | "split" | "composer" | "canvas"
type SurfaceTab = "input" | "input_ui"
type SchemaNodeType = "string" | "number" | "boolean" | "object" | "array"

type SchemaNode = {
    id: string
    name: string
    type: SchemaNodeType
    required: boolean
    description: string
    children: SchemaNode[]
    item: SchemaNode | null
    expanded: boolean
    emitBaseType: boolean
    schemaPatchText: string
    uiLabel: string
    uiPlaceholder: string
    uiHelp: string
}

const SCHEMA_MODES: Array<{ id: SchemaMode; label: string; description: string }> = [
    { id: "outline", label: "Outline Tree", description: "Recursive tree with inline structure editing." },
    { id: "drilldown", label: "Breadcrumb Drilldown", description: "One level at a time with a path header." },
    { id: "split", label: "Split Tree + Detail", description: "Compact tree on the left, focused editing on the right." },
    { id: "composer", label: "Slash Composer", description: "Quick-add structure with token-like rows." },
    { id: "canvas", label: "Indented Schema Canvas", description: "Minimal recursive canvas with typographic depth." },
]

function createId() {
    return Math.random().toString(36).slice(2, 10)
}

function createNode(overrides: Partial<SchemaNode> = {}): SchemaNode {
    return {
        id: createId(),
        name: "",
        type: "string",
        required: false,
        description: "",
        children: [],
        item: null,
        expanded: true,
        emitBaseType: true,
        schemaPatchText: "",
        uiLabel: "",
        uiPlaceholder: "",
        uiHelp: "",
        ...overrides,
    }
}

function normalizeSchemaType(raw: unknown): SchemaNodeType {
    if (raw === "number" || raw === "integer") return "number"
    if (raw === "boolean") return "boolean"
    if (raw === "array") return "array"
    if (raw === "object") return "object"
    return "string"
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
    return !!value && typeof value === "object" && !Array.isArray(value)
}

function extractSchemaPatch(record: Record<string, unknown>, type: SchemaNodeType) {
    const patch: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(record)) {
        if (key === "description" || key === "required") continue
        if (key === "type" && typeof value === "string") continue
        if (type === "object" && (key === "properties" || key === "additionalProperties")) continue
        if (type === "array" && key === "items") continue
        patch[key] = value
    }
    return Object.keys(patch).length > 0 ? JSON.stringify(patch, null, 2) : ""
}

function schemaToNode(name: string, schema: unknown, required = false): SchemaNode {
    const record = isPlainObject(schema) ? schema : {}
    const hasObjectShape = isPlainObject(record.properties)
    const hasArrayShape = record.items !== undefined
    const type = hasObjectShape ? "object" : hasArrayShape ? "array" : normalizeSchemaType(record.type)
    const emitBaseType = hasObjectShape || hasArrayShape || typeof record.type === "string"
    const node = createNode({
        name,
        type,
        required,
        description: typeof record.description === "string" ? record.description : "",
        emitBaseType,
        schemaPatchText: extractSchemaPatch(record, type),
    })

    if (type === "object") {
        const properties = isPlainObject(record.properties) ? record.properties : {}
        const requiredNames = new Set(Array.isArray(record.required) ? record.required.filter((value): value is string => typeof value === "string") : [])
        node.children = Object.entries(properties).map(([childName, childSchema]) =>
            schemaToNode(childName, childSchema, requiredNames.has(childName))
        )
    }

    if (type === "array") {
        node.item = schemaToNode("item", record.items, true)
    }

    return node
}

function mergePatch(base: Record<string, unknown>, patchText: string) {
    if (!patchText.trim()) return base
    try {
        const patch = JSON.parse(patchText)
        if (!isPlainObject(patch)) return base
        return { ...base, ...patch }
    } catch {
        return base
    }
}

function nodeToSchema(node: SchemaNode): Record<string, unknown> {
    const base: Record<string, unknown> = {}
    if (node.emitBaseType) {
        base.type = node.type
    }

    if (node.type === "object") {
        const properties: Record<string, unknown> = {}
        const required = node.children.filter((child) => child.required && child.name.trim()).map((child) => child.name.trim())
        for (const child of node.children) {
            const key = child.name.trim()
            if (!key) continue
            properties[key] = nodeToSchema(child)
        }
        base.properties = properties
        base.additionalProperties = false
        if (required.length > 0) {
            base.required = required
        }
    } else if (node.type === "array") {
        base.items = node.item ? nodeToSchema(node.item) : { type: "string" }
    }

    if (node.description.trim()) {
        base.description = node.description.trim()
    }

    return mergePatch(base, node.schemaPatchText)
}

function findNode(node: SchemaNode, id: string): SchemaNode | null {
    if (node.id === id) return node
    for (const child of node.children) {
        const match = findNode(child, id)
        if (match) return match
    }
    if (node.item) {
        return findNode(node.item, id)
    }
    return null
}

function findPath(node: SchemaNode, id: string, trail: SchemaNode[] = []): SchemaNode[] | null {
    const nextTrail = [...trail, node]
    if (node.id === id) return nextTrail
    for (const child of node.children) {
        const match = findPath(child, id, nextTrail)
        if (match) return match
    }
    if (node.item) {
        return findPath(node.item, id, nextTrail)
    }
    return null
}

function updateNode(node: SchemaNode, id: string, updater: (node: SchemaNode) => SchemaNode): SchemaNode {
    if (node.id === id) return updater(node)
    return {
        ...node,
        children: node.children.map((child) => updateNode(child, id, updater)),
        item: node.item ? updateNode(node.item, id, updater) : null,
    }
}

function removeNode(node: SchemaNode, id: string): SchemaNode {
    return {
        ...node,
        children: node.children
            .filter((child) => child.id !== id)
            .map((child) => removeNode(child, id)),
        item: node.item?.id === id ? null : node.item ? removeNode(node.item, id) : null,
    }
}

function createChild(type: SchemaNodeType, name = "") {
    return createNode({
        name,
        type,
        expanded: true,
        children: type === "object" ? [] : [],
        item: type === "array" ? createNode({ name: "item", type: "string", required: true }) : null,
    })
}

function typeAccent(type: SchemaNodeType) {
    if (type === "object") return "text-sky-700 bg-sky-500/10"
    if (type === "array") return "text-amber-700 bg-amber-500/10"
    if (type === "boolean") return "text-emerald-700 bg-emerald-500/10"
    if (type === "number") return "text-fuchsia-700 bg-fuchsia-500/10"
    return "text-zinc-700 bg-zinc-500/10"
}

function FieldTypeSelect({
    value,
    onChange,
}: {
    value: SchemaNodeType
    onChange: (value: SchemaNodeType) => void
}) {
    return (
        <select
            value={value}
            onChange={(event) => onChange(event.target.value as SchemaNodeType)}
            className="h-8 rounded-md bg-transparent px-1.5 text-sm text-foreground outline-none"
        >
            <option value="string">string</option>
            <option value="number">number</option>
            <option value="boolean">boolean</option>
            <option value="object">object</option>
            <option value="array">array</option>
        </select>
    )
}

function NavigatorRow({
    node,
    depth,
    selectedId,
    onSelect,
    onToggle,
    style,
}: {
    node: SchemaNode
    depth: number
    selectedId: string
    onSelect: (id: string) => void
    onToggle: (id: string) => void
    style: "outline" | "canvas" | "mini"
}) {
    const selected = node.id === selectedId
    const expandable = node.type === "object" ? node.children.length > 0 : node.type === "array" && !!node.item
    return (
        <div>
            <button
                type="button"
                onClick={() => onSelect(node.id)}
                className={cn(
                    "group flex w-full items-center gap-2 rounded-xl px-2 py-1.5 text-left transition-colors",
                    style === "canvas" ? "min-h-9" : "",
                    selected ? "bg-foreground/[0.06] text-foreground" : "text-muted-foreground hover:bg-foreground/[0.03] hover:text-foreground"
                )}
                style={{ paddingLeft: depth * (style === "mini" ? 14 : 18) + 8 }}
            >
                <span
                    className="flex h-4 w-4 items-center justify-center text-muted-foreground/70"
                    onClick={(event) => {
                        event.stopPropagation()
                        if (expandable) onToggle(node.id)
                    }}
                >
                    {expandable ? node.expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" /> : <span className="h-1 w-1 rounded-full bg-current/40" />}
                </span>
                <span className={cn("min-w-0 truncate text-sm", style === "canvas" ? "font-medium tracking-[-0.01em]" : "")}>
                    {node.name || (node.type === "array" ? "item" : "field")}
                </span>
                <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.16em]", typeAccent(node.type))}>
                    {node.type}
                </span>
                {node.required && node.name ? <span className="text-[10px] uppercase tracking-[0.16em] text-foreground/45">required</span> : null}
            </button>
            {node.expanded && node.type === "object"
                ? node.children.map((child) => (
                      <NavigatorRow
                          key={child.id}
                          node={child}
                          depth={depth + 1}
                          selectedId={selectedId}
                          onSelect={onSelect}
                          onToggle={onToggle}
                          style={style}
                      />
                  ))
                : null}
            {node.expanded && node.type === "array" && node.item ? (
                <NavigatorRow
                    node={node.item}
                    depth={depth + 1}
                    selectedId={selectedId}
                    onSelect={onSelect}
                    onToggle={onToggle}
                    style={style}
                />
            ) : null}
        </div>
    )
}

export function ExportAgentToolDialog({
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
    const [schemaMode, setSchemaMode] = useState<SchemaMode>("outline")
    const [surfaceTab, setSurfaceTab] = useState<SurfaceTab>("input")
    const [rootNode, setRootNode] = useState<SchemaNode>(() => schemaToNode("input", DEFAULT_AGENT_TOOL_INPUT_SCHEMA, true))
    const [selectedNodeId, setSelectedNodeId] = useState("")
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const selectedAgent = useMemo(
        () => agents.find((agent) => agent.id === selectedAgentId) ?? null,
        [agents, selectedAgentId]
    )

    const selectedNode = useMemo(() => findNode(rootNode, selectedNodeId) ?? rootNode, [rootNode, selectedNodeId])
    const selectedPath = useMemo(() => findPath(rootNode, selectedNode.id) ?? [rootNode], [rootNode, selectedNode.id])
    const currentDrillNode = selectedNode.type === "object" ? selectedNode : selectedPath.at(-2) ?? rootNode

    useEffect(() => {
        if (!open) return
        if (!selectedAgentId && agents.length > 0) {
            setSelectedAgentId(agents[0].id)
        }
    }, [agents, open, selectedAgentId])

    useEffect(() => {
        if (!open || !selectedAgent) return
        const nextRoot = schemaToNode("input", DEFAULT_AGENT_TOOL_INPUT_SCHEMA, true)
        setName(`${selectedAgent.name} Tool`)
        setDescription(selectedAgent.description || `Delegates to agent ${selectedAgent.name}.`)
        setSchemaMode("outline")
        setSurfaceTab("input")
        setRootNode(nextRoot)
        setSelectedNodeId(nextRoot.id)
        setError(null)
    }, [open, selectedAgent])

    const updateSelectedNode = (patch: Partial<SchemaNode>) => {
        setRootNode((current) => updateNode(current, selectedNode.id, (node) => ({ ...node, ...patch })))
    }

    const handleToggleExpanded = (id: string) => {
        setRootNode((current) =>
            updateNode(current, id, (node) => ({
                ...node,
                expanded: !node.expanded,
            }))
        )
    }

    const addChildToSelected = (type: SchemaNodeType) => {
        if (selectedNode.type !== "object") return
        const child = createChild(type)
        setRootNode((current) =>
            updateNode(current, selectedNode.id, (node) => ({
                ...node,
                expanded: true,
                children: [...node.children, child],
            }))
        )
        setSelectedNodeId(child.id)
    }

    const replaceArrayItem = (type: SchemaNodeType) => {
        if (selectedNode.type !== "array") return
        const item = createChild(type, "item")
        item.required = true
        setRootNode((current) =>
            updateNode(current, selectedNode.id, (node) => ({
                ...node,
                expanded: true,
                item,
            }))
        )
        setSelectedNodeId(item.id)
    }

    const removeSelected = () => {
        if (selectedNode.id === rootNode.id) return
        const nextSelected = selectedPath.at(-2)?.id ?? rootNode.id
        setRootNode((current) => removeNode(current, selectedNode.id))
        setSelectedNodeId(nextSelected)
    }

    const renderDrilldown = () => {
        const path = findPath(rootNode, currentDrillNode.id) ?? [rootNode]
        return (
            <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {path.map((node, index) => (
                        <button
                            key={node.id}
                            type="button"
                            onClick={() => setSelectedNodeId(node.id)}
                            className="rounded-full px-2 py-1 hover:bg-foreground/[0.04]"
                        >
                            {index === 0 ? "input" : node.name || node.type}
                        </button>
                    ))}
                </div>
                <div className="space-y-1">
                    {(currentDrillNode.type === "object" ? currentDrillNode.children : currentDrillNode.item ? [currentDrillNode.item] : []).map((node) => (
                        <button
                            key={node.id}
                            type="button"
                            onClick={() => setSelectedNodeId(node.id)}
                            className={cn(
                                "flex w-full items-center justify-between rounded-2xl px-3 py-2 text-left transition-colors",
                                selectedNode.id === node.id ? "bg-foreground/[0.06]" : "hover:bg-foreground/[0.03]"
                            )}
                        >
                            <div className="min-w-0">
                                <div className="truncate text-sm text-foreground">{node.name || node.type}</div>
                                <div className="text-[11px] text-muted-foreground">{node.description || node.type}</div>
                            </div>
                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                        </button>
                    ))}
                </div>
            </div>
        )
    }

    const renderSplitTree = () => (
        <div className="grid gap-4 md:grid-cols-[260px_minmax(0,1fr)]">
            <div className="max-h-[320px] overflow-y-auto rounded-2xl bg-background/70 p-2">
                <NavigatorRow node={rootNode} depth={0} selectedId={selectedNode.id} onSelect={setSelectedNodeId} onToggle={handleToggleExpanded} style="mini" />
            </div>
            <div className="rounded-2xl bg-background/70 p-3">
                <div className="mb-3 text-xs uppercase tracking-[0.16em] text-muted-foreground">Selected</div>
                <div className="space-y-2">
                    <Input
                        aria-label="Selected Field Name"
                        value={selectedNode.id === rootNode.id ? "input" : selectedNode.name}
                        onChange={(event) => selectedNode.id !== rootNode.id && updateSelectedNode({ name: event.target.value })}
                        disabled={selectedNode.id === rootNode.id}
                    />
                    <div className="flex items-center gap-2">
                        <FieldTypeSelect value={selectedNode.type} onChange={(value) => updateSelectedNode({ type: value, children: value === "object" ? selectedNode.children : [], item: value === "array" ? selectedNode.item ?? createChild("string", "item") : null })} />
                        {selectedNode.id !== rootNode.id ? (
                            <label className="flex items-center gap-2 text-sm text-muted-foreground">
                                <input
                                    type="checkbox"
                                    checked={selectedNode.required}
                                    onChange={(event) => updateSelectedNode({ required: event.target.checked })}
                                />
                                Required
                            </label>
                        ) : null}
                    </div>
                    <Input
                        aria-label="Selected Field Description"
                        placeholder="Description"
                        value={selectedNode.description}
                        onChange={(event) => updateSelectedNode({ description: event.target.value })}
                    />
                </div>
            </div>
        </div>
    )

    const renderComposer = () => (
        <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
                {(["string", "number", "boolean", "object", "array"] as SchemaNodeType[]).map((type) => (
                    <button
                        key={type}
                        type="button"
                        onClick={() => (selectedNode.type === "array" ? replaceArrayItem(type) : addChildToSelected(type))}
                        className="rounded-full bg-background px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-foreground/[0.06]"
                    >
                        /{type}
                    </button>
                ))}
            </div>
            <div className="space-y-1">
                <NavigatorRow node={rootNode} depth={0} selectedId={selectedNode.id} onSelect={setSelectedNodeId} onToggle={handleToggleExpanded} style="outline" />
            </div>
        </div>
    )

    const renderNavigator = () => {
        if (schemaMode === "drilldown") return renderDrilldown()
        if (schemaMode === "split") return renderSplitTree()
        if (schemaMode === "composer") return renderComposer()
        if (schemaMode === "canvas") {
            return <NavigatorRow node={rootNode} depth={0} selectedId={selectedNode.id} onSelect={setSelectedNodeId} onToggle={handleToggleExpanded} style="canvas" />
        }
        return <NavigatorRow node={rootNode} depth={0} selectedId={selectedNode.id} onSelect={setSelectedNodeId} onToggle={handleToggleExpanded} style="outline" />
    }

    const handleSubmit = async () => {
        if (!selectedAgentId) {
            setError("Select an agent to export.")
            return
        }

        setLoading(true)
        setError(null)
        try {
            await agentService.exportAgentTool(selectedAgentId, {
                name: name.trim() || undefined,
                description: description.trim() || undefined,
                input_schema: nodeToSchema(rootNode),
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

    const advancedPatchError = useMemo(() => {
        if (!selectedNode.schemaPatchText.trim()) return null
        try {
            const parsed = JSON.parse(selectedNode.schemaPatchText)
            return isPlainObject(parsed) ? null : "Advanced patch must be a JSON object."
        } catch {
            return "Advanced patch must be valid JSON."
        }
    }, [selectedNode.schemaPatchText])

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[980px] max-h-[88vh] overflow-hidden border-none bg-[#faf8f4] shadow-2xl">
                <DialogHeader>
                    <DialogTitle>Export Agent As Tool</DialogTitle>
                    <DialogDescription>
                        Create or refresh an owner-managed `agent_call` tool for an agent.
                    </DialogDescription>
                </DialogHeader>

                <div className="max-h-[calc(88vh-11rem)] space-y-5 overflow-y-auto py-2 pr-2">
                    <div className="space-y-2">
                        <Label htmlFor="export-agent-select">Agent</Label>
                        <select
                            id="export-agent-select"
                            value={selectedAgentId}
                            onChange={(event) => setSelectedAgentId(event.target.value)}
                            className="flex h-10 w-full rounded-xl bg-white/80 px-3 py-2 text-sm outline-none"
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
                            <Input id="export-tool-name" value={name} onChange={(event) => setName(event.target.value)} className="rounded-xl border-none bg-white/85 shadow-none" />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="export-tool-description">Description</Label>
                            <Input id="export-tool-description" value={description} onChange={(event) => setDescription(event.target.value)} className="rounded-xl border-none bg-white/85 shadow-none" />
                        </div>
                    </div>

                    <div className="space-y-4 rounded-[28px] bg-[#f2eee7] p-4">
                        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                            <div>
                                <Label>Input Schema Playground</Label>
                                <p className="mt-1 text-xs text-muted-foreground">
                                    Five structural UI directions over the same schema tree.
                                </p>
                            </div>
                            <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
                                {SCHEMA_MODES.map((mode) => (
                                    <button
                                        key={mode.id}
                                        type="button"
                                        onClick={() => setSchemaMode(mode.id)}
                                        className={cn(
                                            "rounded-2xl px-3 py-2 text-left transition-colors",
                                            schemaMode === mode.id ? "bg-white text-foreground" : "text-muted-foreground hover:bg-white/60 hover:text-foreground"
                                        )}
                                    >
                                        <div className="text-sm font-medium">{mode.label}</div>
                                        <div className="mt-1 text-[11px] leading-4">{mode.description}</div>
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="rounded-[24px] bg-white/70 p-3">
                            {renderNavigator()}
                        </div>

                        <div className="rounded-[24px] bg-white/78 p-3">
                            <div className="mb-3 flex items-center gap-2">
                                <button
                                    type="button"
                                    onClick={() => setSurfaceTab("input")}
                                    className={cn(
                                        "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                                        surfaceTab === "input" ? "bg-foreground text-background" : "text-muted-foreground hover:bg-foreground/[0.05]"
                                    )}
                                >
                                    Input
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setSurfaceTab("input_ui")}
                                    className={cn(
                                        "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                                        surfaceTab === "input_ui" ? "bg-foreground text-background" : "text-muted-foreground hover:bg-foreground/[0.05]"
                                    )}
                                >
                                    Input UI
                                </button>
                                <div className="ml-auto text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                                    {selectedNode.id === rootNode.id ? "root object" : selectedNode.name || selectedNode.type}
                                </div>
                            </div>

                            {surfaceTab === "input" ? (
                                <div className="space-y-3">
                                    <div className="grid gap-3 md:grid-cols-[minmax(0,1.2fr)_180px_120px]">
                                        <div className="space-y-1">
                                            <Label htmlFor="selected-field-name">Field Name</Label>
                                            <Input
                                                id="selected-field-name"
                                                value={selectedNode.id === rootNode.id ? "input" : selectedNode.name}
                                                onChange={(event) => selectedNode.id !== rootNode.id && updateSelectedNode({ name: event.target.value })}
                                                disabled={selectedNode.id === rootNode.id}
                                                className="rounded-xl border-none bg-[#f7f4ee] shadow-none"
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label>Type</Label>
                                            <div className="rounded-xl bg-[#f7f4ee]">
                                                <FieldTypeSelect
                                                    value={selectedNode.type}
                                                    onChange={(value) =>
                                                        updateSelectedNode({
                                                            type: value,
                                                            children: value === "object" ? selectedNode.children : [],
                                                            item: value === "array" ? selectedNode.item ?? createChild("string", "item") : null,
                                                        })
                                                    }
                                                />
                                            </div>
                                        </div>
                                        <div className="space-y-1">
                                            <Label>Required</Label>
                                            <label className="flex h-8 items-center gap-2 rounded-xl bg-[#f7f4ee] px-3 text-sm text-muted-foreground">
                                                <input
                                                    type="checkbox"
                                                    checked={selectedNode.required}
                                                    disabled={selectedNode.id === rootNode.id}
                                                    onChange={(event) => updateSelectedNode({ required: event.target.checked })}
                                                />
                                                Required
                                            </label>
                                        </div>
                                    </div>

                                    <div className="space-y-1">
                                        <Label htmlFor="selected-field-description">Description</Label>
                                        <Input
                                            id="selected-field-description"
                                            value={selectedNode.description}
                                            onChange={(event) => updateSelectedNode({ description: event.target.value })}
                                            className="rounded-xl border-none bg-[#f7f4ee] shadow-none"
                                        />
                                    </div>

                                    <div className="flex flex-wrap gap-2">
                                        {selectedNode.type === "object"
                                            ? (["string", "number", "boolean", "object", "array"] as SchemaNodeType[]).map((type) => (
                                                  <Button key={type} type="button" variant="ghost" className="h-8 rounded-full bg-[#f7f4ee] px-3 text-xs hover:bg-[#ede8de]" onClick={() => addChildToSelected(type)}>
                                                      <Plus className="mr-1 h-3.5 w-3.5" />
                                                      Add {type}
                                                  </Button>
                                              ))
                                            : null}
                                        {selectedNode.type === "array"
                                            ? (["string", "number", "boolean", "object", "array"] as SchemaNodeType[]).map((type) => (
                                                  <Button key={type} type="button" variant="ghost" className="h-8 rounded-full bg-[#f7f4ee] px-3 text-xs hover:bg-[#ede8de]" onClick={() => replaceArrayItem(type)}>
                                                      <Plus className="mr-1 h-3.5 w-3.5" />
                                                      Set items to {type}
                                                  </Button>
                                              ))
                                            : null}
                                        {selectedNode.id !== rootNode.id ? (
                                            <Button type="button" variant="ghost" className="h-8 rounded-full px-3 text-xs text-destructive hover:bg-destructive/10" onClick={removeSelected}>
                                                <Trash2 className="mr-1 h-3.5 w-3.5" />
                                                Remove
                                            </Button>
                                        ) : null}
                                    </div>
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    <div className="grid gap-3 md:grid-cols-2">
                                        <div className="space-y-1">
                                            <Label htmlFor="selected-ui-label">Label</Label>
                                            <Input
                                                id="selected-ui-label"
                                                value={selectedNode.uiLabel}
                                                onChange={(event) => updateSelectedNode({ uiLabel: event.target.value })}
                                                className="rounded-xl border-none bg-[#f7f4ee] shadow-none"
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label htmlFor="selected-ui-placeholder">Placeholder</Label>
                                            <Input
                                                id="selected-ui-placeholder"
                                                value={selectedNode.uiPlaceholder}
                                                onChange={(event) => updateSelectedNode({ uiPlaceholder: event.target.value })}
                                                className="rounded-xl border-none bg-[#f7f4ee] shadow-none"
                                            />
                                        </div>
                                    </div>
                                    <div className="space-y-1">
                                        <Label htmlFor="selected-ui-help">Help Text</Label>
                                        <Input
                                            id="selected-ui-help"
                                            value={selectedNode.uiHelp}
                                            onChange={(event) => updateSelectedNode({ uiHelp: event.target.value })}
                                            className="rounded-xl border-none bg-[#f7f4ee] shadow-none"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <Label htmlFor="selected-schema-patch">Advanced Schema Patch</Label>
                                        <Textarea
                                            id="selected-schema-patch"
                                            value={selectedNode.schemaPatchText}
                                            onChange={(event) => updateSelectedNode({ schemaPatchText: event.target.value })}
                                            className="min-h-[120px] rounded-2xl border-none bg-[#f7f4ee] font-mono text-xs shadow-none"
                                            placeholder='{"enum":["short","long"]}'
                                        />
                                        <div className="text-[11px] text-muted-foreground">
                                            Use this only for schema capabilities the UI tree does not expose directly.
                                        </div>
                                        {advancedPatchError ? <div className="text-xs text-destructive">{advancedPatchError}</div> : null}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {error ? (
                        <div className="rounded-2xl bg-destructive/8 px-3 py-2 text-sm text-destructive">
                            {error}
                        </div>
                    ) : null}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                        Cancel
                    </Button>
                    <Button onClick={handleSubmit} disabled={loading || agents.length === 0 || !!advancedPatchError} className="gap-2">
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wrench className="h-4 w-4" />}
                        Export Tool
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
