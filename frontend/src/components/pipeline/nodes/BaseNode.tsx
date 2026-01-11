"use client"

import { memo } from "react"
import { Handle, Position, NodeProps } from "@xyflow/react"
import { cn } from "@/lib/utils"
import { AlertCircle, CheckCircle2 } from "lucide-react"
import { PipelineNodeData, CATEGORY_COLORS, getHandleColor } from "../types"

interface BaseNodeProps extends NodeProps {
  data: PipelineNodeData
  icon: React.ReactNode
}

function BaseNodeComponent({ data, selected, icon }: BaseNodeProps) {
  const borderColor = CATEGORY_COLORS[data.category]
  const inputHandleColor = getHandleColor(data.inputType)
  const outputHandleColor = getHandleColor(data.outputType)

  return (
    <div
      className={cn(
        "relative px-4 py-3 rounded-lg border-2 bg-background shadow-sm min-w-[160px]",
        "transition-all duration-200",
        selected && "ring-2 ring-primary ring-offset-2"
      )}
      style={{ borderColor }}
    >
      {data.inputType !== "none" && (
        <Handle
          type="target"
          position={Position.Left}
          className="!w-3 !h-3 !border-2 !border-background"
          style={{ backgroundColor: inputHandleColor }}
        />
      )}

      <div className="flex items-center gap-2">
        <div
          className="p-1.5 rounded-md"
          style={{ backgroundColor: `${borderColor}20` }}
        >
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            {data.category}
          </div>
          <div className="text-sm font-semibold truncate">
            {data.displayName}
          </div>
        </div>
        <div className="flex-shrink-0">
          {data.hasErrors ? (
            <AlertCircle className="h-4 w-4 text-destructive" />
          ) : data.isConfigured ? (
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          ) : (
            <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/30" />
          )}
        </div>
      </div>

      {data.outputType !== "none" && (
        <Handle
          type="source"
          position={Position.Right}
          className="!w-3 !h-3 !border-2 !border-background"
          style={{ backgroundColor: outputHandleColor }}
        />
      )}
    </div>
  )
}

export const BaseNode = memo(BaseNodeComponent)
