"use client"

import {
  X,
  FolderInput,
  Scissors,
  Sparkles,
  Database,
  Hash
} from "lucide-react"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import {
  PipelineNodeData,
  OperatorSpec,
  CATEGORY_COLORS
} from "./types"
import { ConfigFieldInput } from "./ConfigFieldInput"

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  source: FolderInput,
  transform: Scissors,
  embedding: Sparkles,
  storage: Database,
}

interface ConfigPanelProps {
  nodeId: string
  data: PipelineNodeData
  operatorSpec?: OperatorSpec
  onConfigChange: (nodeId: string, config: Record<string, unknown>) => void
  onClose: () => void
}


export function ConfigPanel({
  nodeId,
  data,
  operatorSpec,
  onConfigChange,
  onClose,
}: ConfigPanelProps) {
  const handleFieldChange = (fieldName: string, value: unknown) => {
    const newConfig = { ...(data.config || {}), [fieldName]: value }
    onConfigChange(nodeId, newConfig)
  }

  const allFields = [
    ...(operatorSpec?.required_config || []),
    ...(operatorSpec?.optional_config || []),
  ]

  const color = CATEGORY_COLORS[data.category]
  const Icon = CATEGORY_ICONS[data.category] || Hash

  return (
    <div className="h-full flex flex-col ">
      <div className="p-3.5 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center"
            style={{ backgroundColor: color }}
          >
            <Icon className="h-4 w-4 text-foreground" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-foreground/80 uppercase tracking-tight">{data.displayName}</h3>
            <p className="text-[10px] text-muted-foreground leading-none mt-0.5 uppercase tracking-wider font-medium opacity-50">
              Settings
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="h-8 w-8 rounded-lg text-muted-foreground hover:bg-muted"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-3.5 pb-6 space-y-4 scrollbar-none">
        {allFields.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center bg-muted/20 rounded-xl border border-dashed border-border/50">
            <p className="text-[11px] text-muted-foreground font-medium">No parameters to configure</p>
          </div>
        ) : (
          allFields.map((field) => (
            <div key={field.name} className="space-y-1.5 px-0.5">
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
                value={data.config[field.name]}
                onChange={(value) => handleFieldChange(field.name, value)}
              />
              {field.description && (
                <p className="text-[10px] text-muted-foreground/60 leading-tight px-1">{field.description}</p>
              )}
            </div>
          ))
        )}
      </div>

      <div className="px-3.5 py-4 flex items-center justify-between border-t border-border/10 bg-muted/5">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold text-foreground/40 uppercase tracking-widest">
            Instance ID
          </span>
          <span className="text-[10px] font-mono text-muted-foreground tabular-nums">
            {nodeId.split("-").pop()}
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-[9px] font-bold text-foreground/40 uppercase tracking-widest">
            Type
          </span>
          <span className="text-[10px] font-medium text-muted-foreground">
            {data.operator}
          </span>
        </div>
      </div>
    </div>
  )
}
