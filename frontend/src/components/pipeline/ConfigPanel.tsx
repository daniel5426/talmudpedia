"use client"

import { useEffect, useState } from "react"
import { X, AlertCircle, Lock } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import {
  PipelineNodeData,
  ConfigFieldSpec,
  OperatorSpec,
  CATEGORY_COLORS
} from "./types"

interface ConfigPanelProps {
  nodeId: string
  data: PipelineNodeData
  operatorSpec?: OperatorSpec
  onConfigChange: (nodeId: string, config: Record<string, unknown>) => void
  onClose: () => void
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
    if (isSelect && field.options) {
      return (
        <select
          className={cn(
            "w-full h-10 px-3 rounded-md border border-input bg-background text-sm",
            "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
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
                "pr-8",
                !isValidSecret && secretValue && "border-destructive"
              )}
            />
            <Lock className="absolute right-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          </div>
          {!isValidSecret && secretValue && (
            <p className="text-xs text-destructive flex items-center gap-1">
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
      />
    )
  }

  return (
    <div className="space-y-1.5">
      <Label className="flex items-center gap-2">
        {field.name}
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
            Configure operator settings
          </p>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {allFields.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            This operator has no configurable fields.
          </p>
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

      <div className="p-4 border-t">
        <div className="text-xs text-muted-foreground">
          <span className="font-medium">Operator ID:</span> {data.operator}
        </div>
      </div>
    </div>
  )
}
