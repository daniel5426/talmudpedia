"use client"

import { useEffect, useState } from "react"
import { X, AlertCircle } from "lucide-react"
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
import { modelsService, toolsService, LogicalModel, ToolDefinition } from "@/services/agent-resources"

interface ConfigPanelProps {
    nodeId: string
    data: AgentNodeData
    onConfigChange: (nodeId: string, config: Record<string, unknown>) => void
    onClose: () => void
}

interface ResourceOption {
    value: string
    label: string
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
                <select
                    className={cn(
                        "w-full h-10 px-3 rounded-md border border-input bg-background text-sm",
                        "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                    )}
                    value={(value as string) || ""}
                    onChange={(e) => onChange(e.target.value)}
                >
                    <option value="">Select a model...</option>
                    {models.map((model) => (
                        <option key={model.value} value={model.value}>
                            {model.label}
                        </option>
                    ))}
                </select>
            )
        }

        if (isTool) {
            return (
                <select
                    className={cn(
                        "w-full h-10 px-3 rounded-md border border-input bg-background text-sm",
                        "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                    )}
                    value={(value as string) || ""}
                    onChange={(e) => onChange(e.target.value)}
                >
                    <option value="">Select a tool...</option>
                    {tools.map((tool) => (
                        <option key={tool.value} value={tool.value}>
                            {tool.label}
                        </option>
                    ))}
                </select>
            )
        }

        if (isRag) {
            // For now, RAG pipelines need to be fetched similarly
            // This is a placeholder - could integrate with pipeline service
            return (
                <Input
                    type="text"
                    value={(value as string) || ""}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder="Enter RAG pipeline ID"
                />
            )
        }

        if (isBoolean) {
            return (
                <div className="flex items-center gap-2">
                    <input
                        type="checkbox"
                        checked={Boolean(value ?? field.default)}
                        onChange={(e) => onChange(e.target.checked)}
                        className="h-4 w-4 rounded border-gray-300"
                    />
                    <span className="text-sm text-muted-foreground">
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
                    className="resize-none"
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
            />
        )
    }

    return (
        <div className="space-y-1.5">
            <Label className="flex items-center gap-2">
                {field.label}
                {field.required && (
                    <Badge variant="outline" className="text-[10px] px-1 py-0">
                        Required
                    </Badge>
                )}
            </Label>
            {renderInput()}
            {field.description && (
                <p className="text-xs text-muted-foreground">{field.description}</p>
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

                setModels(modelsRes.models.map(m => ({ value: m.id, label: m.name })))
                setTools(toolsRes.tools.map(t => ({ value: t.id, label: t.name })))
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

    const borderColor = CATEGORY_COLORS[data.category]

    return (
        <div className="h-full flex flex-col border-l">
            <div
                className="p-4 border-b flex items-center justify-between"
                style={{ borderTopColor: borderColor, borderTopWidth: 3 }}
            >
                <div>
                    <h3 className="font-semibold text-sm">{data.displayName}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                        Configure node settings
                    </p>
                </div>
                <Button variant="ghost" size="icon" onClick={onClose}>
                    <X className="h-4 w-4" />
                </Button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {loading ? (
                    <p className="text-sm text-muted-foreground text-center py-8">
                        Loading resources...
                    </p>
                ) : configFields.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-8">
                        This node has no configurable fields.
                    </p>
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

            <div className="p-4 border-t">
                <div className="text-xs text-muted-foreground">
                    <span className="font-medium">Node Type:</span> {data.nodeType}
                </div>
            </div>
        </div>
    )
}
