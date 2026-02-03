"use client"

import { useEffect, useState } from "react"
import {
    X,
    FolderInput,
    Scissors,
    Sparkles,
    Database,
    Hash,
    Play,
    Brain,
    Wrench,
    Search,
    GitBranch,
    GitFork,
    UserCheck,
    Circle,
    Plus,
    Trash2,
    RefreshCw,
    Bot,
    ListFilter,
    Check,
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { cn } from "@/lib/utils"
import {
    AgentNodeData,
    ConfigFieldSpec,
    CATEGORY_COLORS,
    getNodeSpec
} from "./types"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { modelsService, toolsService, ragAdminService, LogicalModel, ToolDefinition } from "@/services"
import { useTenant } from "@/contexts/TenantContext"
import { KnowledgeStoreSelect } from "../shared/KnowledgeStoreSelect"
import { RetrievalPipelineSelect } from "../shared/RetrievalPipelineSelect"


const CATEGORY_ICONS: Record<string, React.ElementType> = {
    control: Play,
    reasoning: Brain,
    action: Wrench,
    logic: GitBranch,
    interaction: UserCheck,
    data: Database,
    start: Play,
    end: Circle,
    llm: Brain,
    agent: Bot,
    tool: Wrench,
    rag: Search,
    conditional: GitBranch,
    if_else: GitBranch,
    while: RefreshCw,
    parallel: GitFork,
    human_input: UserCheck,
    user_approval: UserCheck,
    transform: Sparkles,
    set_state: Database,
    classify: ListFilter,
}

interface ConfigPanelProps {
    nodeId: string
    data: AgentNodeData
    onConfigChange: (nodeId: string, config: Record<string, unknown>) => void
    onClose: () => void
    availableVariables?: any[]
}

interface ResourceOption {
    value: string
    label: string
    providerInfo?: string
}

function SmartInput({
    value,
    onChange,
    placeholder,
    className,
    multiline = false,
    availableVariables = []
}: {
    value: string
    onChange: (val: string) => void
    placeholder?: string
    className?: string
    multiline?: boolean
    availableVariables?: any[]
}) {
    const [showSuggestions, setShowSuggestions] = useState(false)
    const [cursorPosition, setCursorPosition] = useState(0)
    const [searchTerm, setSearchTerm] = useState("")
    const [selectedIndex, setSelectedIndex] = useState(0)

    // Handle input change and detect {{
    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const val = e.target.value
        const pos = e.target.selectionStart || 0
        onChange(val)
        setCursorPosition(pos)

        // Detect {{ pattern
        const textBeforeCursor = val.slice(0, pos)
        const match = textBeforeCursor.match(/{{([^{}]*)$/)

        if (match) {
            setShowSuggestions(true)
            setSearchTerm(match[1])
            setSelectedIndex(0)
        } else {
            setShowSuggestions(false)
        }
    }

    const filteredVariables = availableVariables?.filter(v =>
        v.name.toLowerCase().includes(searchTerm.toLowerCase())
    ) || []

    const insertVariable = (varName: string) => {
        const textBeforeCursor = value.slice(0, cursorPosition)
        const textAfterCursor = value.slice(cursorPosition)
        const match = textBeforeCursor.match(/{{([^{}]*)$/)

        if (match) {
            const prefix = textBeforeCursor.slice(0, match.index! + 2) // keep {{
            const newText = prefix + varName + "}}" + textAfterCursor
            onChange(newText)
            setShowSuggestions(false)
            // Ideally we'd reset cursor too but simple onChange is okay for now
        }
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (!showSuggestions || filteredVariables.length === 0) return

        if (e.key === "ArrowDown") {
            e.preventDefault()
            setSelectedIndex(i => (i + 1) % filteredVariables.length)
        } else if (e.key === "ArrowUp") {
            e.preventDefault()
            setSelectedIndex(i => (i - 1 + filteredVariables.length) % filteredVariables.length)
        } else if (e.key === "Enter" || e.key === "Tab") {
            e.preventDefault()
            insertVariable(filteredVariables[selectedIndex].name)
        } else if (e.key === "Escape") {
            setShowSuggestions(false)
        }
    }

    const Component = multiline ? Textarea : Input

    return (
        <div className="relative">
            <Component
                value={value}
                onChange={handleChange}
                onKeyDown={(e) => {
                    e.stopPropagation()
                    handleKeyDown(e)
                }}
                placeholder={placeholder}
                className={className}
                onBlur={() => setShowSuggestions(false)}
                rows={multiline ? 4 : 1}
            />
            {showSuggestions && filteredVariables.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-popover text-popover-foreground shadow-md rounded-md border border-border p-1 max-h-[200px] overflow-auto">
                    {filteredVariables.map((v, idx) => (
                        <div
                            key={v.name}
                            className={cn(
                                "flex items-center justify-between px-2 py-1.5 text-xs rounded-sm cursor-pointer",
                                idx === selectedIndex ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                            )}
                            onMouseDown={(e) => {
                                e.preventDefault()
                                insertVariable(v.name)
                            }}
                        >
                            <div className="flex items-center gap-2">
                                <Hash className="h-3 w-3 opacity-50" />
                                <span className="font-medium">{v.name}</span>
                            </div>
                            <span className="text-[10px] opacity-50">{v.type || "any"}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

function SearchableResourceInput({
    value,
    onChange,
    placeholder,
    className,
    resources = []
}: {
    value: string
    onChange: (val: string) => void
    placeholder?: string
    className?: string
    resources: Array<{ value: string; label: string; info?: string }>
}) {
    const [showSuggestions, setShowSuggestions] = useState(false)
    const [selectedIndex, setSelectedIndex] = useState(0)

    // Get the label for the current value
    const selectedResource = resources.find(r => r.value === value)
    const [query, setQuery] = useState(selectedResource?.label || "")
    const [isFocused, setIsFocused] = useState(false)

    // Sync query when value changes and we are not typing
    useEffect(() => {
        if (!isFocused) {
            setQuery(selectedResource?.label || value || "")
        }
    }, [value, selectedResource, isFocused])

    const filteredResources = resources.filter(r =>
        r.label.toLowerCase().includes(query.toLowerCase()) ||
        r.value.toLowerCase().includes(query.toLowerCase())
    )

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (!showSuggestions || filteredResources.length === 0) {
            e.stopPropagation()
            return
        }

        if (e.key === "ArrowDown") {
            e.preventDefault()
            e.stopPropagation()
            setSelectedIndex(i => (i + 1) % filteredResources.length)
        } else if (e.key === "ArrowUp") {
            e.preventDefault()
            e.stopPropagation()
            setSelectedIndex(i => (i - 1 + filteredResources.length) % filteredResources.length)
        } else if (e.key === "Enter" || e.key === "Tab") {
            e.preventDefault()
            e.stopPropagation()
            const selected = filteredResources[selectedIndex]
            onChange(selected.value)
            setQuery(selected.label)
            setShowSuggestions(false)
        } else if (e.key === "Escape") {
            e.stopPropagation()
            setShowSuggestions(false)
        } else {
            e.stopPropagation()
        }
    }

    return (
        <div className="relative">
            <div className="relative">
                <Input
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value)
                        setShowSuggestions(true)
                    }}
                    onFocus={() => {
                        setIsFocused(true)
                        setShowSuggestions(true)
                    }}
                    onKeyDown={handleKeyDown}
                    placeholder={placeholder}
                    className={cn(className, "pr-8")}
                    onBlur={() => {
                        setIsFocused(false)
                        setShowSuggestions(false)
                    }}
                />
                {query && (
                    <button
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground/40 hover:text-muted-foreground"
                        onClick={() => {
                            setQuery("")
                            onChange("")
                        }}
                    >
                        <X className="h-3 w-3" />
                    </button>
                )}
            </div>
            {showSuggestions && filteredResources.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-popover text-popover-foreground shadow-md rounded-md border border-border p-1 max-h-[200px] overflow-auto">
                    {filteredResources.map((r, idx) => (
                        <div
                            key={r.value}
                            className={cn(
                                "flex flex-col px-2 py-1.5 text-xs rounded-sm cursor-pointer",
                                idx === selectedIndex ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                            )}
                            onMouseDown={(e) => {
                                e.preventDefault()
                                onChange(r.value)
                                setQuery(r.label)
                                setShowSuggestions(false)
                            }}
                        >
                            <div className="flex items-center justify-between">
                                <span className="font-medium">{r.label}</span>
                                {r.value === value && <Check className="h-3 w-3 text-primary" />}
                            </div>
                            <span className="text-[10px] opacity-50 font-mono truncate">{r.value}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

// Helper to render list editors
function ListEditor({
    items,
    onChange,
    fields,
    addItemLabel = "Add Item",
    availableVariables
}: {
    items: any[]
    onChange: (items: any[]) => void
    fields: { key: string; label: string; placeholder?: string; type?: "text" | "select" | "expression"; options?: string[] }[]
    addItemLabel?: string
    availableVariables?: any[]
}) {
    const handleAdd = () => {
        const newItem: any = {}
        fields.forEach(f => newItem[f.key] = "")
        onChange([...(items || []), newItem])
    }

    const handleRemove = (index: number) => {
        const newItems = [...(items || [])]
        newItems.splice(index, 1)
        onChange(newItems)
    }

    const handleChange = (index: number, key: string, value: string) => {
        const newItems = [...(items || [])]
        newItems[index] = { ...newItems[index], [key]: value }
        onChange(newItems)
    }

    return (
        <div className="space-y-2">
            {(items || []).map((item, idx) => (
                <div key={idx} className="flex gap-2 items-start group">
                    <div className="flex-1 grid gap-2" style={{ gridTemplateColumns: `repeat(${fields.length}, 1fr)` }}>
                        {fields.map(field => (
                            <div key={field.key} className="min-w-0">
                                {field.type === "select" ? (
                                    <select
                                        className="w-full h-8 px-2 rounded-md border border-input bg-background/50 text-[11px] focus:outline-none focus:ring-1 focus:ring-ring"
                                        value={item[field.key] || ""}
                                        onChange={(e) => handleChange(idx, field.key, e.target.value)}
                                    >
                                        <option value="">{field.placeholder || "Select..."}</option>
                                        {field.options?.map(opt => (
                                            <option key={opt} value={opt}>{opt}</option>
                                        ))}
                                    </select>
                                ) : (
                                    <SmartInput
                                        className={cn(
                                            "h-8 px-2 text-[11px] bg-background/50",
                                            field.type === "expression" && "font-mono text-blue-600"
                                        )}
                                        placeholder={field.placeholder || field.label}
                                        value={item[field.key] || ""}
                                        onChange={(val) => handleChange(idx, field.key, val)}
                                        availableVariables={field.type === "expression" ? availableVariables : undefined}
                                        multiline={false}
                                    />
                                )}
                            </div>
                        ))}
                    </div>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive shrink-0"
                        onClick={() => handleRemove(idx)}
                    >
                        <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                </div>
            ))}
            <Button
                variant="outline"
                size="sm"
                onClick={handleAdd}
                className="w-full h-8 text-xs border-dashed text-muted-foreground hover:text-foreground"
            >
                <Plus className="h-3 w-3 mr-1.5" />
                {addItemLabel}
            </Button>
        </div>
    )
}

function ConfigField({
    field,
    value,
    onChange,
    models,
    tools,
    namespaces,
    availableVariables
}: {
    field: ConfigFieldSpec
    value: unknown
    onChange: (value: unknown) => void
    models: ResourceOption[]
    tools: ResourceOption[]
    namespaces: ResourceOption[]
    availableVariables?: any[]
}) {
    const isNumber = field.fieldType === "number"
    const isBoolean = field.fieldType === "boolean"
    const isSelect = field.fieldType === "select"
    const isText = field.fieldType === "text"
    const isModel = field.fieldType === "model"
    const isTool = field.fieldType === "tool"
    const isRag = field.fieldType === "rag"
    const isKnowledgeStore = field.fieldType === "knowledge_store" || field.fieldType === "knowledge_store_select"
    const isRetrievalPipelineSelect = field.fieldType === "retrieval_pipeline_select"

    // New types
    const isExpression = field.fieldType === "expression" || field.fieldType === "template_string"
    const isVariableList = field.fieldType === "variable_list"
    const isCategoryList = field.fieldType === "category_list"
    const isConditionList = field.fieldType === "condition_list"
    const isMappingList = field.fieldType === "mapping_list"
    const isAssignmentList = field.fieldType === "assignment_list"
    const isToolList = field.fieldType === "tool_list"
    const isVariableSelector = field.fieldType === "variable_selector"

    const renderInput = () => {
        if (isSelect && field.options) {
            return (
                <Select value={(value as string) || ""} onValueChange={onChange}>
                    <SelectTrigger className="w-full h-9 text-[13px] bg-muted/40 border-none rounded-lg focus:ring-1 focus:ring-offset-0">
                        <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl border-border/50">
                        {field.options.map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>
                                {opt.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            )
        }

        if (isModel) {
            return (
                <Select value={(value as string) || ""} onValueChange={onChange}>
                    <SelectTrigger className="w-full h-9 text-[13px] bg-muted/40 border-none rounded-lg focus:ring-1 focus:ring-offset-0">
                        <SelectValue placeholder="Select a model..." />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl border-border/50">
                        {models.length === 0 ? (
                            <SelectItem value="none" disabled>No models found</SelectItem>
                        ) : (
                            models.map((model) => (
                                <SelectItem key={model.value} value={model.value}>
                                    <div className="flex flex-col text-left">
                                        <span className="font-medium text-xs">{model.label}</span>
                                        <span className="text-[10px] text-muted-foreground">
                                            {model.providerInfo || "AI Model"}
                                        </span>
                                    </div>
                                </SelectItem>
                            ))
                        )}
                    </SelectContent>
                </Select>
            )
        }

        if (isTool) {
            return (
                <Select value={(value as string) || ""} onValueChange={onChange}>
                    <SelectTrigger className="w-full h-9 text-[13px] bg-muted/40 border-none rounded-lg focus:ring-1 focus:ring-offset-0">
                        <SelectValue placeholder="Select a tool..." />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl border-border/50">
                        {tools.length === 0 ? (
                            <SelectItem value="none" disabled>No tools found</SelectItem>
                        ) : (
                            tools.map((tool) => (
                                <SelectItem key={tool.value} value={tool.value}>
                                    <div className="flex flex-col text-left">
                                        <span className="font-medium text-xs">{tool.label}</span>
                                        {tool.providerInfo && (
                                            <span className="text-[10px] text-muted-foreground">
                                                {tool.providerInfo}
                                            </span>
                                        )}
                                    </div>
                                </SelectItem>
                            ))
                        )}
                    </SelectContent>
                </Select>
            )
        }

        if (isKnowledgeStore) {
            return (
                <KnowledgeStoreSelect
                    value={(value as string) || ""}
                    onChange={onChange}
                    className="h-9 pr-8"
                />
            )
        }

        if (isRetrievalPipelineSelect) {
            return (
                <RetrievalPipelineSelect
                    value={(value as string) || ""}
                    onChange={onChange}
                    className="h-9 pr-8"
                />
            )
        }

        if (isRag) {
            return (
                <SearchableResourceInput
                    value={(value as string) || ""}
                    onChange={onChange}
                    placeholder="Search namespaces..."
                    className="h-9 px-3 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40 font-mono"
                    resources={namespaces.map(ns => ({
                        value: ns.value,
                        label: ns.label,
                        info: ns.value
                    }))}
                />
            )
        }

        if (isBoolean) {
            return (
                <div className="flex items-center gap-2 py-1">
                    <input
                        type="checkbox"
                        checked={Boolean(value ?? field.default)}
                        onChange={(e) => onChange(e.target.checked)}
                        className="h-4 w-4 rounded border-border/50 accent-foreground/20"
                    />
                    <span className="text-[13px] text-muted-foreground font-medium">
                        {value === true ? "Enabled" : value === false ? "Disabled" : (field.default ? "Enabled" : "Disabled")}
                    </span>
                </div>
            )
        }

        if (isText || isExpression) {
            return (
                <SmartInput
                    value={(value as string) ?? field.default ?? ""}
                    onChange={(val) => onChange(val)}
                    placeholder={field.description}
                    multiline={true} // SmartInput fields (text, expression, template) should usually be multiline
                    className={cn(
                        "resize-none min-h-[60px] bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40",
                        field.fieldType === "expression" && "font-mono text-blue-600"
                    )}
                    availableVariables={availableVariables}
                />
            )
        }

        if (isVariableList) {
            return (
                <ListEditor
                    items={(value as any[]) || []}
                    onChange={onChange}
                    addItemLabel="Add Variable"
                    fields={[
                        { key: "name", label: "Name", placeholder: "var_name" },
                        { key: "type", label: "Type", type: "select", options: ["string", "number", "boolean", "object", "array"] },
                        { key: "default", label: "Default", placeholder: "Optional value" }
                    ]}
                    availableVariables={availableVariables}
                />
            )
        }

        if (isCategoryList) {
            return (
                <ListEditor
                    items={(value as any[]) || []}
                    onChange={onChange}
                    addItemLabel="Add Category"
                    fields={[
                        { key: "name", label: "Category Name", placeholder: "support" },
                        { key: "description", label: "Description", placeholder: "Requests about support" }
                    ]}
                    availableVariables={availableVariables}
                />
            )
        }

        if (isConditionList) {
            return (
                <ListEditor
                    items={(value as any[]) || []}
                    onChange={onChange}
                    addItemLabel="Add Condition"
                    fields={[
                        { key: "name", label: "Name", placeholder: "high_score" },
                        { key: "expression", label: "Condition (CEL)", placeholder: "state.score > 80", type: "expression" }
                    ]}
                    availableVariables={availableVariables}
                />
            )
        }

        if (isMappingList) {
            return (
                <ListEditor
                    items={(value as any[]) || []}
                    onChange={onChange}
                    addItemLabel="Add Mapping"
                    fields={[
                        { key: "key", label: "Key", placeholder: "output_key" },
                        { key: "value", label: "Value (CEL)", placeholder: "state.input + ' processed'", type: "expression" }
                    ]}
                    availableVariables={availableVariables}
                />
            )
        }

        if (isAssignmentList) {
            return (
                <ListEditor
                    items={(value as any[]) || []}
                    onChange={onChange}
                    addItemLabel="Add Assignment"
                    fields={[
                        { key: "variable", label: "Variable", placeholder: "state.key" },
                        { key: "value", label: "Value", placeholder: "value or expression", type: "expression" }
                    ]}
                    availableVariables={availableVariables}
                />
            )
        }

        if (isToolList) {
            const currentTools = new Set((value as string[]) || []);
            return (
                <div className="space-y-1 bg-muted/40 p-2 rounded-lg max-h-[200px] overflow-y-auto">
                    {tools.length === 0 ? (
                        <div className="text-[11px] text-muted-foreground text-center">No tools available</div>
                    ) : (
                        tools.map(tool => (
                            <div key={tool.value} className="flex items-center space-x-2">
                                <Checkbox
                                    id={`tool-${tool.value}`}
                                    checked={currentTools.has(tool.value)}
                                    onCheckedChange={(checked) => {
                                        const next = new Set(currentTools);
                                        if (checked) next.add(tool.value);
                                        else next.delete(tool.value);
                                        onChange(Array.from(next));
                                    }}
                                />
                                <label
                                    htmlFor={`tool-${tool.value}`}
                                    className="text-xs font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
                                >
                                    {tool.label}
                                    {tool.providerInfo && <span className="ml-1 text-[10px] text-muted-foreground">({tool.providerInfo})</span>}
                                </label>
                            </div>
                        ))
                    )}
                </div>
            )
        }

        if (isVariableSelector) {
            // Smart input for selecting a single variable
            // Basically just text input but with suggestions
            return (
                <SmartInput
                    value={(value as string) || ""}
                    onChange={(val) => onChange(val)}
                    placeholder="Select or type variable name..."
                    className="h-9 px-3 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40 font-mono text-blue-600"
                    availableVariables={availableVariables}
                    multiline={false}
                />
            )
        }

        // Field mapping editor for artifacts
        if (field.fieldType === "field_mapping") {
            const mappings = (value as Record<string, string>) || {}
            const artifactInputs = (field as any).artifactInputs || []

            return (
                <div className="space-y-2 bg-muted/30 rounded-lg p-2">
                    {artifactInputs.length === 0 ? (
                        <div className="text-[11px] text-muted-foreground text-center py-2">
                            No input fields defined for this artifact
                        </div>
                    ) : (
                        artifactInputs.map((input: { name: string; type: string; required?: boolean; description?: string }) => (
                            <div key={input.name} className="space-y-1">
                                <div className="flex items-center justify-between">
                                    <span className="text-[10px] font-bold uppercase tracking-tight text-foreground/60">
                                        {input.name}
                                    </span>
                                    <span className="text-[9px] text-muted-foreground font-mono">
                                        {input.type}{input.required ? " *" : ""}
                                    </span>
                                </div>
                                <SmartInput
                                    value={mappings[input.name] || ""}
                                    onChange={(val) => {
                                        const newMappings = { ...mappings, [input.name]: val }
                                        onChange(newMappings)
                                    }}
                                    placeholder={input.description || `{{ state.field }} or {{ upstream.node.field }}`}
                                    className="h-8 px-2 text-[11px] bg-background/50 font-mono text-blue-600"
                                    availableVariables={availableVariables}
                                    multiline={false}
                                />
                            </div>
                        ))
                    )}
                </div>
            )
        }

        return (
            <Input
                type={isNumber ? "number" : "text"}
                value={(value as string | number) ?? field.default ?? ""}
                onChange={(e) => {
                    const val = isNumber ? Number(e.target.value) : e.target.value
                    onChange(val)
                }}
                placeholder={field.description}
                step={isNumber ? 0.1 : undefined}
                min={isNumber && field.name === "temperature" ? 0 : undefined}
                max={isNumber && field.name === "temperature" ? 1 : undefined}
                className="h-9 px-3 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40"
            />
        )
    }

    return (
        <div className="space-y-1.5 px-0.5">
            <Label className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">
                    {field.label}
                </span>
                {field.required && (
                    <span className="text-[9px] font-medium text-foreground/30 px-1 border border-foreground/10 rounded uppercase tracking-wider">
                        Required
                    </span>
                )}
            </Label>
            {renderInput()}
            {field.description && (
                <p className="text-[10px] text-muted-foreground/60 leading-tight px-1">
                    {field.description}
                </p>
            )}
        </div>
    )
}

export function ConfigPanel({
    nodeId,
    data,
    onConfigChange,
    onClose,
    availableVariables
}: ConfigPanelProps) {
    const [localConfig, setLocalConfig] = useState<Record<string, unknown>>(
        data.config || {}
    )
    const [models, setModels] = useState<ResourceOption[]>([])
    const [tools, setTools] = useState<ResourceOption[]>([])
    const [namespaces, setNamespaces] = useState<ResourceOption[]>([])
    const [loading, setLoading] = useState(true)

    const { currentTenant } = useTenant()

    useEffect(() => {
        setLocalConfig(data.config || {})
    }, [nodeId, data.config])

    // Load available models and tools
    useEffect(() => {
        async function loadResources() {
            setLoading(true)
            try {
                const [modelsRes, toolsRes, pipelinesRes] = await Promise.all([
                    modelsService.listModels("chat", "active", 0, 100),
                    toolsService.listTools(undefined, "published", 0, 100),
                    ragAdminService.listVisualPipelines(currentTenant?.slug)
                ])

                setModels(modelsRes.models.map(m => ({
                    value: m.id,
                    label: m.name,
                    providerInfo: `${m.providers?.[0]?.provider} • ${m.providers?.[0]?.provider_model_id}`
                })))
                setTools(toolsRes.tools.map(t => ({
                    value: t.id,
                    label: t.name,
                    providerInfo: t.implementation_type
                })))
                setNamespaces((pipelinesRes.pipelines || [])
                    .filter(p => p.pipeline_type === "retrieval")
                    .map(p => ({
                        value: p.id,
                        label: p.name || (p as any).slug || "Unnamed Pipeline"
                    })))
            } catch (error) {
                console.error("Failed to load resources:", error)
            } finally {
                setLoading(false)
            }
        }
        loadResources()
    }, [currentTenant?.slug])

    const handleFieldChange = (fieldName: string, value: unknown) => {
        const newConfig = { ...localConfig, [fieldName]: value }
        setLocalConfig(newConfig)
        onConfigChange(nodeId, newConfig)
    }

    const nodeSpec = getNodeSpec(data.nodeType)
    const configFields = nodeSpec?.configFields || []

    const color = CATEGORY_COLORS[data.category]
    const Icon = CATEGORY_ICONS[data.nodeType] || CATEGORY_ICONS[data.category] || Hash

    return (
        <div className="flex flex-col min-w-[320px]">
            <div className="p-3.5 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2.5">
                    <div
                        className="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center"
                        style={{ backgroundColor: color }}
                    >
                        <Icon className="h-4 w-4 text-foreground" />
                    </div>
                    <div>
                        <h3 className="text-xs font-bold text-foreground/80 uppercase tracking-tight">{data.displayName}</h3>
                        <p className="text-[10px] text-muted-foreground leading-none mt-0.5 uppercase tracking-wider font-medium opacity-50">
                            Settings
                        </p>
                    </div>
                </div>
                <Button
                    variant="ghost"
                    size="icon"
                    onClick={onClose}
                    className="h-8 w-8 rounded-lg text-muted-foreground hover:bg-muted"
                >
                    <X className="h-4 w-4" />
                </Button>
            </div>

            <div className="flex-1 overflow-y-auto px-3.5 pb-6 space-y-4 max-h-[60vh] scrollbar-none">
                {loading ? (
                    <p className="text-[11px] text-muted-foreground text-center py-8">
                        Loading resources...
                    </p>
                ) : configFields.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-center bg-muted/20 rounded-xl border border-dashed border-border/50">
                        <p className="text-[11px] text-muted-foreground font-medium">No parameters to configure</p>
                    </div>
                ) : (
                    configFields.map((field) => (
                        <ConfigField
                            key={field.name}
                            field={field}
                            value={localConfig[field.name]}
                            onChange={(value) => handleFieldChange(field.name, value)}
                            models={models}
                            tools={tools}
                            namespaces={namespaces}
                            availableVariables={availableVariables}
                        />
                    ))
                )}
            </div>

            <div className="px-3.5 py-4 flex items-center justify-between border-t border-border/10 bg-muted/5">
                <div className="flex flex-col">
                    <span className="text-[9px] font-bold text-foreground/40 uppercase tracking-widest">
                        Node ID
                    </span>
                    <span className="text-[10px] font-mono text-muted-foreground tabular-nums">
                        {nodeId.split("-").pop()}
                    </span>
                </div>
                <div className="flex flex-col items-end">
                    <span className="text-[9px] font-bold text-foreground/40 uppercase tracking-widest">
                        Type
                    </span>
                    <Badge variant="outline" className="text-[10px] font-mono bg-background/50 py-0 h-4">
                        {data.nodeType}
                    </Badge>
                </div>
            </div>
        </div>
    )
}
