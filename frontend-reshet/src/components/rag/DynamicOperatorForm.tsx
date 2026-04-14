"use client"

import { useMemo, useState, useEffect } from "react"
import { ChevronRight } from "lucide-react"
import { Label } from "@/components/ui/label"
import { ConfigFieldInput, FileInputRendererProps } from "@/components/pipeline/ConfigFieldInput"
import {
  ExecutablePipelineInputField,
  ExecutablePipelineInputSchema,
  ExecutablePipelineInputStep,
} from "@/components/pipeline/types"
import { FileUploadInput } from "@/components/rag/FileUploadInput"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"

interface DynamicOperatorFormProps {
  schema: ExecutablePipelineInputSchema | null
  values: Record<string, Record<string, unknown>>
  onChange: (values: Record<string, Record<string, unknown>>) => void
  onUploadFile: (file: File) => Promise<string>
  showAdvanced?: boolean
  disabled?: boolean
}

export function DynamicOperatorForm({
  schema,
  values,
  onChange,
  onUploadFile,
  showAdvanced = false,
  disabled,
}: DynamicOperatorFormProps) {
  // Track open steps by their ID
  const [openSteps, setOpenSteps] = useState<Set<string>>(new Set())

  const stepsWithFields = useMemo(
    () => (schema?.steps || []).filter((step) => (step.fields || []).length > 0),
    [schema?.steps]
  )

  // Initialize with all steps open by default
  useEffect(() => {
    if (stepsWithFields.length > 0) {
      setOpenSteps(new Set(stepsWithFields.map(s => s.step_id)))
    }
  }, [stepsWithFields])

  const stepMap = useMemo(() => {
    const map = new Map<string, ExecutablePipelineInputStep>()
    schema?.steps?.forEach((step) => {
      map.set(step.step_id, step)
    })
    return map
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

  const getFieldValue = (stepId: string, field: ExecutablePipelineInputField) => {
    if (values[stepId] && field.name in values[stepId]) {
      return values[stepId][field.name]
    }
    const stepConfig = stepMap.get(stepId)?.config || {}
    if (field.name in stepConfig) {
      return stepConfig[field.name]
    }
    return field.default
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

  const toggleStep = (stepId: string) => {
    setOpenSteps((current) => {
      const next = new Set(current)
      if (next.has(stepId)) {
        next.delete(stepId)
      } else {
        next.add(stepId)
      }
      return next
    })
  }

  const isAdvancedField = (field: ExecutablePipelineInputField) =>
    field.operator_id === "query_input" && (field.name === "schema" || field.name === "filters")

  const renderField = (stepId: string, field: ExecutablePipelineInputField) => (
    <div key={`${stepId}-${field.name}`} className="space-y-1.5">
      <Label className="flex items-center justify-between">
        <span className="text-[11px] font-medium text-foreground/70">
          {field.name}
        </span>
        {field.required && (
          <span className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground/30">
            Required
          </span>
        )}
      </Label>
      <ConfigFieldInput
        field={field}
        value={getFieldValue(stepId, field)}
        onChange={(value) => setFieldValue(stepId, field.name, value)}
        renderFileInput={renderFileInput(stepId)}
      />
      {field.description && (
        <p className="text-[10px] leading-tight text-muted-foreground/40">
          {field.description}
        </p>
      )}
    </div>
  )

  if (!schema || stepsWithFields.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <p className="text-[13px] font-medium text-muted-foreground/60">
          No runtime inputs required
        </p>
        <p className="text-xs text-muted-foreground/30 mt-1 px-4 max-w-[240px]">
          This pipeline is ready to run with its pre-configured settings.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3 pb-4">
      {stepsWithFields.map((step) => {
        const stepId = step.step_id
        const fields = step.fields || []
        const basicFields = fields.filter((field) => !isAdvancedField(field))
        const advancedFields = fields.filter((field) => isAdvancedField(field))
        const isOpen = openSteps.has(stepId)
        
        return (
          <div key={stepId} className="flex flex-col gap-0 border border-border/30 rounded-lg bg-background/50 overflow-hidden">
            <button
              onClick={() => toggleStep(stepId)}
              className="flex items-center justify-between gap-3 px-4 py-3 leading-none transition-colors hover:bg-muted/30"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <ChevronRight
                  className={cn(
                    "h-3.5 w-3.5 text-muted-foreground/40 shrink-0 transition-transform duration-200",
                    isOpen && "rotate-90"
                  )}
                />
                <div className="flex flex-col items-start gap-1">
                  <span className="text-[13px] font-semibold text-foreground/80 tracking-tight leading-none">
                    {step?.operator_display_name || step?.operator_id || "Source Operator"}
                  </span>
                  <span className="text-[10px] text-muted-foreground/50 font-medium uppercase tracking-wider leading-none">
                    {fields.length} {fields.length === 1 ? "input" : "inputs"}
                  </span>
                </div>
              </div>
            </button>
            
            {isOpen && (
              <div className="px-4 py-4 border-t border-border/20 space-y-4">
                {basicFields.map((field) => renderField(stepId, field))}
                
                {showAdvanced && advancedFields.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-border/20 space-y-4">
                    <div className="flex items-center gap-2">
                       <div className="h-px flex-1 bg-border/20" />
                       <span className="text-[9px] font-bold uppercase tracking-[0.2em] text-muted-foreground/30">
                         Advanced
                       </span>
                       <div className="h-px flex-1 bg-border/20" />
                    </div>
                    {advancedFields.map((field) => renderField(stepId, field))}
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
