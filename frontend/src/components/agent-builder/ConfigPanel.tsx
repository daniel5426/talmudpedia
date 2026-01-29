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
    Circle
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
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
import { modelsService, toolsService, LogicalModel, ToolDefinition } from "@/services"

const CATEGORY_ICONS: Record<string, React.ElementType> = {
    control: Play,
    reasoning: Brain,
    action: Wrench,
    logic: GitBranch,
    interaction: UserCheck,
    start: Play,
    end: Circle,
    llm: Brain,
    tool: Wrench,
    rag: Search,
    conditional: GitBranch,
    parallel: GitFork,
    human_input: UserCheck,
}

interface ConfigPanelProps {
    nodeId: string
    data: AgentNodeData
    onConfigChange: (nodeId: string, config: Record<string, unknown>) => void
    onClose: () => void
}

interface ResourceOption {
    value: string
    label: string
    providerInfo?: string
}

function ConfigField({
    field,
    value,
    onChange,
    models,
    tools,
}: {
    field: ConfigFieldSpec
    value: unknown
    onChange: (value: unknown) => void
    models: ResourceOption[]
    tools: ResourceOption[]
}) {
    const isNumber = field.fieldType === "number"
    const isBoolean = field.fieldType === "boolean"
    const isSelect = field.fieldType === "select"
    const isText = field.fieldType === "text"
    const isModel = field.fieldType === "model"
    const isTool = field.fieldType === "tool"
    const isRag = field.fieldType === "rag"

    const renderInput = () => {
        if (isSelect && field.options) {
            return (
                <select
                    className={cn(
                        "w-full h-10 px-3 rounded-md border border-input bg-background text-sm",
                        "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                    )}
                    value={(value as string) || ""}
                    onChange={(e) => onChange(e.target.value)}
                >
                    <option value="">Select...</option>
                    {field.options.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                            {opt.label}
                        </option>
                    ))}
                </select>
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

        if (isRag) {
            return (
                <Input
                    type="text"
                    value={(value as string) || ""}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder="Enter RAG pipeline ID"
                    className="h-9 px-3 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40"
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
                        {value ? "Enabled" : "Disabled"}
                    </span>
                </div>
            )
        }

        if (isText) {
            return (
                <Textarea
                    value={(value as string) ?? field.default ?? ""}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder={field.description}
                    rows={4}
                    className="resize-none min-h-[100px] bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40"
                />
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
}: ConfigPanelProps) {
    const [localConfig, setLocalConfig] = useState<Record<string, unknown>>(
        data.config || {}
    )
    const [models, setModels] = useState<ResourceOption[]>([])
    const [tools, setTools] = useState<ResourceOption[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        setLocalConfig(data.config || {})
    }, [nodeId, data.config])

    // Load available models and tools
    useEffect(() => {
        async function loadResources() {
            setLoading(true)
            try {
                const [modelsRes, toolsRes] = await Promise.all([
                    modelsService.listModels("chat", "active", 0, 100),
                    toolsService.listTools(undefined, "published", 0, 100),
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
            } catch (error) {
                console.error("Failed to load resources:", error)
            } finally {
                setLoading(false)
            }
        }
        loadResources()
    }, [])

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
