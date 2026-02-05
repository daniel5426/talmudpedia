import { ToolDefinition, ToolImplementationType, ToolStatus, ToolTypeBucket } from "@/services/agent"

export interface ToolBucketMeta {
  id: ToolTypeBucket
  label: string
  description: string
  sort: number
}

export interface ToolSubtypeMeta {
  id: ToolImplementationType
  label: string
  description: string
  sort: number
}

export const TOOL_BUCKETS: ToolBucketMeta[] = [
  { id: "built_in", label: "Built-in", description: "System-provided tools", sort: 1 },
  { id: "mcp", label: "MCP", description: "Remote MCP servers", sort: 2 },
  { id: "artifact", label: "Artifact", description: "Artifact-backed tools", sort: 3 },
  { id: "custom", label: "Custom", description: "Tenant-defined tools", sort: 4 },
]

export const TOOL_SUBTYPES: ToolSubtypeMeta[] = [
  { id: "internal", label: "Internal", description: "Platform built-in", sort: 1 },
  { id: "http", label: "HTTP", description: "HTTP endpoint", sort: 2 },
  { id: "rag_retrieval", label: "RAG Retrieval", description: "Retrieval pipeline", sort: 3 },
  { id: "function", label: "Function", description: "Code-backed", sort: 4 },
  { id: "custom", label: "Custom", description: "Custom wrapper", sort: 5 },
  { id: "artifact", label: "Artifact", description: "Artifact executor", sort: 6 },
  { id: "mcp", label: "MCP", description: "MCP tool", sort: 7 },
]

export function getToolBucket(tool: ToolDefinition): ToolTypeBucket {
  if (tool.tool_type) return tool.tool_type
  if (tool.implementation_type === "mcp") return "mcp"
  if (tool.implementation_type === "artifact" || tool.artifact_id) return "artifact"
  if (tool.implementation_type === "internal") return "built_in"
  return "custom"
}

export function getSubtypeLabel(implementationType: ToolImplementationType): string {
  return TOOL_SUBTYPES.find((t) => t.id === implementationType)?.label || implementationType
}

export interface ToolFilterState {
  query?: string
  status?: ToolStatus | "all"
  bucket?: ToolTypeBucket | "all"
  subtype?: ToolImplementationType | "all"
}

export function filterTools(tools: ToolDefinition[], filters: ToolFilterState): ToolDefinition[] {
  const query = (filters.query || "").toLowerCase().trim()
  return tools.filter((tool) => {
    if (filters.status && filters.status !== "all" && tool.status !== filters.status) return false
    if (filters.bucket && filters.bucket !== "all" && getToolBucket(tool) !== filters.bucket) return false
    if (filters.subtype && filters.subtype !== "all" && tool.implementation_type !== filters.subtype) return false
    if (!query) return true
    return (
      tool.name.toLowerCase().includes(query) ||
      tool.slug.toLowerCase().includes(query) ||
      (tool.description || "").toLowerCase().includes(query)
    )
  })
}
