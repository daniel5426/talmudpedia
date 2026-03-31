"use client"

import { Fragment, useEffect, useMemo, useState } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { AgentGraphDefinition } from "@/services/agent"

type StateVariable = NonNullable<AgentGraphDefinition["state_contract"]>["variables"][number]

function normalizeListValue(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item ?? "").trim()).filter(Boolean)
}

function schemaTypeOf(schema: unknown): string {
  if (!schema || typeof schema !== "object") return "string"
  const rawType = String((schema as Record<string, unknown>).type || "").trim().toLowerCase()
  if (rawType === "array") return "list"
  if (rawType) return rawType
  if (typeof (schema as Record<string, unknown>).properties === "object") return "object"
  return "string"
}

function ObjectFieldEditor({
  schema,
  value,
  onChange,
  depth = 0,
}: {
  schema: Record<string, unknown>
  value: Record<string, unknown>
  onChange: (value: Record<string, unknown>) => void
  depth?: number
}) {
  const properties = useMemo(
    () =>
      schema.properties && typeof schema.properties === "object"
        ? (schema.properties as Record<string, Record<string, unknown>>)
        : {},
    [schema],
  )

  const updateKey = (key: string, nextValue: unknown) => {
    const next = { ...value }
    const shouldDelete =
      nextValue === undefined ||
      nextValue === "" ||
      (Array.isArray(nextValue) && nextValue.length === 0) ||
      (typeof nextValue === "object" && nextValue !== null && !Array.isArray(nextValue) && Object.keys(nextValue as Record<string, unknown>).length === 0)
    if (shouldDelete) delete next[key]
    else next[key] = nextValue
    onChange(next)
  }

  return (
    <div className="space-y-3">
      {Object.entries(properties).map(([key, propertySchema]) => {
        const propertyType = schemaTypeOf(propertySchema)
        const description = typeof propertySchema.description === "string" ? propertySchema.description : undefined
        const propertyValue = value[key]
        if (propertyType === "object") {
          const nestedValue =
            propertyValue && typeof propertyValue === "object" && !Array.isArray(propertyValue)
              ? (propertyValue as Record<string, unknown>)
              : {}
          return (
            <div
              key={`${depth}-${key}`}
              className="space-y-3 rounded-xl border border-border/50 bg-muted/20 p-3"
              style={{ marginLeft: depth > 0 ? 12 : 0 }}
            >
              <div className="space-y-0.5">
                <p className="text-[12px] font-medium text-foreground">{key}</p>
                {description ? <p className="text-[11px] text-muted-foreground/70">{description}</p> : null}
              </div>
              <ObjectFieldEditor
                schema={propertySchema}
                value={nestedValue}
                onChange={(nextValue) => updateKey(key, nextValue)}
                depth={depth + 1}
              />
            </div>
          )
        }

        if (propertyType === "boolean") {
          return (
            <div key={`${depth}-${key}`} className="space-y-1.5">
              <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">{key}</label>
              <Select
                value={typeof propertyValue === "boolean" ? String(propertyValue) : "__unset__"}
                onValueChange={(next) => {
                  if (next === "__unset__") {
                    updateKey(key, undefined)
                    return
                  }
                  updateKey(key, next === "true")
                }}
              >
                <SelectTrigger className="h-9 rounded-lg border-border/60 bg-background/80 text-[13px]">
                  <SelectValue placeholder="Use default" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__unset__">Use default</SelectItem>
                  <SelectItem value="true">True</SelectItem>
                  <SelectItem value="false">False</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )
        }

        if (propertyType === "number") {
          return (
            <div key={`${depth}-${key}`} className="space-y-1.5">
              <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">{key}</label>
              <Input
                type="number"
                value={typeof propertyValue === "number" ? String(propertyValue) : ""}
                onChange={(event) => {
                  const raw = event.target.value.trim()
                  updateKey(key, raw ? Number(raw) : undefined)
                }}
                placeholder={description || "Enter number"}
                className="h-9 rounded-lg border-border/60 bg-background/80 text-[13px]"
              />
            </div>
          )
        }

        if (propertyType === "list") {
          const listValue = normalizeListValue(propertyValue)
          return (
            <div key={`${depth}-${key}`} className="space-y-1.5">
              <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">{key}</label>
              <Textarea
                value={listValue.join("\n")}
                onChange={(event) => {
                  const next = event.target.value
                    .split("\n")
                    .map((item) => item.trim())
                    .filter(Boolean)
                  updateKey(key, next.length > 0 ? next : undefined)
                }}
                placeholder={description || "One item per line"}
                className="min-h-[88px] rounded-lg border-border/60 bg-background/80 text-[13px]"
              />
            </div>
          )
        }

        return (
          <div key={`${depth}-${key}`} className="space-y-1.5">
            <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">{key}</label>
            <Input
              value={typeof propertyValue === "string" ? propertyValue : ""}
              onChange={(event) => updateKey(key, event.target.value.trim() ? event.target.value : undefined)}
              placeholder={description || `Enter ${key}`}
              className="h-9 rounded-lg border-border/60 bg-background/80 text-[13px]"
            />
          </div>
        )
      })}
    </div>
  )
}

