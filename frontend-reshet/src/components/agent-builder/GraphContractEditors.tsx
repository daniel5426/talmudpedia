"use client"

import { useMemo } from "react"
import { Plus, Trash2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { AgentGraphAnalysis } from "@/services/agent"
import {
  buildDefaultEndOutputBindings,
  buildDefaultEndOutputSchema,
  EndOutputBinding,
  EndOutputSchemaConfig,
  getValueRefGroups,
  isValueRefTypeCompatible,
  normalizeEndConfig,
  normalizeSetStateAssignments,
  normalizeStateVariables,
  SetStateAssignment,
  StateVariableDefinition,
  ValueRef,
} from "./graph-contract"

const STATE_TYPE_OPTIONS = ["string", "number", "boolean", "object", "list"] as const

function encodeValueRef(valueRef?: ValueRef) {
  return valueRef ? JSON.stringify(valueRef) : ""
}

function decodeValueRef(raw: string): ValueRef | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as ValueRef
  } catch {
    return null
  }
}

export function ValueRefPicker({
  analysis,
  value,
  onChange,
  expectedTypes,
}: {
  analysis?: AgentGraphAnalysis | null
  value?: ValueRef | null
  onChange: (value: ValueRef | null) => void
  expectedTypes?: string[]
}) {
  const groups = useMemo(() => getValueRefGroups(analysis), [analysis])
  const selected = encodeValueRef(value || undefined)

  return (
    <select
      value={selected}
      onChange={(event) => onChange(decodeValueRef(event.target.value))}
      className="h-9 w-full rounded-lg border-none bg-muted/40 px-3 text-[13px] focus:outline-none"
    >
      <option value="">Select a value...</option>
      {groups.map((group) => (
        <optgroup key={group.label} label={group.label}>
          {group.options
            .filter((option) => isValueRefTypeCompatible(option.type, expectedTypes))
            .map((option) => (
              <option key={`${group.label}:${option.node_id || "global"}:${option.key}`} value={encodeValueRef(option.value_ref)}>
                {option.label || option.key} [{option.type}]
              </option>
            ))}
        </optgroup>
      ))}
    </select>
  )
}

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
            <div className="text-[13px] font-medium">input_as_text</div>
            <div className="text-[11px] text-muted-foreground">Built-in chat workflow input</div>
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

type SimpleSchemaProperty = {
  key: string
  type: string
  binding?: ValueRef | null
}

function schemaToSimpleRows(schema: Record<string, unknown>, bindings: EndOutputBinding[]): SimpleSchemaProperty[] {
  const properties = (schema.properties as Record<string, Record<string, unknown>>) || {}
  return Object.entries(properties).map(([key, propertySchema]) => ({
    key,
    type: String(propertySchema?.type || "string"),
    binding: bindings.find((binding) => binding.json_pointer === `/${key}`)?.value_ref || null,
  }))
}

function simpleRowsToSchema(rows: SimpleSchemaProperty[], schemaName?: string): EndOutputSchemaConfig {
  return {
    name: schemaName || "workflow_result",
    mode: "simple",
    schema: {
      type: "object",
      additionalProperties: false,
      properties: Object.fromEntries(
        rows
          .filter((row) => row.key.trim())
          .map((row) => [row.key.trim(), { type: row.type }]),
      ),
      required: rows.filter((row) => row.key.trim()).map((row) => row.key.trim()),
    },
  }
}

