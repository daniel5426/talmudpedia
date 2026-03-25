"use client"

import { useEffect, useMemo, useState, type ReactNode } from "react"
import { Plus, Settings2, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { PromptMentionInput } from "../shared/PromptMentionInput"
import type { AgentGraphAnalysis } from "@/services/agent"
import { EndContractEditor, ValueRefPicker } from "./GraphContractEditors"
import {
  EndOutputBinding,
  EndOutputSchemaConfig,
  normalizeEndConfig,
  normalizeStateVariables,
  StateVariableDefinition,
} from "./graph-contract"

type ResourceOption = {
  value: string
  label: string
  providerInfo?: string
  slug?: string
}

const STATE_TYPE_OPTIONS = ["string", "number", "boolean", "object", "list"] as const

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

function parseDraftDefaultValue(raw: string): unknown {
  const trimmed = raw.trim()
  if (!trimmed) return undefined
  try {
    return JSON.parse(trimmed)
  } catch {
    return trimmed
  }
}

export function StartNodeSettings({
  value,
  onChange,
}: {
  value: unknown
  onChange: (stateVariables: StateVariableDefinition[]) => void
}) {
  const stateVariables = normalizeStateVariables(value)
  const [open, setOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [draft, setDraft] = useState<StateVariableDefinition>({ key: "", type: "string" })
  const hasEditingRow = editingIndex !== null

  const openEditor = (index: number | null) => {
    const nextDraft = index != null && stateVariables[index]
      ? { ...stateVariables[index] }
      : { key: "", type: "string" as const }
    setEditingIndex(index)
    setDraft(nextDraft)
    setOpen(true)
  }

  const saveDraft = () => {
    const key = draft.key.trim()
    if (!key) return
    const next = [...stateVariables]
    const normalizedDraft = { ...draft, key }
    if (editingIndex == null) next.push(normalizedDraft)
    else next[editingIndex] = normalizedDraft
    onChange(next)
    setOpen(false)
  }

  return (
    <>
      <div className="space-y-4">
        <EditorIntro description="Define the workflow inputs and any seeded state values for the run." />

        <EditorSection title="Input Variables">
          <VariableRow name="input_as_text" type="string" />
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
                        onClick={() => onChange(stateVariables.filter((_, rowIndex) => rowIndex !== index))}
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
                      onClick={() => setDraft((current) => ({ ...current, type: option }))}
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
                  className="h-9 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">
                  Default Value <span className="font-normal text-foreground/30">Optional</span>
                </label>
                <Textarea
                  value={
                    draft.default_value == null
                      ? ""
                      : typeof draft.default_value === "string"
                        ? draft.default_value
                        : JSON.stringify(draft.default_value, null, 2)
                  }
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      default_value: parseDraftDefaultValue(event.target.value),
                    }))
                  }
                  placeholder="New variable"
                  className="resize-none min-h-[60px] bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setOpen(false)} className="h-8 rounded-lg px-3 text-[12px]">
                Cancel
              </Button>
              <Button type="button" onClick={saveDraft} className="h-8 rounded-lg px-3 text-[12px]">
                Save
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

export function EndNodeSettings({
  value,
  analysis,
  onChange,
  isConfigured = false,
}: {
  value: unknown
  analysis?: AgentGraphAnalysis | null
  onChange: (value: { output_schema: EndOutputSchemaConfig; output_bindings: EndOutputBinding[] }) => void
  isConfigured?: boolean
}) {
  const normalized = normalizeEndConfig(value)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(normalized)

  useEffect(() => {
    setDraft(normalized)
  }, [value])

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

      <Dialog
        open={open}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) setDraft(normalizeEndConfig(value))
          setOpen(nextOpen)
        }}
      >
        <DialogContent
          showCloseButton={false}
          className="w-[min(96vw,1180px)] max-w-[1180px] rounded-xl border border-border/50 bg-background p-0 shadow-lg"
          onPointerDownOutside={(event) => {
            const target = event.target as HTMLElement | null
            if (target?.closest("[data-value-ref-picker-portal='true']")) {
              event.preventDefault()
            }
          }}
          onInteractOutside={(event) => {
            const target = event.target as HTMLElement | null
            if (target?.closest("[data-value-ref-picker-portal='true']")) {
              event.preventDefault()
            }
          }}
        >
          <DialogTitle className="sr-only">Structured output</DialogTitle>
          <DialogDescription className="sr-only">
            Configure the JSON schema and bindings returned by the End node.
          </DialogDescription>
          <div className="max-h-[min(86vh,920px)] overflow-auto p-4">
            <EndContractEditor value={draft} analysis={analysis} onChange={setDraft} />
          </div>
          <div className="flex items-center justify-between border-t border-border/30 px-4 py-3">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
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
                setDraft(nextSchema)
              }}
              className="h-8 rounded-lg px-3 text-[12px] text-muted-foreground hover:text-foreground"
            >
              Generate
            </Button>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setDraft(normalizeEndConfig(value))
                  setOpen(false)
                }}
                className="h-8 rounded-lg px-3 text-[12px]"
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={() => {
                  onChange(draft)
                  setOpen(false)
                }}
                className="h-8 rounded-lg px-3 text-[12px]"
              >
                {isConfigured ? "Save" : "Add"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
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
            <select
              value={String(value.model_id || "")}
              onChange={(event) => onChange({ ...value, model_id: event.target.value })}
              className="h-9 w-full rounded-lg bg-muted/40 border-none px-3 text-[13px] text-foreground outline-none focus:ring-1 focus:ring-offset-0"
            >
              <option value="">Select model</option>
              {models.map((model) => (
                <option key={model.value} value={model.value}>
                  {model.label}
                </option>
              ))}
            </select>
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