function StateField({
  variable,
  value,
  onChange,
}: {
  variable: StateVariable
  value: unknown
  onChange: (value: unknown) => void
}) {
  const [listDraft, setListDraft] = useState("")
  const type = String(variable.type || "string")
  const listValue = normalizeListValue(value)

  useEffect(() => {
    if (type !== "list") setListDraft("")
  }, [type])

  if (type === "boolean") {
    return (
      <div className="space-y-1.5">
        <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">{variable.key}</label>
        <Select
          value={typeof value === "boolean" ? String(value) : "__unset__"}
          onValueChange={(next) => onChange(next === "__unset__" ? undefined : next === "true")}
        >
          <SelectTrigger className="h-9 rounded-lg border-border/60 bg-background/80 text-[13px]">
            <SelectValue placeholder="Use default" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__unset__">Use default</SelectItem>
            <SelectItem value="true">True</SelectItem>
            <SelectItem value="false">False</SelectItem>
          </SelectContent>
        </Select>
      </div>
    )
  }

  if (type === "number") {
    return (
      <div className="space-y-1.5">
        <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">{variable.key}</label>
        <Input
          type="number"
          value={typeof value === "number" ? String(value) : ""}
          onChange={(event) => {
            const raw = event.target.value.trim()
            onChange(raw ? Number(raw) : undefined)
          }}
          placeholder={variable.description || "Enter number"}
          className="h-9 rounded-lg border-border/60 bg-background/80 text-[13px]"
        />
      </div>
    )
  }

  if (type === "list") {
    return (
      <div className="space-y-2">
        <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">{variable.key}</label>
        {listValue.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {listValue.map((item, index) => (
              <button
                key={`${item || "item"}:${index}`}
                type="button"
                onClick={() => onChange(listValue.filter((_, entryIndex) => entryIndex !== index))}
                className="rounded-full border border-border/60 bg-background/90 px-2.5 py-1 text-[11px] text-foreground/80"
              >
                {item}
              </button>
            ))}
          </div>
        ) : null}
        <Input
          value={listDraft}
          onChange={(event) => setListDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return
            event.preventDefault()
            const nextItem = listDraft.trim()
            if (!nextItem) return
            onChange([...listValue, nextItem])
            setListDraft("")
          }}
          placeholder={variable.description || "Type a value and press Enter"}
          className="h-9 rounded-lg border-border/60 bg-background/80 text-[13px]"
        />
      </div>
    )
  }

  if (type === "object") {
    const objectValue =
      value && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : {}
    const schema = variable.schema && typeof variable.schema === "object" ? variable.schema : { type: "object", properties: {} }
    return (
      <div className="space-y-2">
        <div className="space-y-0.5">
          <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">{variable.key}</label>
          {variable.description ? <p className="text-[11px] text-muted-foreground/70">{variable.description}</p> : null}
        </div>
        <div className="rounded-xl border border-border/50 bg-muted/20 p-3">
          <ObjectFieldEditor schema={schema} value={objectValue} onChange={onChange as (value: Record<string, unknown>) => void} />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">{variable.key}</label>
      <Input
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value.trim() ? event.target.value : undefined)}
        placeholder={variable.description || "Enter value"}
        className="h-9 rounded-lg border-border/60 bg-background/80 text-[13px]"
      />
    </div>
  )
}

export function WorkflowStateSettingsDialog({
  open,
  onOpenChange,
  stateVariables,
  values,
  onChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  stateVariables: StateVariable[]
  values: Record<string, unknown>
  onChange: (values: Record<string, unknown>) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl rounded-2xl border border-border/60 bg-background p-0 shadow-xl">
        <DialogTitle className="sr-only">Workflow state inputs</DialogTitle>
        <DialogDescription className="sr-only">Set per-run state values before submitting the workflow.</DialogDescription>
        <div className="space-y-4 p-5">
          <div className="space-y-0.5">
            <h2 className="text-[15px] font-semibold text-foreground">Workflow state</h2>
            <p className="text-[11px] text-muted-foreground/70">These values seed state for the next run only.</p>
          </div>

          {stateVariables.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/60 bg-muted/20 px-4 py-6 text-center text-[12px] text-muted-foreground/70">
              No state variables declared for this workflow.
            </div>
          ) : (
            <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
              {stateVariables.map((variable, index) => (
                <Fragment key={`${variable.key || "state"}:${index}`}>
                  <StateField
                    variable={variable}
                    value={values[variable.key]}
                    onChange={(nextValue) => {
                      const next = { ...values }
                      const shouldDelete =
                        nextValue === undefined ||
                        nextValue === "" ||
                        (Array.isArray(nextValue) && nextValue.length === 0) ||
                        (typeof nextValue === "object" && nextValue !== null && !Array.isArray(nextValue) && Object.keys(nextValue as Record<string, unknown>).length === 0)
                      if (shouldDelete) delete next[variable.key]
                      else next[variable.key] = nextValue
                      onChange(next)
                    }}
                  />
                </Fragment>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between gap-3 border-t border-border/50 pt-3">
            <Button type="button" variant="ghost" size="sm" onClick={() => onChange({})}>
              Clear
            </Button>
            <Button type="button" size="sm" onClick={() => onOpenChange(false)}>
              Done
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
