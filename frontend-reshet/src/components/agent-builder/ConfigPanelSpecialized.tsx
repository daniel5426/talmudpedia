"use client"

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { Plus, Settings2, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Checkbox } from "@/components/ui/checkbox"
import { Textarea } from "@/components/ui/textarea"
import { PromptMentionInput } from "../shared/PromptMentionInput"
import type { AgentGraphAnalysis, AgentGraphDefinition } from "@/services/agent"
import { StructuredSchemaDialog } from "./StructuredSchemaDialog"
import { ValueRefPicker } from "./ValueRefPicker"
import {
  endSchemaToStructuredProperties,
  EndOutputBinding,
  EndOutputSchemaConfig,
  normalizeEndConfig,
  normalizeStateVariables,
  stateVariableObjectSchemaToStructuredProperties,
  StateVariableDefinition,
  type StructuredPropertyDefinition,
  structuredPropertiesToEndConfig,
  structuredPropertiesToObjectSchema,
} from "./graph-contract"

type ResourceOption = {
  value: string
  label: string
  providerInfo?: string
  slug?: string
}

const STATE_TYPE_OPTIONS = ["string", "number", "boolean", "object", "list"] as const
const CANONICAL_WORKFLOW_INPUT_ORDER = ["text", "files", "audio", "images"] as const

function EditorIntro({ description }: { description: string }) {
  return <p className="text-[10px] text-muted-foreground/60 leading-tight px-0.5">{description}</p>
}

function EditorSection({
  title,
  action,
  children,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 px-0.5">
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground/70 font-semibold">{title}</p>
        {action}
      </div>
      {children}
    </div>
  )
}

function FormRow({
  label,
  children,
}: {
  label: string
  align?: "center" | "start"
  children: ReactNode
}) {
  return (
    <div className="space-y-1.5 px-0.5">
      <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">{label}</label>
      {children}
    </div>
  )
}

function VariableRow({
  name,
  type,
  actions,
}: {
  name: string
  type: string
  actions?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg bg-muted/40 px-3 py-2">
      <div className="min-w-0">
        <span className="truncate text-[13px] font-medium text-foreground">{name}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground/60">
          {type}
        </span>
        {actions}
      </div>
    </div>
  )
}

function normalizeListDefaultValue(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item ?? "").trim()).filter(Boolean)
}

