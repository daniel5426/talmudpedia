"use client"

import { X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ToolDefinitionDetailBody } from "./tool-definition-detail-body"
import type { ToolDefinition } from "@/services/agent"

type AgentToolDetailPanelProps = {
  tool: ToolDefinition | null
  toolIdFallback: string | null
  resourcesLoading: boolean
  onClose: () => void
}

export function AgentToolDetailPanel({
  tool,
  toolIdFallback,
  resourcesLoading,
  onClose,
}: AgentToolDetailPanelProps) {
  const showBody = Boolean(tool)
  const showMissing =
    !resourcesLoading && toolIdFallback && !tool

  return (
    <div className="flex flex-col w-full max-h-[min(640px,calc(100vh-48px))]">
      <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-border/40 shrink-0">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Tool</p>
          {resourcesLoading ? (
            <p className="text-sm text-muted-foreground mt-0.5">Loading…</p>
          ) : tool ? (
            <>
              <h2 className="text-base font-semibold truncate text-foreground">{tool.name}</h2>
              {tool.description ? (
                <p className="text-xs text-muted-foreground mt-1 line-clamp-3">{tool.description}</p>
              ) : null}
            </>
          ) : showMissing ? (
            <>
              <p className="text-sm text-muted-foreground mt-0.5">Not found in catalog</p>
              <code className="text-[11px] bg-muted px-2 py-1 rounded font-mono block mt-2 truncate" title={toolIdFallback}>
                {toolIdFallback}
              </code>
            </>
          ) : null}
        </div>
        <Button type="button" variant="ghost" size="icon" className="shrink-0 h-8 w-8" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      {showBody ? (
        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
          <ToolDefinitionDetailBody tool={tool!} />
        </div>
      ) : null}
    </div>
  )
}
