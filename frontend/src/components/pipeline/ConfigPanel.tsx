"use client"

import { useEffect, useState } from "react"
import {
  X,
  AlertCircle,
  Lock,
  FolderInput,
  Scissors,
  Sparkles,
  Database,
  Hash
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { modelsService, LogicalModel } from "@/services/agent-resources"
import {
  PipelineNodeData,
  ConfigFieldSpec,
  OperatorSpec,
  CATEGORY_COLORS
} from "./types"

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  source: FolderInput,
  transform: Scissors,
  embedding: Sparkles,
  storage: Database,
}

interface ConfigPanelProps {
  nodeId: string
  data: PipelineNodeData
  operatorSpec?: OperatorSpec
  onConfigChange: (nodeId: string, config: Record<string, unknown>) => void
  onClose: () => void
}

function ModelSelectField({
  capability,
  value,
  onChange,
}: {
  capability?: string
  value: string
  onChange: (value: unknown) => void
}) {
  const [models, setModels] = useState<LogicalModel[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    async function loadModels() {
      try {
        setIsLoading(true)
        const response = await modelsService.listModels(capability as any)
        setModels(response.models)
      } catch (error) {
        console.error("Failed to load models:", error)
      } finally {
        setIsLoading(false)
      }
    }
    loadModels()
  }, [capability])

  return (
    <Select value={value || ""} onValueChange={onChange}>
      <SelectTrigger className="w-full h-9 text-xs bg-muted/40 border-none rounded-lg focus:ring-1 focus:ring-offset-0">
        <SelectValue placeholder="Select a model..." />
      </SelectTrigger>
      <SelectContent className="rounded-xl border-border/50">
        {isLoading ? (
          <SelectItem value="loading" disabled>
            Loading models...
          </SelectItem>
        ) : models.length === 0 ? (
          <SelectItem value="none" disabled>
            No models found
          </SelectItem>
        ) : (
          models.map((model) => (
            <SelectItem key={model.id} value={model.slug || model.id}>
              <div className="flex flex-col">
                <span className="font-medium text-xs">{model.name}</span>
                <span className="text-[10px] text-muted-foreground">
                  {model.providers?.[0]?.provider} • {model.providers?.[0]?.provider_model_id}
                </span>
              </div>
            </SelectItem>
          ))
        )}
      </SelectContent>
    </Select>
  )
}

function ConfigField({
  field,
  value,
  onChange,
}: {
  field: ConfigFieldSpec
  value: unknown
  onChange: (value: unknown) => void
}) {
  const isSecret = field.field_type === "secret"
  const isSelect = field.field_type === "select"
  const isNumber = field.field_type === "integer" || field.field_type === "float"
  const isBoolean = field.field_type === "boolean"

  const renderInput = () => {
    if (field.field_type === "model_select") {
      return (
        <ModelSelectField
          capability={field.required_capability}
          value={value as string}
          onChange={onChange}
        />
      )
    }

    if (isSelect && field.options) {
      return (
        <select
          className={cn(
            "w-full h-9 px-3 rounded-lg bg-muted/40 border-none text-[13px] appearance-none cursor-pointer",
            "focus:outline-none focus:ring-1 focus:ring-ring"
          )}
          value={(value as string) || (field.default as string) || ""}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Select...</option>
          {field.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
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

    if (isSecret) {
      const secretValue = (value as string) || ""
      const isValidSecret = secretValue.startsWith("$secret:")

      return (
        <div className="space-y-1">
          <div className="relative">
            <Input
              type="text"
              value={secretValue}
              onChange={(e) => onChange(e.target.value)}
              placeholder="$secret:my_api_key"
              className={cn(
                "h-9 pl-3 pr-8 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0",
                !isValidSecret && secretValue && "ring-1 ring-destructive"
              )}
            />
            <Lock className="absolute right-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          </div>
          {!isValidSecret && secretValue && (
            <p className="text-[10px] text-destructive flex items-center gap-1 px-1">
              <AlertCircle className="h-3 w-3" />
              Must be a secret reference (e.g., $secret:key)
            </p>
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
        className="h-9 px-3 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40"
      />
    )
  }

  return (
    <div className="space-y-1.5 px-0.5">
      <Label className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">
          {field.name}
        </span>
        {field.required && (
          <span className="text-[9px] font-medium text-foreground/30 px-1 border border-foreground/10 rounded uppercase tracking-wider">
            Required
          </span>
        )}
      </Label>
      {renderInput()}
      {field.description && !isNumber && !isSecret && (
        <p className="text-[10px] text-muted-foreground/60 leading-tight px-1">{field.description}</p>
      )}
    </div>
  )
}

export function ConfigPanel({
  nodeId,
  data,
  operatorSpec,
  onConfigChange,
  onClose,
}: ConfigPanelProps) {
  const [localConfig, setLocalConfig] = useState<Record<string, unknown>>(
    data.config || {}
  )

  useEffect(() => {
    setLocalConfig(data.config || {})
  }, [nodeId, data.config])

  const handleFieldChange = (fieldName: string, value: unknown) => {
    const newConfig = { ...localConfig, [fieldName]: value }
    setLocalConfig(newConfig)
    onConfigChange(nodeId, newConfig)
  }

  const allFields = [
    ...(operatorSpec?.required_config || []),
    ...(operatorSpec?.optional_config || []),
  ]

  const color = CATEGORY_COLORS[data.category]
  const Icon = CATEGORY_ICONS[data.category] || Hash

  return (
    <div className="h-full flex flex-col ">
      <div className="p-3.5 flex items-center justify-between flex-shrink-0">
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

      <div className="flex-1 overflow-y-auto px-3.5 pb-6 space-y-4 scrollbar-none">
        {allFields.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center bg-muted/20 rounded-xl border border-dashed border-border/50">
            <p className="text-[11px] text-muted-foreground font-medium">No parameters to configure</p>
          </div>
        ) : (
          allFields.map((field) => (
            <ConfigField
              key={field.name}
              field={field}
              value={localConfig[field.name]}
              onChange={(value) => handleFieldChange(field.name, value)}
            />
          ))
        )}
      </div>

      <div className="px-3.5 py-4 flex items-center justify-between border-t border-border/10 bg-muted/5">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold text-foreground/40 uppercase tracking-[0.1em]">
            Instance ID
          </span>
          <span className="text-[10px] font-mono text-muted-foreground tabular-nums">
            {nodeId.split("-").pop()}
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-[9px] font-bold text-foreground/40 uppercase tracking-[0.1em]">
            Type
          </span>
          <span className="text-[10px] font-medium text-muted-foreground">
            {data.operator}
          </span>
        </div>
      </div>
    </div>
  )
}