export function StartNodeSettings({
  workflowContract,
  stateContract,
  onChange,
}: {
  workflowContract?: AgentGraphDefinition["workflow_contract"]
  stateContract?: AgentGraphDefinition["state_contract"]
  onChange: (value: {
    workflowContract: NonNullable<AgentGraphDefinition["workflow_contract"]>
    stateContract: NonNullable<AgentGraphDefinition["state_contract"]>
  }) => void
}) {
  const workflowInputs = Array.isArray(workflowContract?.inputs) ? workflowContract.inputs : []
  const workflowInputsByKey = useMemo(
    () => new Map(workflowInputs.map((item) => [String(item.key), item])),
    [workflowInputs],
  )
  const orderedWorkflowInputs = useMemo(
    () =>
      CANONICAL_WORKFLOW_INPUT_ORDER.map((key) => workflowInputsByKey.get(key)).filter(
        (item): item is NonNullable<AgentGraphDefinition["workflow_contract"]>["inputs"][number] => !!item,
      ),
    [workflowInputsByKey],
  )
  const stateVariables = normalizeStateVariables(stateContract?.variables)
  const [open, setOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [draft, setDraft] = useState<StateVariableDefinition>({ key: "", type: "string" })
  const [objectSchemaMode, setObjectSchemaMode] = useState<"simple" | "advanced">("simple")
  const [listDraftItem, setListDraftItem] = useState("")
  const [objectSchemaDraft, setObjectSchemaDraft] = useState("[]")
  const [objectSchemaProperties, setObjectSchemaProperties] = useState<StructuredPropertyDefinition[]>([])
  const [objectSchemaOpen, setObjectSchemaOpen] = useState(false)
  const [objectSchemaSnapshot, setObjectSchemaSnapshot] = useState<{
    schema?: Record<string, unknown>
    raw: string
    mode: "simple" | "advanced"
    properties: StructuredPropertyDefinition[]
  } | null>(null)
  const hasEditingRow = editingIndex !== null
  const trimmedDraftKey = draft.key.trim()
  const hasDuplicateKey = trimmedDraftKey
    ? stateVariables.some((item, index) => index !== editingIndex && item.key === trimmedDraftKey)
    : false

  const openEditor = (index: number | null) => {
    const nextDraft = index != null && stateVariables[index]
      ? { ...stateVariables[index] }
      : { key: "", type: "string" as const }
    setEditingIndex(index)
    setDraft(nextDraft)
    const nextStructured = stateVariableObjectSchemaToStructuredProperties(nextDraft.schema)
    setObjectSchemaProperties(nextStructured)
    setObjectSchemaMode("simple")
    setObjectSchemaDraft(JSON.stringify(nextDraft.schema || structuredPropertiesToObjectSchema(nextStructured), null, 2))
    setListDraftItem("")
    setOpen(true)
  }

  const saveDraft = () => {
    const key = trimmedDraftKey
    if (!key || hasDuplicateKey) return
    const next = [...stateVariables]
    const normalizedDraft = { ...draft, key }
    if (editingIndex == null) next.push(normalizedDraft)
    else next[editingIndex] = normalizedDraft
    onChange({
      workflowContract: { inputs: workflowInputs },
      stateContract: { variables: next },
    })
    setOpen(false)
  }

  return (
    <>
      <div className="space-y-4">
        <EditorIntro description="Define the workflow inputs and any seeded state values for the run." />

        <EditorSection title="Input Variables">
          {orderedWorkflowInputs.map((item) => (
            <VariableRow
              key={item.key}
              name={item.label || item.key}
              type={item.type}
              actions={
                <div className="flex items-center gap-2">
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground/60">
                    {item.enabled !== false ? "On" : "Off"}
                  </span>
                  <Checkbox
                    checked={item.enabled !== false}
                    onCheckedChange={(checked: boolean | "indeterminate") =>
                      onChange({
                        workflowContract: {
                          inputs: workflowInputs.map((input) =>
                            input.key === item.key ? { ...input, enabled: checked === true } : input,
                          ),
                        },
                        stateContract: { variables: stateVariables },
                      })
                    }
                    aria-label={`Toggle ${item.label || item.key}`}
                  />
                </div>
              }
            />
          ))}
        </EditorSection>

        <EditorSection
          title="State Variables"
          action={
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => openEditor(null)}
              className="h-7 rounded-lg px-2.5 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <Plus className="mr-1 h-3 w-3" />
              Add
            </Button>
          }
        >
          {stateVariables.length === 0 ? (
            <p className="text-[11px] text-muted-foreground/50 px-0.5 py-2">
              No state variables declared.
            </p>
          ) : (
            <div className="space-y-2">
              {stateVariables.map((item, index) => (
                <VariableRow
                  key={`${item.key}-${index}`}
                  name={item.key}
                  type={item.type}
                  actions={
                    <>
                      <button
                        type="button"
                        onClick={() => openEditor(index)}
                        className="rounded p-1 text-muted-foreground/50 transition hover:text-foreground"
                        aria-label={`Edit ${item.key}`}
                      >
                        <Settings2 className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          onChange({
                            workflowContract: { inputs: workflowInputs },
                            stateContract: { variables: stateVariables.filter((_, rowIndex) => rowIndex !== index) },
                          })
                        }
                        className="rounded p-1 text-muted-foreground/50 transition hover:text-foreground"
                        aria-label={`Delete ${item.key}`}
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </>
                  }
                />
              ))}
            </div>
          )}
        </EditorSection>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          showCloseButton={false}
          className="max-w-md rounded-xl border border-border/50 bg-background p-0 shadow-lg"
        >
          <DialogTitle className="sr-only">{hasEditingRow ? "Edit state variable" : "Add state variable"}</DialogTitle>
          <DialogDescription className="sr-only">
            Configure a typed state variable and optional default value.
          </DialogDescription>
          <div className="space-y-4 p-4">
            <div className="space-y-0.5">
              <h3 className="text-[13px] font-semibold text-foreground">State Variable</h3>
              <p className="text-[10px] text-muted-foreground/60">Choose a type, name it, and optionally seed a default value.</p>
            </div>

            <div className="rounded-lg bg-muted/40 p-0.5">
              <div className="grid grid-cols-5 gap-0.5">
                {STATE_TYPE_OPTIONS.map((option) => {
                  const active = draft.type === option
                  return (
                    <button
                      key={option}
                      type="button"
                      onClick={() =>
                        setDraft((current) => {
                          const next: StateVariableDefinition = { ...current, type: option }
                          if (option === "boolean" && typeof current.default_value !== "boolean") next.default_value = undefined
                          if (option === "number" && typeof current.default_value !== "number") next.default_value = undefined
                          if (option === "list") next.default_value = normalizeListDefaultValue(current.default_value)
                          if (option === "object") next.schema = current.schema || structuredPropertiesToObjectSchema([])
                          return next
                        })
                      }
                      className={`rounded-md px-2 py-1.5 text-[11px] font-medium transition ${
                        active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground/60"
                      }`}
                    >
                      {option[0].toUpperCase() + option.slice(1)}
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">Name</label>
                <Input
                  value={draft.key}
                  onChange={(event) => setDraft((current) => ({ ...current, key: event.target.value }))}
                  placeholder="name"
                  aria-invalid={hasDuplicateKey}
                  className={`h-9 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40 ${
                    hasDuplicateKey ? "ring-1 ring-destructive/70 focus-visible:ring-destructive/70" : ""
                  }`}
                />
                {hasDuplicateKey ? (
                  <p className="text-[10px] text-destructive">A state variable with this key already exists.</p>
                ) : null}
              </div>

              {draft.type === "string" ? (
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">
                    Default Value <span className="font-normal text-foreground/30">Optional</span>
                  </label>
                  <Input
                    value={typeof draft.default_value === "string" ? draft.default_value : ""}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        default_value: event.target.value || undefined,
                      }))
                    }
                    placeholder="Default text"
                    className="h-9 bg-muted/40 border-none rounded-lg text-[13px]"
                  />
                </div>
              ) : null}

              {draft.type === "number" ? (
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">
                    Default Value <span className="font-normal text-foreground/30">Optional</span>
                  </label>
                  <Input
                    type="number"
                    value={typeof draft.default_value === "number" ? String(draft.default_value) : ""}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        default_value: event.target.value === "" ? undefined : Number(event.target.value),
                      }))
                    }
                    placeholder="0"
                    className="h-9 bg-muted/40 border-none rounded-lg text-[13px]"
                  />
                </div>
              ) : null}

              {draft.type === "boolean" ? (
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">
                    Default Value <span className="font-normal text-foreground/30">Optional</span>
                  </label>
                  <Select
                    value={typeof draft.default_value === "boolean" ? String(draft.default_value) : "__unset__"}
                    onValueChange={(value) =>
                      setDraft((current) => ({
                        ...current,
                        default_value: value === "__unset__" ? undefined : value === "true",
                      }))
                    }
                  >
                    <SelectTrigger className="h-9 rounded-lg border-none bg-muted/40 text-[13px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__unset__">No default</SelectItem>
                      <SelectItem value="true">true</SelectItem>
                      <SelectItem value="false">false</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              ) : null}

              {draft.type === "list" ? (
                <div className="space-y-2">
                  <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">
                    Default Value <span className="font-normal text-foreground/30">Optional</span>
                  </label>
                  <Input
                    value={listDraftItem}
                    onChange={(event) => setListDraftItem(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key !== "Enter") return
                      event.preventDefault()
                      const value = listDraftItem.trim()
                      if (!value) return
                      setDraft((current) => ({
                        ...current,
                        default_value: [...normalizeListDefaultValue(current.default_value), value],
                      }))
                      setListDraftItem("")
                    }}
                    placeholder="Type a value and press Enter"
                    className="h-9 bg-muted/40 border-none rounded-lg text-[13px]"
                  />
                  <div className="flex flex-wrap gap-2">
                    {normalizeListDefaultValue(draft.default_value).map((item, index) => (
                      <button
                        key={`${item}-${index}`}
                        type="button"
                        onClick={() =>
                          setDraft((current) => ({
                            ...current,
                            default_value: normalizeListDefaultValue(current.default_value).filter((_, itemIndex) => itemIndex !== index),
                          }))
                        }
                        className="rounded-full bg-muted px-3 py-1 text-[12px] text-foreground/80"
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {draft.type === "object" ? (
                <div className="space-y-3">
                  <div className="space-y-0.5">
                    <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">Object schema</label>
                    <p className="text-[10px] text-muted-foreground/60">Configure the nested structure for this object variable.</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setObjectSchemaSnapshot({
                        schema: (draft.schema as Record<string, unknown> | undefined),
                        raw: objectSchemaDraft,
                        mode: objectSchemaMode,
                        properties: objectSchemaProperties,
                      })
                      setObjectSchemaProperties(stateVariableObjectSchemaToStructuredProperties(draft.schema))
                      setObjectSchemaOpen(true)
                    }}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-muted px-3 text-[12px] font-medium text-foreground/70 transition hover:text-foreground hover:bg-muted/80"
                  >
                    {draft.schema ? "Edit schema" : "Add schema"}
                  </button>
                </div>
              ) : null}
            </div>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setOpen(false)} className="h-8 rounded-lg px-3 text-[12px]">
                Cancel
              </Button>
              <Button type="button" onClick={saveDraft} disabled={!trimmedDraftKey || hasDuplicateKey} className="h-8 rounded-lg px-3 text-[12px]">
                Save
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <StructuredSchemaDialog
        open={objectSchemaOpen}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && objectSchemaSnapshot) {
            setDraft((current) => ({ ...current, schema: objectSchemaSnapshot.schema }))
            setObjectSchemaDraft(objectSchemaSnapshot.raw)
            setObjectSchemaMode(objectSchemaSnapshot.mode)
            setObjectSchemaProperties(objectSchemaSnapshot.properties)
            setObjectSchemaSnapshot(null)
          }
          setObjectSchemaOpen(nextOpen)
        }}
        title="Structured output (JSON)"
        description="Define the JSON shape for this object state variable."
        schemaMode={objectSchemaMode}
        onSchemaModeChange={setObjectSchemaMode}
        properties={objectSchemaProperties}
        onPropertiesChange={(properties) => {
          setObjectSchemaProperties(properties)
          setObjectSchemaDraft(JSON.stringify(structuredPropertiesToObjectSchema(properties), null, 2))
        }}
        advancedDraft={objectSchemaDraft}
        onAdvancedDraftChange={(nextRaw) => {
          setObjectSchemaDraft(nextRaw)
          try {
            const parsed = JSON.parse(nextRaw)
            setObjectSchemaProperties(stateVariableObjectSchemaToStructuredProperties(parsed))
          } catch {
            // keep local draft until valid JSON
          }
        }}
        propertyMode="description"
        showSchemaName={false}
        onCancel={() => {
          if (objectSchemaSnapshot) {
            setDraft((current) => ({ ...current, schema: objectSchemaSnapshot.schema }))
            setObjectSchemaDraft(objectSchemaSnapshot.raw)
            setObjectSchemaMode(objectSchemaSnapshot.mode)
            setObjectSchemaProperties(objectSchemaSnapshot.properties)
            setObjectSchemaSnapshot(null)
          }
          setObjectSchemaOpen(false)
        }}
        onSave={() => {
          if (objectSchemaMode === "advanced") {
            try {
              const parsed = JSON.parse(objectSchemaDraft)
              setDraft((current) => ({ ...current, schema: parsed }))
            } catch {
              setDraft((current) => ({ ...current, schema: structuredPropertiesToObjectSchema(objectSchemaProperties) }))
            }
          } else {
            setDraft((current) => ({ ...current, schema: structuredPropertiesToObjectSchema(objectSchemaProperties) }))
          }
          setObjectSchemaSnapshot(null)
          setObjectSchemaOpen(false)
        }}
      />
    </>
  )
}