export function EndContractEditor({
  value,
  analysis,
  onChange,
}: {
  value: unknown
  analysis?: AgentGraphAnalysis | null
  onChange: (value: { output_schema: EndOutputSchemaConfig; output_bindings: EndOutputBinding[] }) => void
}) {
  const normalized = normalizeEndConfig(value)
  const simpleRows = schemaToSimpleRows(normalized.output_schema.schema, normalized.output_bindings)

  const updateSimpleRows = (rows: SimpleSchemaProperty[]) => {
    const outputSchema = simpleRowsToSchema(rows, normalized.output_schema.name)
    const outputBindings = rows
      .filter((row) => row.key.trim() && row.binding)
      .map((row) => ({
        json_pointer: `/${row.key.trim()}`,
        value_ref: row.binding as ValueRef,
      }))
    onChange({ output_schema: outputSchema, output_bindings: outputBindings })
  }

  const setAdvancedSchema = (rawSchema: string) => {
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
      <div className="space-y-2 rounded-xl border border-border/40 bg-muted/20 p-3">
        <Label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">Schema</Label>
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <Input
            value={normalized.output_schema.name || ""}
            onChange={(event) =>
              onChange({
                ...normalized,
                output_schema: { ...normalized.output_schema, name: event.target.value },
              })
            }
            placeholder="workflow_result"
            className="h-8 bg-background/60 text-[12px]"
          />
          <select
            value={normalized.output_schema.mode}
            onChange={(event) =>
              onChange({
                ...normalized,
                output_schema: { ...normalized.output_schema, mode: event.target.value as "simple" | "advanced" },
              })
            }
            className="h-8 rounded-md border border-border/50 bg-background px-2 text-[12px]"
          >
            <option value="simple">Simple</option>
            <option value="advanced">Advanced</option>
          </select>
        </div>

        {normalized.output_schema.mode === "advanced" ? (
          <Textarea
            defaultValue={JSON.stringify(normalized.output_schema.schema || buildDefaultEndOutputSchema().schema, null, 2)}
            onChange={(event) => setAdvancedSchema(event.target.value)}
            className="min-h-[180px] bg-background/60 font-mono text-[12px]"
          />
        ) : (
          <div className="space-y-2">
            {simpleRows.length === 0 ? (
              <div className="text-[11px] text-muted-foreground">No output properties yet.</div>
            ) : (
              simpleRows.map((row, index) => (
                <div key={`end-row-${index}`} className="grid grid-cols-[1.2fr_0.9fr_1.6fr_auto] gap-2 rounded-lg bg-background/60 p-2">
                  <Input
                    value={row.key}
                    onChange={(event) => {
                      const next = [...simpleRows]
                      next[index] = { ...next[index], key: event.target.value }
                      updateSimpleRows(next)
                    }}
                    placeholder="property_name"
                    className="h-8 text-[12px]"
                  />
                  <select
                    value={row.type}
                    onChange={(event) => {
                      const next = [...simpleRows]
                      next[index] = { ...next[index], type: event.target.value }
                      updateSimpleRows(next)
                    }}
                    className="h-8 rounded-md border border-border/50 bg-background px-2 text-[12px]"
                  >
                    {STATE_TYPE_OPTIONS.map((option) => (
                      <option key={option} value={option === "list" ? "array" : option}>
                        {option}
                      </option>
                    ))}
                  </select>
                  <ValueRefPicker
                    analysis={analysis}
                    value={row.binding || undefined}
                    expectedTypes={[row.type === "array" ? "list" : row.type]}
                    onChange={(binding) => {
                      const next = [...simpleRows]
                      next[index] = { ...next[index], binding }
                      updateSimpleRows(next)
                    }}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => updateSimpleRows(simpleRows.filter((_, rowIndex) => rowIndex !== index))}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 text-[11px]"
              onClick={() => updateSimpleRows([...simpleRows, { key: "", type: "string", binding: null }])}
            >
              <Plus className="mr-1 h-3 w-3" />
              Add Property
            </Button>
          </div>
        )}
      </div>

      {normalized.output_schema.mode === "advanced" && (
        <div className="space-y-2 rounded-xl border border-border/40 bg-muted/20 p-3">
          <div className="flex items-center justify-between">
            <Label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">Bindings</Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-[11px]"
              onClick={() =>
                onChange({
                  ...normalized,
                  output_bindings: [...normalized.output_bindings, { json_pointer: "/", value_ref: buildDefaultEndOutputBindings()[0].value_ref }],
                })
              }
            >
              <Plus className="mr-1 h-3 w-3" />
              Add
            </Button>
          </div>
          {normalized.output_bindings.map((binding, index) => (
            <div key={`binding-${index}`} className="grid grid-cols-[1fr_1.4fr_auto] gap-2 rounded-lg bg-background/60 p-2">
              <Input
                value={binding.json_pointer}
                onChange={(event) => {
                  const next = [...normalized.output_bindings]
                  next[index] = { ...next[index], json_pointer: event.target.value }
                  onChange({ ...normalized, output_bindings: next })
                }}
                placeholder="/property"
                className="h-8 text-[12px]"
              />
              <ValueRefPicker
                analysis={analysis}
                value={binding.value_ref}
                onChange={(valueRef) => {
                  const next = [...normalized.output_bindings]
                  next[index] = { ...next[index], value_ref: valueRef || buildDefaultEndOutputBindings()[0].value_ref }
                  onChange({ ...normalized, output_bindings: next })
                }}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() =>
                  onChange({
                    ...normalized,
                    output_bindings: normalized.output_bindings.filter((_, bindingIndex) => bindingIndex !== index),
                  })
                }
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function SetStateAssignmentsEditor({
  value,
  analysis,
  onChange,
}: {
  value: unknown
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
