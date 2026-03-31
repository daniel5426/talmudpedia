"use client"

import { useEffect, useMemo, useState } from "react"
import { Check, Plus, Trash2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { AgentGraphAnalysis } from "@/services/agent"
import {
  buildDefaultEndOutputSchema,
  EndOutputBinding,
  EndOutputSchemaConfig,
  endSchemaToStructuredProperties,
  normalizeEndConfig,
  normalizeSetStateAssignments,
  normalizeStateVariables,
  SetStateAssignment,
  StateVariableDefinition,
  structuredPropertiesToEndConfig,
  type StructuredPropertyDefinition,
} from "./graph-contract"
import { StructuredPropertyTreeEditor } from "./StructuredPropertyTreeEditor"
import { ValueRefPicker } from "./ValueRefPicker"

const STATE_TYPE_OPTIONS = ["string", "number", "boolean", "object", "list"] as const

export function StartContractEditor({
  value,
  onChange,
}: {
  value: unknown
  onChange: (stateVariables: StateVariableDefinition[]) => void
}) {
  const stateVariables = normalizeStateVariables(value)

  const updateRow = (index: number, patch: Partial<StateVariableDefinition>) => {
    const next = [...stateVariables]
    next[index] = { ...next[index], ...patch }
    onChange(next)
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2 rounded-xl border border-border/40 bg-muted/20 p-3">
        <Label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">Workflow Input</Label>
        <div className="flex items-center justify-between rounded-lg bg-background/60 px-3 py-2">
          <div className="space-y-1">
            <div className="text-[13px] font-medium">text</div>
            <div className="text-[11px] text-muted-foreground">Primary text input for the workflow</div>
          </div>
          <Badge variant="secondary">string</Badge>
        </div>
      </div>

      <div className="space-y-2 rounded-xl border border-border/40 bg-muted/20 p-3">
        <div className="flex items-center justify-between">
          <Label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">State Variables</Label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-[11px]"
            onClick={() => onChange([...stateVariables, { key: "", type: "string" }])}
          >
            <Plus className="mr-1 h-3 w-3" />
            Add
          </Button>
        </div>
        {stateVariables.length === 0 ? (
          <div className="text-[11px] text-muted-foreground">No state variables declared.</div>
        ) : (
          <div className="space-y-2">
            {stateVariables.map((item, index) => (
              <div key={`state-var-${index}`} className="grid grid-cols-[1.4fr_1fr_auto] gap-2 rounded-lg bg-background/60 p-2">
                <Input
                  value={item.key || ""}
                  onChange={(event) => updateRow(index, { key: event.target.value })}
                  placeholder="variable_key"
                  className="h-8 bg-transparent text-[12px]"
                />
                <select
                  value={item.type}
                  onChange={(event) => updateRow(index, { type: event.target.value as StateVariableDefinition["type"] })}
                  className="h-8 rounded-md border border-border/50 bg-background px-2 text-[12px]"
                >
                  {STATE_TYPE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => onChange(stateVariables.filter((_, rowIndex) => rowIndex !== index))}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
                <Textarea
                  value={item.default_value == null ? "" : JSON.stringify(item.default_value)}
                  onChange={(event) => {
                    const raw = event.target.value.trim()
                    if (!raw) {
                      updateRow(index, { default_value: undefined })
                      return
                    }
                    try {
                      updateRow(index, { default_value: JSON.parse(raw) })
                    } catch {
                      updateRow(index, { default_value: raw })
                    }
                  }}
                  placeholder="Optional default value"
                  className="col-span-3 min-h-[56px] bg-transparent text-[12px]"
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function EndContractEditor({
  value,
  nodeId,
  analysis,
  onChange,
}: {
  value: unknown
  nodeId?: string | null
  analysis?: AgentGraphAnalysis | null
  onChange: (value: { output_schema: EndOutputSchemaConfig; output_bindings: EndOutputBinding[] }) => void
}) {
  const normalized = normalizeEndConfig(value)
  const simpleRowsSignature = useMemo(
    () =>
      JSON.stringify({
        schema: normalized.output_schema.schema,
        bindings: normalized.output_bindings,
      }),
    [normalized.output_schema.schema, normalized.output_bindings],
  )
  const advancedSchemaSignature = useMemo(
    () => JSON.stringify(normalized.output_schema.schema || buildDefaultEndOutputSchema().schema, null, 2),
    [normalized.output_schema.schema],
  )
  const [simpleRows, setSimpleRows] = useState<StructuredPropertyDefinition[]>(() =>
    endSchemaToStructuredProperties(normalized.output_schema.schema, normalized.output_bindings),
  )
  const [advancedDraft, setAdvancedDraft] = useState(advancedSchemaSignature)

  useEffect(() => {
    setSimpleRows(endSchemaToStructuredProperties(normalized.output_schema.schema, normalized.output_bindings))
  }, [simpleRowsSignature])

  useEffect(() => {
    setAdvancedDraft(advancedSchemaSignature)
  }, [advancedSchemaSignature])

  const updateSimpleRows = (rows: StructuredPropertyDefinition[]) => {
    setSimpleRows(rows)
    onChange(structuredPropertiesToEndConfig(rows, normalized.output_schema.name))
  }

  const setAdvancedSchema = (rawSchema: string) => {
    setAdvancedDraft(rawSchema)
    try {
      const parsed = JSON.parse(rawSchema)
      onChange({
        output_schema: {
          ...normalized.output_schema,
          mode: "advanced",
          schema: parsed,
        },
        output_bindings: normalized.output_bindings,
      })
    } catch {
      // Keep invalid JSON local-only until the next valid parse.
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-0.5">
          <h2 className="text-[13px] font-semibold text-foreground">Structured output (JSON)</h2>
          <p className="text-[10px] text-muted-foreground/60">
            The model will generate a JSON object that matches this schema.
          </p>
        </div>
        <div className="rounded-lg bg-muted/40 p-0.5">
          <div className="grid grid-cols-2 gap-0.5">
            {(["simple", "advanced"] as const).map((mode) => {
              const active = normalized.output_schema.mode === mode
              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() =>
                    onChange({
                      ...normalized,
                      output_schema: { ...normalized.output_schema, mode },
                    })
                  }
                  className={`rounded-md px-3 py-1.5 text-[11px] font-medium transition ${
                    active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground/60"
                  }`}
                >
                  {mode[0].toUpperCase() + mode.slice(1)}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {normalized.output_schema.mode === "advanced" ? (
        <div className="space-y-3">
          <Textarea
            value={advancedDraft}
            onChange={(event) => setAdvancedSchema(event.target.value)}
            className="min-h-[280px] resize-none rounded-lg bg-muted/40 border-none px-3 py-2.5 font-mono text-[13px] leading-6 shadow-none focus-visible:ring-1 focus-visible:ring-offset-0"
          />
        </div>
      ) : (
        <div className="space-y-3">
          <div className="space-y-1.5 px-0.5">
            <Label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">Name</Label>
            <Input
              value={normalized.output_schema.name || ""}
              onChange={(event) =>
                onChange({
                  ...normalized,
                  output_schema: { ...normalized.output_schema, name: event.target.value },
                })
              }
              placeholder="workflow_result"
              className="h-9 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40"
            />
          </div>

          <div className="space-y-2">
            <Label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50 px-0.5">Properties</Label>
            <StructuredPropertyTreeEditor
              properties={simpleRows}
              mode="value"
              nodeId={nodeId}
              analysis={analysis}
              onChange={updateSimpleRows}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export function SetStateAssignmentsEditor({
  value,
  nodeId,
  analysis,
  onChange,
}: {
  value: unknown
  nodeId?: string | null
  analysis?: AgentGraphAnalysis | null
  onChange: (assignments: SetStateAssignment[]) => void
}) {
  const assignments = normalizeSetStateAssignments(value)

  const updateRow = (index: number, patch: Partial<SetStateAssignment>) => {
    const next = [...assignments]
    next[index] = { ...next[index], ...patch }
    onChange(next)
  }

  return (
    <div className="space-y-2 rounded-xl border border-border/40 bg-muted/20 p-3">
      <div className="flex items-center justify-between">
        <Label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">Assignments</Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 text-[11px]"
          onClick={() => onChange([...assignments, { key: "", type: "string" }])}
        >
          <Plus className="mr-1 h-3 w-3" />
          Add
        </Button>
      </div>

      {assignments.length === 0 ? (
        <div className="text-[11px] text-muted-foreground">No assignments declared.</div>
      ) : (
        <div className="space-y-2">
          {assignments.map((assignment, index) => {
            const sourceMode = assignment.value_ref ? "value_ref" : "literal"
            return (
              <div key={`set-state-${index}`} className="space-y-2 rounded-lg bg-background/60 p-2">
                <div className="grid grid-cols-[1.1fr_0.8fr_0.95fr_auto] gap-2">
                  <Input
                    value={assignment.key || ""}
                    onChange={(event) => updateRow(index, { key: event.target.value })}
                    placeholder="state_key"
                    className="h-8 text-[12px]"
                  />
                  <select
                    value={assignment.type || "string"}
                    onChange={(event) => updateRow(index, { type: event.target.value as SetStateAssignment["type"] })}
                    className="h-8 rounded-md border border-border/50 bg-background px-2 text-[12px]"
                  >
                    {STATE_TYPE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                  <select
                    value={sourceMode}
                    onChange={(event) =>
                      updateRow(
                        index,
                        event.target.value === "value_ref"
                          ? { value: undefined, value_ref: assignment.value_ref || undefined }
                          : { value_ref: undefined, value: assignment.value ?? "" },
                      )
                    }
                    className="h-8 rounded-md border border-border/50 bg-background px-2 text-[12px]"
                  >
                    <option value="literal">Literal / Expression</option>
                    <option value="value_ref">ValueRef</option>
                  </select>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => onChange(assignments.filter((_, rowIndex) => rowIndex !== index))}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>

                {sourceMode === "value_ref" ? (
                  <ValueRefPicker
                    analysis={analysis}
                    nodeId={nodeId}
                    value={assignment.value_ref || undefined}
                    expectedTypes={assignment.type ? [assignment.type] : undefined}
                    onChange={(valueRef) => updateRow(index, { value_ref: valueRef || undefined, value: undefined })}
                  />
                ) : (
                  <Textarea
                    value={assignment.value == null ? "" : typeof assignment.value === "string" ? assignment.value : JSON.stringify(assignment.value)}
                    onChange={(event) => {
                      const raw = event.target.value.trim()
                      if (!raw) {
                        updateRow(index, { value: "" })
                        return
                      }
                      try {
                        updateRow(index, { value: JSON.parse(raw), value_ref: undefined })
                      } catch {
                        updateRow(index, { value: raw, value_ref: undefined })
                      }
                    }}
                    placeholder="Literal value or CEL expression"
                    className="min-h-[56px] bg-transparent text-[12px]"
                  />
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
