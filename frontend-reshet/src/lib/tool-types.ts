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
  { id: "custom", label: "Custom", description: "Organization-defined tools", sort: 4 },
]

export const TOOL_SUBTYPES: ToolSubtypeMeta[] = [
  { id: "internal", label: "Internal", description: "Platform built-in", sort: 1 },
  { id: "http", label: "HTTP", description: "HTTP endpoint", sort: 2 },
  { id: "rag_pipeline", label: "RAG Pipeline", description: "Pipeline-backed tool", sort: 3 },
  { id: "agent_call", label: "Agent Call", description: "Invoke another published agent", sort: 4 },
  { id: "function", label: "Function", description: "Code-backed", sort: 5 },
  { id: "custom", label: "Custom", description: "Custom wrapper", sort: 6 },
  { id: "artifact", label: "Artifact", description: "Artifact executor", sort: 7 },
  { id: "mcp", label: "MCP", description: "MCP tool", sort: 8 },
]

export function getToolBucket(tool: ToolDefinition): ToolTypeBucket {
  if (tool.tool_type) return tool.tool_type
  if (tool.builtin_key) return "built_in"
  if (tool.implementation_type === "mcp") return "mcp"
  if (tool.implementation_type === "artifact" || tool.artifact_id) return "artifact"
  if (tool.implementation_type === "internal") return "built_in"
  return "custom"
}

export function getSubtypeLabel(implementationType: ToolImplementationType): string {
  return TOOL_SUBTYPES.find((t) => t.id === implementationType)?.label || implementationType
}

export function getToolIdentifier(tool: Pick<ToolDefinition, "id" | "builtin_key">): string {
  return tool.builtin_key || tool.id
}

export interface ToolsetGroup {
  id: string
  name: string
  description?: string | null
  selection_mode: "expand_to_members"
  member_ids: string[]
  members: ToolDefinition[]
  bucket: ToolTypeBucket
}

export function buildToolsets(tools: ToolDefinition[]): ToolsetGroup[] {
  const toolById = new Map<string, ToolDefinition>()
  tools.forEach((tool) => {
    toolById.set(tool.id, tool)
  })

  const groups: ToolsetGroup[] = []
  const seen = new Set<string>()

  tools.forEach((tool) => {
    const meta = tool.toolset
    if (!meta || seen.has(meta.id)) return
    seen.add(meta.id)

    const members = meta.member_ids
      .map((memberId) => toolById.get(memberId))
      .filter((member): member is ToolDefinition => Boolean(member))

    if (members.length === 0) return

    groups.push({
      id: meta.id,
      name: meta.name,
      description: meta.description || null,
      selection_mode: meta.selection_mode,
      member_ids: members.map((member) => member.id),
      members,
      bucket: getToolBucket(members[0]),
    })
  })

  return groups
}

export function getToolsetSelectionState(toolset: ToolsetGroup, selectedToolIds: string[]): "none" | "partial" | "full" {
  const selected = new Set(selectedToolIds)
  const selectedCount = toolset.member_ids.filter((memberId) => selected.has(memberId)).length
  if (selectedCount === 0) return "none"
  if (selectedCount === toolset.member_ids.length) return "full"
  return "partial"
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
      getToolIdentifier(tool).toLowerCase().includes(query) ||
      (tool.description || "").toLowerCase().includes(query)
    )
  })
}