export function EndNodeSettings({
  nodeId,
  value,
  analysis,
  onChange,
  isConfigured = false,
}: {
  nodeId?: string | null
  value: unknown
  analysis?: AgentGraphAnalysis | null
  onChange: (value: { output_schema: EndOutputSchemaConfig; output_bindings: EndOutputBinding[] }) => void
  isConfigured?: boolean
}) {
  const normalized = normalizeEndConfig(value)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(normalized)
  const draftRef = useRef(normalized)
  const [simpleRows, setSimpleRows] = useState(() =>
    endSchemaToStructuredProperties(normalized.output_schema.schema, normalized.output_bindings),
  )
  const [advancedDraft, setAdvancedDraft] = useState(
    JSON.stringify(normalized.output_schema.schema || {}, null, 2),
  )

  useEffect(() => {
    setDraft(normalized)
    draftRef.current = normalized
    setSimpleRows(endSchemaToStructuredProperties(normalized.output_schema.schema, normalized.output_bindings))
    setAdvancedDraft(JSON.stringify(normalized.output_schema.schema || {}, null, 2))
  }, [value])

  const updateDraft = (next: { output_schema: EndOutputSchemaConfig; output_bindings: EndOutputBinding[] }) => {
    draftRef.current = next
    setDraft(next)
  }

  const schemaLabel = normalized.output_schema.name?.trim() || "workflow_result"

  return (
    <>
      <div className="space-y-4">
        <EditorIntro description="Choose the authoritative final output returned by the End node." />

        <EditorSection title="Output">
          <div className="flex items-center justify-between gap-2 rounded-lg bg-muted/40 px-3 py-2">
            <div className="space-y-0.5">
              <div className="text-[13px] font-medium text-foreground">Structured output</div>
              <div className="text-[10px] text-muted-foreground/60">JSON payload at workflow completion.</div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-muted px-3 text-[12px] font-medium text-foreground/70 transition hover:text-foreground hover:bg-muted/80"
            >
              {isConfigured ? schemaLabel : "Add schema"}
            </button>
          </div>
        </EditorSection>
      </div>

      <StructuredSchemaDialog
        open={open}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            const fallback = normalizeEndConfig(value)
            setDraft(fallback)
            draftRef.current = fallback
            setSimpleRows(endSchemaToStructuredProperties(fallback.output_schema.schema, fallback.output_bindings))
            setAdvancedDraft(JSON.stringify(fallback.output_schema.schema || {}, null, 2))
          }
          setOpen(nextOpen)
        }}
        title="Structured output (JSON)"
        description="Configure the JSON schema and bindings returned by the End node."
        schemaMode={draft.output_schema.mode}
        onSchemaModeChange={(mode) =>
          updateDraft({
            ...draftRef.current,
            output_schema: { ...draftRef.current.output_schema, mode },
          })
        }
        properties={simpleRows}
        onPropertiesChange={(properties) => {
          setSimpleRows(properties)
          updateDraft(structuredPropertiesToEndConfig(properties, draftRef.current.output_schema.name))
        }}
        advancedDraft={advancedDraft}
        onAdvancedDraftChange={(rawSchema) => {
          setAdvancedDraft(rawSchema)
          try {
            const parsed = JSON.parse(rawSchema)
            updateDraft({
              ...draftRef.current,
              output_schema: {
                ...draftRef.current.output_schema,
                mode: "advanced",
                schema: parsed,
              },
            })
          } catch {
            // keep invalid JSON local-only
          }
        }}
        propertyMode="value"
        schemaName={draft.output_schema.name}
        onSchemaNameChange={(name) =>
          updateDraft({
            ...draftRef.current,
            output_schema: { ...draftRef.current.output_schema, name },
          })
        }
        analysis={analysis}
        nodeId={nodeId}
        resetLabel="Generate"
        onReset={() => {
          const fallback = normalizeEndConfig(value)
          const nextSchema = fallback.output_schema.mode === "advanced"
            ? fallback
            : {
                output_schema: {
                  ...fallback.output_schema,
                  name: fallback.output_schema.name || "workflow_result",
                  mode: "simple" as const,
                  schema: {
                    type: "object",
                    additionalProperties: false,
                    properties: {
                      response: { type: "string" },
                    },
                    required: ["response"],
                  },
                },
                output_bindings: fallback.output_bindings,
              }
          updateDraft(nextSchema)
          setSimpleRows(endSchemaToStructuredProperties(nextSchema.output_schema.schema, nextSchema.output_bindings))
          setAdvancedDraft(JSON.stringify(nextSchema.output_schema.schema || {}, null, 2))
        }}
        onCancel={() => {
          updateDraft(normalizeEndConfig(value))
          setOpen(false)
        }}
        onSave={() => {
          onChange(draftRef.current)
          setOpen(false)
        }}
        saveLabel={isConfigured ? "Save" : "Add"}
      />
    </>
  )
}

