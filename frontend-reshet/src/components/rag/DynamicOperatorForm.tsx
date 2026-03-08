"use client"

import { useMemo, useState } from "react"
import { ChevronDown, Dot } from "lucide-react"
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
  const [openSteps, setOpenSteps] = useState<string[]>([])

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

  const stepsWithFields = useMemo(
    () => (schema?.steps || []).filter((step) => (step.fields || []).length > 0),
    [schema?.steps]
  )

  const visibleOpenSteps = useMemo(() => {
    if (stepsWithFields.length <= 1) {
      return stepsWithFields.map((step) => step.step_id)
    }
    const validStepIds = new Set(stepsWithFields.map((step) => step.step_id))
    return openSteps.filter((stepId) => validStepIds.has(stepId))
  }, [openSteps, stepsWithFields])

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

  const toggleStep = (stepId: string, nextOpen: boolean) => {
    setOpenSteps((current) =>
      nextOpen ? Array.from(new Set([...current, stepId])) : current.filter((id) => id !== stepId)
    )
  }

  const hasFields = schema?.steps?.some((step) => (step.fields || []).length > 0)
  const hasAdvancedFields = schema?.steps?.some((step) =>
    (step.fields || []).some((field) =>
      field.operator_id === "query_input" && (field.name === "schema" || field.name === "filters")
    )
  )

  const isAdvancedField = (field: ExecutablePipelineInputField) =>
    field.operator_id === "query_input" && (field.name === "schema" || field.name === "filters")

  const renderField = (stepId: string, field: ExecutablePipelineInputField) => (
    <div key={`${stepId}-${field.name}`} className="space-y-1.5 px-0.5">
      <Label className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">
          {field.name}
        </span>
        {field.required && (
          <span className="rounded border border-foreground/10 px-1 text-[9px] font-medium uppercase tracking-wider text-foreground/30">
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
        <p className="px-1 text-[10px] leading-tight text-muted-foreground/60">
          {field.description}
        </p>
      )}
    </div>
  )

  if (!schema || !hasFields) {
    return (
      <div className="text-sm text-muted-foreground">
        No runtime inputs are required for this pipeline.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {Array.from(fieldsByStep.entries()).map(([stepId, fields]) => {
        const step = stepMap.get(stepId)
        const basicFields = fields.filter((field) => !isAdvancedField(field))
        const advancedFields = fields.filter((field) => isAdvancedField(field))
        const inputCount = basicFields.length + advancedFields.length
        const isOpen = visibleOpenSteps.includes(stepId)
        return (
          <Collapsible
            key={stepId}
            open={isOpen}
            onOpenChange={(nextOpen) => toggleStep(stepId, nextOpen)}
            className="overflow-hidden rounded-2xl border border-border/70 bg-gradient-to-br from-background via-muted/15 to-muted/35 shadow-sm"
          >
            <CollapsibleTrigger className="group w-full text-left">
              <div className="flex items-center justify-between gap-3 px-4 py-3.5">
                <div className="min-w-0 space-y-1">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-foreground/65">
                    {step?.operator_display_name || step?.operator_id || "Source Operator"}
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <Dot className="h-3.5 w-3.5 text-foreground/45" />
                    <span>{inputCount} {inputCount === 1 ? "input" : "inputs"}</span>
                  </div>
                </div>
                <div className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-full border border-border/60 bg-background/85 text-muted-foreground shadow-sm transition-transform duration-200",
                  isOpen && "rotate-180"
                )}>
                  <ChevronDown className="h-4 w-4" />
                </div>
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent className="data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down">
              <div className="space-y-4 border-t border-border/60 bg-background/70 px-4 py-4">
                {basicFields.map((field) => renderField(stepId, field))}
                {showAdvanced && hasAdvancedFields && advancedFields.length > 0 && (
                  <div className="space-y-3 rounded-xl border border-dashed border-border/70 bg-muted/20 p-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Advanced
                    </div>
                    {advancedFields.map((field) => renderField(stepId, field))}
                  </div>
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )
      })}
    </div>
  )
}
