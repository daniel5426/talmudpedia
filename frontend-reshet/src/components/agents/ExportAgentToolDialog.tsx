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
function typeAccent(type: SchemaNodeType) {
    return type
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
                    "group flex h-[22px] w-full items-center gap-1 text-left text-[13px] transition-colors duration-75",
                    selected ? "bg-accent text-foreground" : "text-foreground hover:bg-accent"
                )}
                style={{ paddingLeft: depth * 14 + 8 }}
            >
                <span
                    className="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground/60"
                    onClick={(event) => {
                        event.stopPropagation()
                        if (expandable) onToggle(node.id)
                    }}
                >
                    {expandable ? node.expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" /> : <span className="h-1 w-1 rounded-full bg-current/40" />}
                </span>
                <span className="min-w-0 truncate text-sm">
                    {node.name || (node.type === "array" ? "item" : "field")}
                </span>
                <span className="ml-auto pr-2 text-[10px] uppercase tracking-[0.08em] text-muted-foreground/60">
                    {typeAccent(node.type)}
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
    const [selectedAgentId, setSelectedAgentId] = useState("")
    const [name, setName] = useState("")
    const [description, setDescription] = useState("")
    const [editorMode, setEditorMode] = useState<EditorMode>("builder")
    const [rootNode, setRootNode] = useState<SchemaNode>(() => schemaToNode("input", DEFAULT_AGENT_TOOL_INPUT_SCHEMA, true))
    const [selectedNodeId, setSelectedNodeId] = useState("")
    const [jsonSchemaText, setJsonSchemaText] = useState(JSON.stringify(DEFAULT_AGENT_TOOL_INPUT_SCHEMA, null, 2))
    const [schemaEditorError, setSchemaEditorError] = useState<string | null>(null)
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
        <div className="grid gap-3 md:grid-cols-[220px_minmax(0,1fr)]">
            <div className="flex max-h-[320px] flex-col overflow-hidden rounded-md border border-border/60">
                <div className="flex h-[32px] shrink-0 items-center justify-between border-b border-border/60 pl-3 pr-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground/60">
                        {visibleTreeNodes.length} fields
                    </span>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <button
                                type="button"
                                aria-label="Add field"
                                className="flex h-[22px] w-[22px] items-center justify-center rounded-[3px] text-muted-foreground/60 transition-colors hover:bg-accent hover:text-foreground"
                                title="Add field"
                            >
                                <Plus className="h-[14px] w-[14px]" />
                            </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-40">
                            {(["string", "number", "boolean", "object", "array"] as SchemaNodeType[]).map((type) => (
                                <DropdownMenuItem key={type} onClick={() => handleAddFromMenu(type)}>
                                    Add {type}
                                </DropdownMenuItem>
                            ))}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
                <div className="flex-1 overflow-y-auto overflow-x-hidden py-0.5">
                    {visibleTreeNodes.length === 0 ? (
                        <p className="px-2 py-4 text-center text-xs text-muted-foreground">No fields yet.</p>
                    ) : (
                        visibleTreeNodes.map((node) => (
                            <NavigatorRow key={node.id} node={node} depth={0} selectedId={selectedNode.id} onSelect={setSelectedNodeId} onToggle={handleToggleExpanded} />
                        ))
                    )}
                </div>
            </div>
            <div className="min-h-0">
                {selectedNode.id === rootNode.id ? (
                    <div className="flex h-full items-center justify-center rounded-md border border-dashed border-border/40 px-3 py-6 text-sm text-muted-foreground">
                        Select a field to edit its properties.
                    </div>
                ) : (
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <span className="text-xs font-medium text-muted-foreground">
                                {selectedNode.name || selectedNode.type}
                            </span>
                            <button
                                type="button"
                                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-destructive transition-colors"
                                onClick={removeSelected}
                            >
                                <Trash2 className="h-3 w-3" />
                                Remove
                            </button>
                        </div>
                        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_120px]">
                            <div className="space-y-1">
                                <Label htmlFor="selected-field-name" className="text-xs">Name</Label>
                                <Input
                                    id="selected-field-name"
                                    value={selectedNode.name}
                                    onChange={(event) => updateSelectedNode({ name: event.target.value })}
                                />
                            </div>
                            <div className="space-y-1">
                                <Label className="text-xs">Type</Label>
                                <div className="rounded-md border border-input">
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
                        </div>
                        <div className="space-y-1">
                            <Label htmlFor="selected-field-description" className="text-xs">Description</Label>
                            <Input
                                id="selected-field-description"
                                placeholder="What this field is for..."
                                value={selectedNode.description}
                                onChange={(event) => updateSelectedNode({ description: event.target.value })}
                            />
                        </div>
                        <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer select-none">
                            <input
                                type="checkbox"
                                checked={selectedNode.required}
                                onChange={(event) => updateSelectedNode({ required: event.target.checked })}
                                className="rounded"
                            />
                            Required
                        </label>
                        {selectedNode.type === "array" ? (
                            <p className="text-xs text-muted-foreground">
                                Array items are configured via the add menu in the tree.
                            </p>
                        ) : null}
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
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[860px] max-h-[88vh] overflow-hidden border-border bg-background shadow-2xl">
                <DialogHeader className="px-2">
                    <DialogTitle>Export Agent as Tool</DialogTitle>
                    <DialogDescription>
                        Create or refresh an owner-managed tool from an agent.
                    </DialogDescription>
                </DialogHeader>

                <div className="max-h-[calc(88vh-11rem)] space-y-4 overflow-y-auto py-2 p-2">
                    <div className="grid gap-3 md:grid-cols-[200px_minmax(0,1fr)]">
                        <div className="space-y-1.5">
                            <Label htmlFor="export-agent-select">Agent</Label>
                            <Select
                                value={selectedAgentId}
                                onValueChange={setSelectedAgentId}
                            >
                                <SelectTrigger id="export-agent-select" className="h-9 w-full">
                                    <SelectValue placeholder="Select an agent" />
                                </SelectTrigger>
                                <SelectContent>
                                    {agents.length === 0 ? (
                                        <SelectItem value="__no_agents__" disabled>
                                            No agents available
                                        </SelectItem>
                                    ) : (
                                    agents.map((agent) => (
                                        <SelectItem key={agent.id} value={agent.id}>
                                            {agent.name}
                                        </SelectItem>
                                    ))
                                    )}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="export-tool-name">Tool Name</Label>
                            <Input id="export-tool-name" value={name} onChange={(event) => setName(event.target.value)} />
                        </div>
                    </div>

                    <div className="space-y-1.5">
                        <Label htmlFor="export-tool-description">Description</Label>
                        <Textarea
                            id="export-tool-description"
                            value={description}
                            onChange={(event) => setDescription(event.target.value)}
                            placeholder="Describe what this tool does..."
                            className="min-h-[72px] resize-none text-sm"
                        />
                    </div>

                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <Label className="text-sm">Input Schema</Label>
                            <button
                                type="button"
                                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                                onClick={editorMode === "builder" ? switchToJson : switchToBuilder}
                            >
                                {editorMode === "builder" ? "Edit as JSON" : "Back to builder"}
                            </button>
                        </div>

                        {editorMode === "builder" ? (
                            renderSplitTree()
                        ) : (
                            <Textarea
                                id="json-schema-editor"
                                aria-label="JSON Schema"
                                className="min-h-[360px] font-mono text-xs"
                                value={jsonSchemaText}
                                onChange={(event) => {
                                    setJsonSchemaText(event.target.value)
                                    setSchemaEditorError(null)
                                }}
                            />
                        )}

                        {schemaEditorError ? <div className="text-sm text-destructive">{schemaEditorError}</div> : null}
                    </div>

                    {error ? (
                        <div className="rounded-lg bg-destructive/8 px-3 py-2 text-sm text-destructive">
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
