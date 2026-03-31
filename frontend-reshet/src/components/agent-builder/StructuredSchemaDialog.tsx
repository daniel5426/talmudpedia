"use client"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { AgentGraphAnalysis } from "@/services/agent"
import type { StructuredPropertyDefinition } from "./graph-contract"
import { StructuredPropertyTreeEditor } from "./StructuredPropertyTreeEditor"

export function StructuredSchemaDialog({
  open,
  onOpenChange,
  title,
  description,
  schemaMode,
  onSchemaModeChange,
  properties,
  onPropertiesChange,
  advancedDraft,
  onAdvancedDraftChange,
  propertyMode,
  schemaName,
  onSchemaNameChange,
  showSchemaName = true,
  analysis,
  nodeId,
  resetLabel,
  onReset,
  onCancel,
  onSave,
  saveLabel = "Save",
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  schemaMode: "simple" | "advanced"
  onSchemaModeChange: (mode: "simple" | "advanced") => void
  properties: StructuredPropertyDefinition[]
  onPropertiesChange: (properties: StructuredPropertyDefinition[]) => void
  advancedDraft: string
  onAdvancedDraftChange: (value: string) => void
  propertyMode: "description" | "value"
  schemaName?: string
  onSchemaNameChange?: (value: string) => void
  showSchemaName?: boolean
  analysis?: AgentGraphAnalysis | null
  nodeId?: string | null
  resetLabel?: string
  onReset?: () => void
  onCancel: () => void
  onSave: () => void
  saveLabel?: string
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="!w-[min(46vw,1160px)] !max-w-[1160px] rounded-xl border border-border/50 bg-background p-0 shadow-lg"
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
        <DialogTitle className="sr-only">{`${title} dialog`}</DialogTitle>
        <DialogDescription className="sr-only">{description}</DialogDescription>
        <div className="max-h-[min(86vh,920px)] overflow-auto p-4">
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-0.5">
                <h2 className="text-[13px] font-semibold text-foreground">{title}</h2>
                <p className="text-[10px] text-muted-foreground/60">{description}</p>
              </div>
              <div className="rounded-lg bg-muted/40 p-0.5">
                <div className="grid grid-cols-2 gap-0.5">
                  {(["simple", "advanced"] as const).map((mode) => {
                    const active = schemaMode === mode
                    return (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => onSchemaModeChange(mode)}
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

            {schemaMode === "advanced" ? (
              <Textarea
                value={advancedDraft}
                onChange={(event) => onAdvancedDraftChange(event.target.value)}
                className="min-h-[280px] resize-none rounded-lg bg-muted/40 border-none px-3 py-2.5 font-mono text-[13px] leading-6 shadow-none focus-visible:ring-1 focus-visible:ring-offset-0"
              />
            ) : (
              <div className="space-y-3">
                {showSchemaName ? (
                  <div className="space-y-1.5 px-0.5">
                    <Label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50">Name</Label>
                    <Input
                      value={schemaName || ""}
                      onChange={(event) => onSchemaNameChange?.(event.target.value)}
                      placeholder="workflow_result"
                      className="h-9 bg-muted/40 border-none rounded-lg text-[13px] focus-visible:ring-1 focus-visible:ring-offset-0 placeholder:text-muted-foreground/40"
                    />
                  </div>
                ) : null}
                <div className="space-y-2">
                  <Label className="text-[11px] font-bold uppercase tracking-tight text-foreground/50 px-0.5">Properties</Label>
                  <StructuredPropertyTreeEditor
                    properties={properties}
                    mode={propertyMode}
                    nodeId={nodeId}
                    analysis={analysis}
                    onChange={onPropertiesChange}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between border-t border-border/30 px-4 py-3">
          <div>
            {onReset && resetLabel ? (
              <Button
                type="button"
                variant="ghost"
                onClick={onReset}
                className="h-8 rounded-lg px-3 text-[12px] text-muted-foreground hover:text-foreground"
              >
                {resetLabel}
              </Button>
            ) : null}
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={onCancel}
              className="h-8 rounded-lg px-3 text-[12px]"
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={onSave}
              className="h-8 rounded-lg px-3 text-[12px]"
            >
              {saveLabel}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