export function ClassifyNodeSettings({
  value,
  onChange,
  analysis,
  models,
  inputSourceAllowedTypes,
}: {
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  analysis?: AgentGraphAnalysis | null
  models: ResourceOption[]
  inputSourceAllowedTypes?: string[]
}) {
  const categories = Array.isArray(value.categories) ? (value.categories as Array<Record<string, unknown>>) : []

  return (
    <div className="space-y-4">
      <EditorIntro description="Sort messages into categories with a model using the builder’s declared contracts." />

      <EditorSection title="Configuration">
        <div className="space-y-3">
          <FormRow label="Name">
            <Input
              value={String(value.name || "Classify")}
              onChange={(event) => onChange({ ...value, name: event.target.value })}
              className="h-9 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40"
            />
          </FormRow>

          <FormRow label="Input">
            <ValueRefPicker
              analysis={analysis}
              value={(value.input_source as any) || null}
              expectedTypes={inputSourceAllowedTypes}
              onChange={(next) => onChange({ ...value, input_source: next || undefined })}
            />
          </FormRow>

          <FormRow label="Categories" align="start">
            <div className="space-y-1.5">
              {categories.map((category, index) => (
                <div key={`category-${index}`} className="rounded-lg bg-muted/20 p-2">
                  <div className="flex items-start gap-1.5">
                    <div className="min-w-0 flex-1 space-y-1.5">
                      <Input
                        value={String(category.name || "")}
                        onChange={(event) => {
                          const next = [...categories]
                          next[index] = { ...next[index], name: event.target.value }
                          onChange({ ...value, categories: next })
                        }}
                        placeholder={index === 0 ? "Primary category" : "Category"}
                        className="h-9 text-[13px] placeholder:text-muted-foreground/40"
                      />
                      <PromptMentionInput
                        value={String(category.description || "")}
                        onChange={(description) => {
                          const next = [...categories]
                          next[index] = { ...next[index], description }
                          onChange({ ...value, categories: next })
                        }}
                        placeholder="Category description"
                        surface="classify.categories.description"
                        multiline={false}
                        className="h-9 text-[13px]"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => onChange({ ...value, categories: categories.filter((_, rowIndex) => rowIndex !== index) })}
                      className="mt-1 rounded p-1 text-muted-foreground/50 transition hover:text-foreground"
                      aria-label={`Delete category ${index + 1}`}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              ))}
              <Button
                type="button"
                variant="ghost"
                onClick={() => onChange({ ...value, categories: [...categories, { name: "", description: "" }] })}
                className="h-7 rounded-lg px-2.5 text-[11px] text-muted-foreground hover:text-foreground"
              >
                <Plus className="mr-1 h-3 w-3" />
                Add category
              </Button>
            </div>
          </FormRow>

          <FormRow label="Model">
            <Select
              value={String(value.model_id || "__unset__")}
              onValueChange={(next) => onChange({ ...value, model_id: next === "__unset__" ? "" : next })}
            >
              <SelectTrigger className="h-9 w-full rounded-lg border-none bg-muted/40 text-[13px] shadow-none focus:ring-1 focus:ring-offset-0">
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__unset__">Select model</SelectItem>
                {models.map((model) => (
                  <SelectItem key={model.value} value={model.value}>
                    {model.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormRow>

          <FormRow label="Instructions" align="start">
            <PromptMentionInput
              value={String(value.instructions || "")}
              onChange={(instructions) => onChange({ ...value, instructions })}
              placeholder="Add examples or routing guidance for the classifier."
              surface="classify.instructions"
              className="min-h-[60px] resize-none"
            />
          </FormRow>
        </div>
      </EditorSection>
    </div>
  )
}
