"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ChevronDown, ChevronRight, Loader2, Plus, Trash2, Wrench, X } from "lucide-react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogTitle,
} from "@/components/ui/dialog"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { PromptMentionInput } from "@/components/shared/PromptMentionInput"
import { PromptMentionJsonEditor, fillPromptMentionJsonToken } from "@/components/shared/PromptMentionJsonEditor"
import { PromptModal } from "@/components/shared/PromptModal"
import { usePromptMentionModal } from "@/components/shared/usePromptMentionModal"
import { cn } from "@/lib/utils"
import { agentService, Agent } from "@/services"
import { fillMentionInValue } from "@/lib/prompt-mentions"
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

type EditorMode = "builder" | "json"
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
const propertyLabelClassName = "text-[11px] font-bold uppercase tracking-tight text-foreground/50"
const propertyControlClassName = "h-9 text-[13px]"
const propertyTextareaClassName = "min-h-[104px] px-3 py-2 text-[13px] placeholder:text-muted-foreground/40"

function FieldTypeSelect({
    value,
    onChange,
    className,
}: {
    value: SchemaNodeType
    onChange: (value: SchemaNodeType) => void
    className?: string
}) {
    return (
        <Select value={value} onValueChange={(v) => onChange(v as SchemaNodeType)}>
            <SelectTrigger className={cn("h-9 w-full rounded-lg border-none bg-muted/40 text-[13px] font-mono shadow-none focus:ring-1 focus:ring-ring focus:ring-offset-0", className)}>
                <SelectValue />
            </SelectTrigger>
            <SelectContent>
                {(["string", "number", "boolean", "object", "array"] as SchemaNodeType[]).map((t) => (
                    <SelectItem key={t} value={t} className="text-[13px] font-mono">
                        {t}
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    )
}
function NavigatorRow({
    node,
    depth,
    selectedId,
    onSelect,
    onToggle,
}: {
    node: SchemaNode
    depth: number
    selectedId: string
    onSelect: (id: string) => void
    onToggle: (id: string) => void
}) {
    const selected = node.id === selectedId
    const expandable = node.type === "object" ? node.children.length > 0 : node.type === "array" && !!node.item
    return (
        <div>
            <button
                type="button"
                onClick={() => onSelect(node.id)}
                className={cn(
                    "group flex h-6 w-full items-center gap-1 text-left text-xs transition-colors duration-75",
                    selected ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                )}
                style={{ paddingLeft: depth * 14 + 8 }}
            >
                <span
                    className="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground/50"
                    onClick={(event) => {
                        event.stopPropagation()
                        if (expandable) onToggle(node.id)
                    }}
                >
                    {expandable ? node.expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" /> : <span className="h-1 w-1 rounded-full bg-muted-foreground/30" />}
                </span>
                <span className="min-w-0 truncate">
                    {node.name || (node.type === "array" ? "item" : "field")}
                </span>
                <span className="ml-auto pr-2 text-[10px] font-mono text-muted-foreground/40">
                    {node.type}
                </span>
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
    const promptMentionModal = usePromptMentionModal<
        | { kind: "description"; mentionIndex: number }
        | { kind: "json_schema"; tokenRange: { from: number; to: number } }
        | { kind: "builder_description"; nodeId: string; mentionIndex: number }
    >()
    const [selectedAgentId, setSelectedAgentId] = useState("")
    const [name, setName] = useState("")
    const [description, setDescription] = useState("")
    const [editorMode, setEditorMode] = useState<EditorMode>("builder")
    const [rootNode, setRootNode] = useState<SchemaNode>(() => schemaToNode("input", DEFAULT_AGENT_TOOL_INPUT_SCHEMA, true))
    const [selectedNodeId, setSelectedNodeId] = useState("")
    const [jsonSchemaText, setJsonSchemaText] = useState(JSON.stringify(DEFAULT_AGENT_TOOL_INPUT_SCHEMA, null, 2))
    const [schemaEditorError, setSchemaEditorError] = useState<string | null>(null)
    const [showMoreFields, setShowMoreFields] = useState(false)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const selectedAgent = useMemo(
        () => agents.find((agent) => agent.id === selectedAgentId) ?? null,
        [agents, selectedAgentId]
    )

    const selectedNode = useMemo(() => findNode(rootNode, selectedNodeId) ?? rootNode, [rootNode, selectedNodeId])
    const selectedPath = useMemo(() => findPath(rootNode, selectedNode.id) ?? [rootNode], [rootNode, selectedNode.id])
    const visibleTreeNodes = rootNode.children
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
        setEditorMode("builder")
        setRootNode(nextRoot)
        setSelectedNodeId(nextRoot.children[0]?.id ?? nextRoot.id)
        setJsonSchemaText(JSON.stringify(DEFAULT_AGENT_TOOL_INPUT_SCHEMA, null, 2))
        setSchemaEditorError(null)
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
    const addChildToNode = (nodeId: string, type: SchemaNodeType) => {
        const child = createChild(type)
        setRootNode((current) =>
            updateNode(current, nodeId, (node) => ({
                ...node,
                expanded: true,
                children: [...node.children, child],
            }))
        )
        setSelectedNodeId(child.id)
    }
    const replaceArrayItemOnNode = (nodeId: string, type: SchemaNodeType) => {
        const item = createChild(type, "item")
        item.required = true
        setRootNode((current) =>
            updateNode(current, nodeId, (node) => ({
                ...node,
                expanded: true,
                item,
            }))
        )
        setSelectedNodeId(item.id)
    }
    const removeSelected = () => {
        if (selectedNode.id === rootNode.id) return
        const nextSelected = selectedPath.at(-2)?.id ?? rootNode.children[0]?.id ?? rootNode.id
        setRootNode((current) => removeNode(current, selectedNode.id))
        setSelectedNodeId(nextSelected)
    }
    const handleAddFromMenu = (type: SchemaNodeType) => {
        if (selectedNode.type === "object") {
            addChildToNode(selectedNode.id, type)
            return
        }
        if (selectedNode.type === "array") {
            replaceArrayItemOnNode(selectedNode.id, type)
            return
        }
        const parent = selectedPath.at(-2) ?? rootNode
        if (parent.type === "array") {
            replaceArrayItemOnNode(parent.id, type)
            return
        }
        addChildToNode(parent.id, type)
    }
    const renderSplitTree = () => (
        <div className="grid h-full grid-cols-[200px_minmax(0,1fr)]">
            {/* Tree panel */}
            <div className="flex flex-col min-h-0 border-r border-border/30 bg-muted/20">
                <div className="flex h-7 shrink-0 items-center justify-between px-2.5 border-b border-border/20">
                    <span className="text-[10px] font-semibold text-muted-foreground/50 uppercase tracking-wider">
                        Fields · {visibleTreeNodes.length}
                    </span>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <button
                                type="button"
                                aria-label="Add field"
                                className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground/40 transition-colors hover:bg-accent hover:text-foreground"
                                title="Add field"
                            >
                                <Plus className="h-3 w-3" />
                            </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-36">
                            {(["string", "number", "boolean", "object", "array"] as SchemaNodeType[]).map((type) => (
                                <DropdownMenuItem key={type} onClick={() => handleAddFromMenu(type)} className="text-xs">
                                    Add {type}
                                </DropdownMenuItem>
                            ))}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
                <div className="flex-1 overflow-y-auto overflow-x-hidden py-0.5">
                    {visibleTreeNodes.length === 0 ? (
                        <p className="px-3 py-8 text-center text-[11px] text-muted-foreground/50">No fields</p>
                    ) : (
                        visibleTreeNodes.map((node) => (
                            <NavigatorRow key={node.id} node={node} depth={0} selectedId={selectedNode.id} onSelect={setSelectedNodeId} onToggle={handleToggleExpanded} />
                        ))
                    )}
                </div>
            </div>

            {/* Field editor */}
            <div className="min-h-0 overflow-y-auto">
                {selectedNode.id === rootNode.id ? (
                    <div className="flex h-full items-center justify-center">
                        <p className="text-xs text-muted-foreground/40">Select a field to edit</p>
                    </div>
                ) : (
                    <div className="p-4 space-y-3">
                        <div className="rounded-xl border border-border/40 bg-background/70 p-4 shadow-sm">
                            <div className="flex items-start justify-between gap-3">
                                <div className="space-y-1">
                                    <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground/55">Properties</span>
                                    <p className="text-[12px] text-muted-foreground/70">
                                        Define the selected field using the same contract controls used in node settings.
                                    </p>
                                </div>
                                <button
                                    type="button"
                                    className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[12px] font-medium text-muted-foreground/65 transition-colors hover:bg-destructive/8 hover:text-destructive"
                                    onClick={removeSelected}
                                >
                                    <Trash2 className="h-3.5 w-3.5" />
                                    Remove
                                </button>
                            </div>

                            <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_176px] md:items-start">
                                <div className="space-y-1.5">
                                    <Label className={propertyLabelClassName}>Name</Label>
                                    <Input
                                        aria-label="Name"
                                        value={selectedNode.name}
                                        onChange={(event) => updateSelectedNode({ name: event.target.value })}
                                        placeholder="field_name"
                                        className={propertyControlClassName}
                                    />
                                </div>
                                <div className="space-y-1.5">
                                    <Label className={propertyLabelClassName}>Type</Label>
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

                            <div className="mt-3 space-y-1.5">
                                <Label className={propertyLabelClassName}>Description</Label>
                                <PromptMentionInput
                                    id="selected-field-description"
                                    placeholder="Explain what this field means, when it should be sent, and any constraints."
                                    value={selectedNode.description}
                                    onChange={(description) => updateSelectedNode({ description })}
                                    multiline
                                    className={propertyTextareaClassName}
                                    surface="agent_export.input_schema.description"
                                    onMentionClick={(promptId, mentionIndex) =>
                                        promptMentionModal.openPromptMentionModal(promptId, {
                                            kind: "builder_description",
                                            nodeId: selectedNode.id,
                                            mentionIndex,
                                        })
                                    }
                                />
                            </div>

                            <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg bg-muted/35 px-3 py-2.5">
                                <label className="flex cursor-pointer items-center gap-2 select-none">
                                    <input
                                        type="checkbox"
                                        checked={selectedNode.required}
                                        onChange={(event) => updateSelectedNode({ required: event.target.checked })}
                                        className="h-4 w-4 rounded border-border accent-primary"
                                    />
                                    <span className="text-[13px] font-medium text-foreground/85">Required field</span>
                                </label>

                                {selectedNode.type === "array" ? (
                                    <span className="text-[12px] text-muted-foreground/70">
                                        Array item shape is configured from the tree.
                                    </span>
                                ) : null}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )

    const switchToJson = () => {
        setJsonSchemaText(JSON.stringify(nodeToSchema(rootNode), null, 2))
        setSchemaEditorError(null)
        setEditorMode("json")
    }

    const switchToBuilder = () => {
        try {
            const parsed = JSON.parse(jsonSchemaText)
            const nextRoot = schemaToNode("input", parsed, true)
            setRootNode(nextRoot)
            setSelectedNodeId(nextRoot.children[0]?.id ?? nextRoot.id)
            setSchemaEditorError(null)
            setEditorMode("builder")
        } catch {
            setSchemaEditorError("JSON schema must be valid before switching back to the builder.")
        }
    }
    const handleSubmit = async () => {
        if (!selectedAgentId) {
            setError("Select an agent to export.")
            return
        }

        let inputSchema: Record<string, unknown>
        if (editorMode === "json") {
            try {
                inputSchema = JSON.parse(jsonSchemaText)
                setSchemaEditorError(null)
            } catch {
                setSchemaEditorError("JSON schema must be valid before export.")
                return
            }
        } else {
            inputSchema = nodeToSchema(rootNode)
        }

        setLoading(true)
        setError(null)
        try {
            await agentService.exportAgentTool(selectedAgentId, {
                name: name.trim() || undefined,
                description: description.trim() || undefined,
                input_schema: inputSchema,
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

    const handlePromptFill = useCallback(async (_promptId: string, content: string) => {
        const context = promptMentionModal.context
        if (!context) return
        if (context.kind === "description") {
            setDescription((current) => fillMentionInValue(current, context.mentionIndex, content))
            return
        }
        if (context.kind === "json_schema") {
            setJsonSchemaText((current) => fillPromptMentionJsonToken(current, context.tokenRange, content))
            return
        }
        setRootNode((current) =>
            updateNode(current, context.nodeId, (node) => ({
                ...node,
                description: fillMentionInValue(node.description, context.mentionIndex, content),
            }))
        )
    }, [promptMentionModal.context, setDescription, setJsonSchemaText, setRootNode])
    return (
        <>
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent showCloseButton={false} className="!max-w-[58rem] h-[80vh] flex flex-col p-0 gap-0 overflow-hidden">
                <DialogTitle className="sr-only">Export Agent as Tool</DialogTitle>
                <DialogDescription className="sr-only">
                    Configure the exported tool metadata and input schema before creating it.
                </DialogDescription>

                {/* ── Header group (row + optional description, single bottom border) ── */}
                <div className="shrink-0 border-b border-border/40">
                    {/* Header row */}
                    <div className="flex items-center justify-between gap-2 px-4 py-2">
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                            <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
                                <SelectTrigger size="sm" className="h-7 w-[150px] text-xs border-none bg-muted/40 shadow-none focus:ring-0">
                                    <SelectValue placeholder="Select agent" />
                                </SelectTrigger>
                                <SelectContent>
                                    {agents.length === 0 ? (
                                        <SelectItem value="__no_agents__" disabled>
                                            No agents available
                                        </SelectItem>
                                    ) : (
                                        agents.map((agent) => (
                                            <SelectItem key={agent.id} value={agent.id} className="text-xs">
                                                {agent.name}
                                            </SelectItem>
                                        ))
                                    )}
                                </SelectContent>
                            </Select>
                            <div className="h-3.5 w-px bg-border/50 shrink-0" />
                            <Input
                                aria-label="Tool Name"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                placeholder="Tool name..."
                                className="h-7 text-xs font-medium border-none bg-transparent px-1 focus-visible:ring-0 shadow-none"
                            />
                        </div>

                        <div className="flex items-center gap-1 shrink-0">
                            <Button
                                variant="ghost"
                                size="sm"
                                className={cn(
                                    "h-7 w-7 p-0 text-muted-foreground hover:text-foreground",
                                    showMoreFields && "text-foreground bg-muted"
                                )}
                                onClick={() => setShowMoreFields((v) => !v)}
                                title="Description"
                            >
                                <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", showMoreFields && "rotate-180")} />
                            </Button>

                            <div className="flex items-center gap-0.5 rounded-md bg-muted/50 p-0.5">
                                <button
                                    type="button"
                                    aria-label="Builder"
                                    onClick={() => { if (editorMode === "json") switchToBuilder() }}
                                    className={cn(
                                        "px-2 py-0.5 rounded text-[11px] font-medium transition-colors",
                                        editorMode === "builder"
                                            ? "bg-background text-foreground shadow-sm"
                                            : "text-muted-foreground hover:text-foreground"
                                    )}
                                >
                                    Builder
                                </button>
                                <button
                                    type="button"
                                    aria-label="Edit as JSON"
                                    onClick={() => { if (editorMode === "builder") switchToJson() }}
                                    className={cn(
                                        "px-2 py-0.5 rounded text-[11px] font-medium transition-colors",
                                        editorMode === "json"
                                            ? "bg-background text-foreground shadow-sm"
                                            : "text-muted-foreground hover:text-foreground"
                                    )}
                                >
                                    JSON
                                </button>
                            </div>

                            <div className="h-3.5 w-px bg-border/50 mx-0.5" />

                            <Button
                                size="sm"
                                aria-label="Export Tool"
                                onClick={handleSubmit}
                                disabled={loading || agents.length === 0}
                                className="h-6 gap-1 text-[11px]"
                            >
                                {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wrench className="h-3 w-3" />}
                                Export
                            </Button>

                            <div className="h-3.5 w-px bg-border/50 mx-0.5" />

                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => onOpenChange(false)}
                                className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                            >
                                <X className="h-3.5 w-3.5" />
                            </Button>
                        </div>
                    </div>

                    {/* Description (seamless expand, no border between header and description) */}
                    {showMoreFields && (
                        <div className="px-4 pb-3">
                            <div className="rounded-xl bg-muted/25 p-3">
                                <div className="space-y-1.5">
                                    <Label htmlFor="export-tool-description" className={propertyLabelClassName}>Description</Label>
                                    <PromptMentionInput
                                        id="export-tool-description"
                                        value={description}
                                        onChange={setDescription}
                                        placeholder="Describe what this tool does, what it expects, and what it returns."
                                        className={propertyTextareaClassName}
                                        surface="agent_export.description"
                                        onMentionClick={(promptId, mentionIndex) =>
                                            promptMentionModal.openPromptMentionModal(promptId, { kind: "description", mentionIndex })
                                        }
                                    />
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* ── Error bar ── */}
                {(error || schemaEditorError) && (
                    <div className="text-xs text-destructive bg-destructive/10 px-4 py-1.5 shrink-0">
                        {error || schemaEditorError}
                    </div>
                )}

                {/* ── Main content ── */}
                <div className="flex-1 min-h-0 overflow-hidden">
                    <span className="sr-only">Input Schema</span>
                    {editorMode === "builder" ? (
                        renderSplitTree()
                    ) : (
                        <div className="h-full min-h-0 overflow-hidden p-4">
                            <PromptMentionJsonEditor
                                id="json-schema-editor"
                                aria-label="JSON Schema"
                                className="h-full min-h-0 font-mono text-xs"
                                value={jsonSchemaText}
                                onChange={(value) => {
                                    setJsonSchemaText(value)
                                    setSchemaEditorError(null)
                                }}
                                height="100%"
                                surface="agent_export.input_schema.description"
                                onMentionClick={(promptId, tokenRange) =>
                                    promptMentionModal.openPromptMentionModal(promptId, { kind: "json_schema", tokenRange })
                                }
                            />
                        </div>
                    )}
                </div>

                {/* ── Footer ── */}
                <div className="flex items-center gap-2 px-4 py-1.5 border-t border-border/40 text-[11px] text-muted-foreground shrink-0">
                    <span>{selectedAgent?.name || "—"}</span>
                    <span className="text-muted-foreground/30">·</span>
                    <span>{visibleTreeNodes.length} field{visibleTreeNodes.length !== 1 ? "s" : ""}</span>
                    <span className="text-muted-foreground/30">·</span>
                    <span className="capitalize">{editorMode}</span>
                </div>
            </DialogContent>
        </Dialog>
        <PromptModal
            promptId={promptMentionModal.promptId}
            open={promptMentionModal.open}
            onOpenChange={promptMentionModal.handleOpenChange}
            onFill={handlePromptFill}
        />
        </>
    )
}
