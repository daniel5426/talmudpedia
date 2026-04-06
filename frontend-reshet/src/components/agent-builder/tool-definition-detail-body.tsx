"use client"

import { Badge } from "@/components/ui/badge"
import { TOOL_BUCKETS, getToolBucket, getSubtypeLabel } from "@/lib/tool-types"
import type { ToolDefinition } from "@/services/agent"

export function ToolDefinitionDetailBody({ tool }: { tool: ToolDefinition }) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="secondary" className="text-xs">
          {TOOL_BUCKETS.find((b) => b.id === getToolBucket(tool))?.label ?? getToolBucket(tool)}
        </Badge>
        <Badge variant="outline" className="text-xs">
          {getSubtypeLabel(tool.implementation_type)}
        </Badge>
        <Badge variant="outline" className="text-xs">
          v{tool.version}
        </Badge>
        <Badge variant={tool.status === "published" ? "default" : "outline"} className="text-xs">
          {tool.status}
        </Badge>
      </div>
      <div>
        <div className="text-xs font-medium text-muted-foreground mb-1">Identifier</div>
        <code className="text-xs bg-muted px-2 py-1 rounded font-mono block">{tool.slug}</code>
      </div>
      {tool.input_schema && Object.keys(tool.input_schema).length > 0 && (
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-2">Input Schema</div>
          <pre className="text-xs bg-muted rounded-md p-3 overflow-x-auto max-h-[200px] overflow-y-auto font-mono leading-relaxed">
            {JSON.stringify(tool.input_schema, null, 2)}
          </pre>
        </div>
      )}
      {tool.output_schema && Object.keys(tool.output_schema).length > 0 && (
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-2">Output Schema</div>
          <pre className="text-xs bg-muted rounded-md p-3 overflow-x-auto max-h-[200px] overflow-y-auto font-mono leading-relaxed">
            {JSON.stringify(tool.output_schema, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
