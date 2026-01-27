"use client"

import { memo } from "react"
import { Handle, Position, NodeProps } from "@xyflow/react"
import {
  FolderInput,
  Scissors,
  Sparkles,
  Database,
  Hash,
  ShieldCheck,
  Sparkle,
  ArrowRightLeft,
  Search,
  SortAsc,
  Code,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock
} from "lucide-react"
import { cn } from "@/lib/utils"
import { PipelineNodeData, CATEGORY_COLORS, getHandleColor } from "../types"

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  source: FolderInput,
  normalization: ShieldCheck,
  enrichment: Sparkle,
  chunking: Scissors,
  transform: ArrowRightLeft,
  embedding: Sparkles,
  storage: Database,
  retrieval: Search,
  reranking: SortAsc,
  custom: Code,
}

interface BaseNodeProps extends NodeProps {
  data: PipelineNodeData
  icon?: React.ReactNode
}

function BaseNodeComponent({ data, selected, icon }: BaseNodeProps) {
  const color = CATEGORY_COLORS[data.category]
  const inputHandleColor = getHandleColor(data.inputType)
  const outputHandleColor = getHandleColor(data.outputType)
  const DefaultIcon = CATEGORY_ICONS[data.category] || Hash

  const statusColors = {
    pending: "text-muted-foreground",
    running: "text-blue-500",
    completed: "text-green-500",
    failed: "text-destructive",
    skipped: "text-muted-foreground/50",
  }

  const statusIcons = {
    pending: <Clock className="w-3.5 h-3.5" />,
    running: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
    completed: <CheckCircle2 className="w-3.5 h-3.5" />,
    failed: <XCircle className="w-3.5 h-3.5" />,
    skipped: <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/30" />,
  }

  const statusBorder = {
    running: "border-blue-500 ring-1 ring-blue-500/20",
    failed: "border-destructive ring-1 ring-destructive/20",
    completed: "border-green-500/50",
  }

  return (
    <div
      className={cn(
        "relative min-w-[200px] p-0 rounded-2xl bg-background backdrop-blur-sm transition-all duration-300 border-[0.5px]",
        selected ? "border-primary ring-2 ring-primary/20 selected border-1" : "border-border/70 border-1",
        data.executionStatus && statusBorder[data.executionStatus as keyof typeof statusBorder]
      )}
    >
      {data.inputType !== "none" && (
        <Handle
          type="target"
          position={Position.Left}
          className="!w-4 !h-4 !border-4 !border-background !-left-2 transition-transform hover:scale-125"
          style={{ backgroundColor: inputHandleColor }}
        />
      )}

      <div className="flex items-center p-2.5 gap-2.5">
        <div
          className="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center relative"
          style={{ backgroundColor: color }}
        >
          {/* Status Overlay Icon */}
          {data.executionStatus && data.executionStatus !== 'pending' && (
            <div className={cn(
              "absolute -top-1 -right-1 w-4 h-4 rounded-full bg-background flex items-center justify-center shadow-sm border",
              statusColors[data.executionStatus]
            )}>
              {statusIcons[data.executionStatus]}
            </div>
          )}
          {icon || <DefaultIcon className="h-4 w-4 text-foreground" />}

        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-[13px] font-semibold text-foreground/80 leading-tight truncate">
            {data.displayName}
          </h4>
        </div>

        {/* Subtle dot for configuration status */}
        {!data.isConfigured && !data.executionStatus && (
          <div className="w-1.5 h-1.5 rounded-full bg-amber-400/60 animate-pulse" />
        )}
      </div>

      {data.outputType !== "none" && (
        <Handle
          type="source"
          position={Position.Right}
          className="!w-4 !h-4 !border-4 !border-background !-right-2 transition-transform hover:scale-125"
          style={{ backgroundColor: outputHandleColor }}
        />
      )}
    </div>
  )
}

export const BaseNode = memo(BaseNodeComponent)
