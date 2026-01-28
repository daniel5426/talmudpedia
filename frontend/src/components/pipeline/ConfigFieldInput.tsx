"use client"

import { useEffect, useState } from "react"
import { AlertCircle, Lock } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { modelsService, LogicalModel } from "@/services/agent-resources"
import { ConfigFieldSpec } from "./types"

export function ModelSelectField({
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

export type FileInputRendererProps = {
  value: string
  onChange: (value: string) => void
}

export type FileInputRenderer = (props: FileInputRendererProps) => React.ReactNode

export function ConfigFieldInput({
  field,
  value,
  onChange,
  renderFileInput,
}: {
  field: ConfigFieldSpec
  value: unknown
  onChange: (value: unknown) => void
  renderFileInput?: FileInputRenderer
}) {
  const isSecret = field.field_type === "secret"
  const isSelect = field.field_type === "select"
  const isNumber = field.field_type === "integer" || field.field_type === "float"
  const isBoolean = field.field_type === "boolean"
  const isFilePath = field.field_type === "file_path"
  const isTextarea = field.field_type === "json" || field.field_type === "code"

  if (isFilePath && renderFileInput) {
    return renderFileInput({
      value: String(value ?? ""),
      onChange: (nextValue) => onChange(nextValue),
    })
  }

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

  if (isTextarea) {
    return (
      <Textarea
        value={(value as string) ?? (field.default as string) ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.placeholder || field.description}
        className="min-h-[120px] bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40 font-mono"
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
      placeholder={field.placeholder || field.description}
      className="h-9 px-3 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40"
    />
  )
}
