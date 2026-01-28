"use client"

import { useMemo } from "react"
import { Label } from "@/components/ui/label"
import { ConfigFieldInput, FileInputRendererProps } from "@/components/pipeline/ConfigFieldInput"
import {
  ExecutablePipelineInputField,
  ExecutablePipelineInputSchema,
  ExecutablePipelineInputStep,
} from "@/components/pipeline/types"
import { FileUploadInput } from "@/components/rag/FileUploadInput"

interface DynamicOperatorFormProps {
  schema: ExecutablePipelineInputSchema | null
  values: Record<string, Record<string, unknown>>
  onChange: (values: Record<string, Record<string, unknown>>) => void
  onUploadFile: (file: File) => Promise<string>
  disabled?: boolean
}

export function DynamicOperatorForm({
  schema,
  values,
  onChange,
  onUploadFile,
  disabled,
}: DynamicOperatorFormProps) {
  const stepMap = useMemo(() => {
    const map = new Map<string, ExecutablePipelineInputStep>()
    schema?.steps?.forEach((step) => {
      map.set(step.step_id, step)
    })
    return map
  }, [schema?.steps])

  const fieldsByStep = useMemo(() => {
    const grouped = new Map<string, ExecutablePipelineInputField[]>()
    schema?.steps?.forEach((step) => {
      grouped.set(step.step_id, step.fields || [])
    })
    return grouped
  }, [schema?.steps])

  const setFieldValue = (stepId: string, name: string, value: unknown) => {
    const stepValues = values[stepId] || {}
    onChange({
      ...values,
      [stepId]: {
        ...stepValues,
        [name]: value,
      },
    })
  }

  const getFileAccept = (config: Record<string, unknown>) => {
    const raw = typeof config.file_extensions === "string"
      ? config.file_extensions
      : typeof config.allowed_extensions === "string"
        ? config.allowed_extensions
        : undefined
    if (!raw) return undefined
    const extensions = raw
      .split(",")
      .map((ext) => ext.trim())
      .filter(Boolean)
      .map((ext) => (ext.startsWith(".") ? ext : `.${ext}`))
    return extensions.length ? extensions.join(",") : undefined
  }

  const renderFileInput = (stepId: string): ((props: FileInputRendererProps) => React.ReactNode) => {
    const step = stepMap.get(stepId)
    const accept = step ? getFileAccept(step.config || {}) : undefined
    return function FileInput({ value, onChange }: FileInputRendererProps) {
      return (
        <FileUploadInput
          value={value}
          accept={accept}
          disabled={disabled}
          onChange={onChange}
          onUpload={onUploadFile}
        />
      )
    }
  }

  const hasFields = schema?.steps?.some((step) => (step.fields || []).length > 0)

  if (!schema || !hasFields) {
    return (
      <div className="text-sm text-muted-foreground">
        No runtime inputs are required for this pipeline.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {Array.from(fieldsByStep.entries()).map(([stepId, fields]) => {
        const step = stepMap.get(stepId)
        return (
          <div key={stepId} className="space-y-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-foreground/60">
              {step?.operator_display_name || step?.operator_id || "Source Operator"}
            </div>
            <div className="space-y-4">
              {fields.map((field) => (
                <div key={`${stepId}-${field.name}`} className="space-y-1.5 px-0.5">
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
                  <ConfigFieldInput
                    field={field}
                    value={values[stepId]?.[field.name]}
                    onChange={(value) => setFieldValue(stepId, field.name, value)}
                    renderFileInput={renderFileInput(stepId)}
                  />
                  {field.description && (
                    <p className="text-[10px] text-muted-foreground/60 leading-tight px-1">
                      {field.description}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
