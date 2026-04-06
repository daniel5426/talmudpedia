"use client"

import { Cpu } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAgentBuilderCanvasResources } from "../hooks/useAgentBuilderCanvasResources"
import { useAgentBuilderUi } from "../agent-builder-ui-context"

type AgentNodeExpandedBodyProps = {
  nodeId: string
  modelId: string | undefined
  toolIds: string[]
}

export function AgentNodeExpandedBody({ nodeId, modelId, toolIds }: AgentNodeExpandedBodyProps) {
  const { getModelLabel, getToolById, loading } = useAgentBuilderCanvasResources()
  const builderUi = useAgentBuilderUi()
  const label = getModelLabel(modelId)
  const modelLine = label || modelId || "No model"

  return (
    <div className="flex flex-col w-full min-w-[228px] max-w-[300px]">
      <div className="flex items-start gap-2 px-3 py-2 border-b border-border/30">
        <Cpu className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60 mt-px" />
        <div className="min-w-0 flex-1">
          <div className="text-[10px] text-muted-foreground/80 tracking-wide">Model</div>
          <div className="text-[12px] text-foreground/90 truncate" title={modelLine}>
            {loading && !label && modelId ? "…" : modelLine}
          </div>
        </div>
      </div>
      <div className="px-3 py-2">
        <div className="text-[10px] text-muted-foreground/80 tracking-wide mb-1.5">Tools</div>
        {toolIds.length === 0 ? (
          <div className="text-[11px] text-muted-foreground/90">None</div>
        ) : (
          <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 min-w-0 w-full">
            {toolIds.map((tid) => {
              const tool = getToolById(tid)
              const name = loading && !tool ? "…" : tool?.name || tid
              return (
                <button
                  key={tid}
                  type="button"
                  className={cn(
                    "min-w-0 w-full max-w-full overflow-hidden rounded-sm px-1 py-1 text-left text-[11px] leading-snug text-foreground/80",
                    "truncate hover:text-foreground hover:bg-muted/50 transition-colors",
                    "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring/40"
                  )}
                  title={typeof name === "string" ? name : undefined}
                  onPointerDown={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation()
                    builderUi?.focusAgentTool(nodeId, tid)
                  }}
                >
                  {name}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
