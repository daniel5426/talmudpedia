import { Edge, Node } from "@xyflow/react"

export type AgentNodeCategory =
  | "control"
  | "reasoning"
  | "action"
  | "logic"
  | "orchestration"
  | "interaction"
  | "data"

export type AgentDataType =
  | "any"
  | "message"
  | "context"
  | "decision"
  | "result"

export type AgentNodeType =
  | "start"
  | "end"
  | "agent"
  | "tool"
  | "rag"
  | "if_else"
  | "while"
  | "parallel"
  | "spawn_run"
  | "spawn_group"
  | "join"
  | "router"
  | "judge"
  | "replan"
  | "cancel_subtree"
  | "user_approval"
  | "transform"
  | "speech_to_text"
  | "set_state"
  | "classify"
  | "vector_search"
  | (string & {})

export interface AgentNodeData {
  nodeType: AgentNodeType
  category: AgentNodeCategory
  displayName: string
  config: Record<string, unknown>
  inputType: AgentDataType
  outputType: AgentDataType
  isConfigured: boolean
  hasErrors: boolean
  outputHandles?: string[]
  dynamicHandles?: boolean
  staticHandles?: string[]
  inputMappings?: Record<string, string>
  [key: string]: unknown
}

export interface ArtifactInputField {
  name: string
  type: string
  required?: boolean
  default?: unknown
  description?: string
}

export interface ConfigFieldSpec {
  name: string
  label: string
  fieldType:
    | "string"
    | "text"
    | "number"
    | "boolean"
    | "select"
    | "model"
    | "tool"
    | "rag"
    | "agent_select"
    | "knowledge_store"
    | "knowledge_store_select"
    | "retrieval_pipeline_select"
    | "variable_list"
    | "variable_selector"
    | "template_string"
    | "expression"
    | "condition_list"
    | "mapping_list"
    | "assignment_list"
    | "tool_list"
    | "category_list"
    | "field_mapping"
    | "scope_subset"
    | "spawn_targets"
    | "route_table"
    | "advanced_toggle"
    | "value_ref"
  required: boolean
  default?: unknown
  description?: string
  options?: Array<{ value: string; label: string }>
  visibility?: "simple" | "advanced" | "both"
  dependsOn?: {
    field: string
    equals?: unknown
    notEquals?: unknown
  }
  helpKind?: "runtime-internal" | "required-for-compile" | "recommended"
  group?: "what_to_run" | "permissions" | "routing" | "reliability"
  artifactInputs?: ArtifactInputField[]
  prompt_capable?: boolean
  prompt_surface?: string
}

export type AgentNode = Node<AgentNodeData, string>
export type AgentEdge = Edge

export const CATEGORY_COLORS: Record<AgentNodeCategory, string> = {
  control: "var(--agent-control)",
  reasoning: "var(--agent-reasoning)",
  action: "var(--agent-action)",
  logic: "var(--agent-logic)",
  orchestration: "var(--agent-orchestration, #bfdbfe)",
  interaction: "var(--agent-interaction)",
  data: "var(--agent-data, #06b6d4)",
}

export const CATEGORY_LABELS: Record<AgentNodeCategory, string> = {
  control: "Control Flow",
  reasoning: "Reasoning",
  action: "Actions",
  logic: "Logic",
  orchestration: "Orchestration",
  interaction: "Interaction",
  data: "Data",
}

export const DATA_TYPE_COLORS: Record<AgentDataType, string> = {
  any: "var(--agent-control)",
  message: "var(--agent-reasoning)",
  context: "var(--agent-action)",
  decision: "var(--agent-logic)",
  result: "var(--agent-interaction)",
}

type NodeUiDefaults = {
  category: AgentNodeCategory
  displayName: string
  inputType: AgentDataType
  outputType: AgentDataType
}

const BUILTIN_NODE_DEFAULTS: Partial<Record<AgentNodeType, NodeUiDefaults>> = {
  start: { category: "control", displayName: "Start", inputType: "any", outputType: "message" },
  end: { category: "control", displayName: "End", inputType: "any", outputType: "any" },
  agent: { category: "reasoning", displayName: "Agent", inputType: "message", outputType: "message" },
  tool: { category: "action", displayName: "Tool", inputType: "context", outputType: "result" },
  rag: { category: "action", displayName: "Retrieval", inputType: "message", outputType: "context" },
  vector_search: { category: "action", displayName: "Vector Search", inputType: "message", outputType: "context" },
  classify: { category: "reasoning", displayName: "Classify", inputType: "message", outputType: "decision" },
  speech_to_text: { category: "data", displayName: "Speech to Text", inputType: "any", outputType: "context" },
  transform: { category: "data", displayName: "Transform", inputType: "any", outputType: "any" },
  set_state: { category: "data", displayName: "Set State", inputType: "any", outputType: "any" },
  if_else: { category: "logic", displayName: "If/Else", inputType: "any", outputType: "decision" },
  while: { category: "logic", displayName: "While", inputType: "any", outputType: "decision" },
  parallel: { category: "logic", displayName: "Parallel", inputType: "any", outputType: "context" },
  spawn_run: { category: "orchestration", displayName: "Spawn Run", inputType: "context", outputType: "context" },
  spawn_group: { category: "orchestration", displayName: "Spawn Group", inputType: "context", outputType: "context" },
  join: { category: "orchestration", displayName: "Join", inputType: "context", outputType: "decision" },
  router: { category: "orchestration", displayName: "Router", inputType: "context", outputType: "decision" },
  judge: { category: "orchestration", displayName: "Judge", inputType: "context", outputType: "decision" },
  replan: { category: "orchestration", displayName: "Replan", inputType: "context", outputType: "decision" },
  cancel_subtree: { category: "orchestration", displayName: "Cancel Subtree", inputType: "context", outputType: "context" },
  user_approval: { category: "interaction", displayName: "User Approval", inputType: "any", outputType: "decision" },
}

export function getNodeUiDefaults(nodeType: AgentNodeType): NodeUiDefaults | undefined {
  return BUILTIN_NODE_DEFAULTS[nodeType]
}

export function canConnect(sourceType: AgentDataType, targetType: AgentDataType): boolean {
  if (targetType === "any" || sourceType === "any" || sourceType === targetType) return true
  const allowedConnections: Record<AgentDataType, AgentDataType[]> = {
    message: ["context", "any"],
    context: ["message", "any"],
    result: ["context", "message", "any"],
    decision: ["message", "context", "result", "any"],
    any: ["message", "context", "result", "decision", "any"],
  }
  return allowedConnections[sourceType]?.includes(targetType) ?? false
}

export function getHandleColor(dataType: AgentDataType): string {
  return DATA_TYPE_COLORS[dataType] || "#6b7280"
}

function getStableBranchHandles(items: Array<{ id?: string; name?: string }>, fallbackPrefix: string): string[] {
  const used = new Set<string>()
  return (items || []).map((item, index) => {
    const explicitId = String(item?.id || "").trim()
    const base = explicitId || (item?.name ?? "").trim() || `${fallbackPrefix}_${index}`
    let unique = base
    let suffix = 1
    while (used.has(unique)) {
      unique = `${base}_${suffix}`
      suffix += 1
    }
    used.add(unique)
    return unique
  })
}

export function getClassifyHandleIds(categories: Array<{ id?: string; name?: string }>): string[] {
  const handles = getStableBranchHandles(categories, "category")
  handles.push("else")
  return handles
}

type RouteTableRow = {
  name?: string
  match?: string
}

function toCleanRouteName(raw: unknown): string {
  if (typeof raw !== "string") return ""
  return raw.trim()
}

export function normalizeRouteTableRows(rows: unknown): RouteTableRow[] {
  if (!Array.isArray(rows)) return []
  const used = new Set<string>()
  const normalized: RouteTableRow[] = []
  rows.forEach((item, idx) => {
    const rawName =
      typeof item === "string"
        ? item
        : (item && typeof item === "object" ? String((item as Record<string, unknown>).name || "") : "")
    const base = toCleanRouteName(rawName) || `route_${idx}`
    let unique = base
    let suffix = 1
    while (used.has(unique)) {
      unique = `${base}_${suffix}`
      suffix += 1
    }
    used.add(unique)
    const match =
      item && typeof item === "object" && "match" in (item as Record<string, unknown>)
        ? String((item as Record<string, unknown>).match ?? "")
        : unique
    normalized.push({ name: unique, match })
  })
  return normalized
}

export function routeTableRowsToRouterRoutes(rows: unknown): Array<{ name: string; match: string }> {
  return normalizeRouteTableRows(rows).map((row) => ({
    name: row.name || "",
    match: row.match ?? "",
  }))
}

export function routeTableRowsToOutcomes(rows: unknown): string[] {
  return normalizeRouteTableRows(rows)
    .map((row) => row.name || "")
    .filter((name) => name.length > 0)
}

function getRouterHandleIds(routes: unknown): string[] {
  const used = new Set<string>()
  const handles = (Array.isArray(routes) ? routes : []).map((route, idx) => {
    let candidate = ""
    if (typeof route === "string") {
      candidate = route.trim()
    } else if (route && typeof route === "object") {
      const routeObj = route as Record<string, unknown>
      candidate = String(routeObj.name || routeObj.key || routeObj.handle || "").trim()
    }
    const rawId = candidate || `route_${idx}`
    let uniqueId = rawId
    let suffix = 1
    while (used.has(uniqueId)) {
      uniqueId = `${rawId}_${suffix}`
      suffix += 1
    }
    used.add(uniqueId)
    return uniqueId
  })
  if (!used.has("default")) {
    handles.push("default")
  }
  return handles
}

export function getNodeOutputHandles(nodeType: AgentNodeType, config: Record<string, unknown>): string[] {
  if (nodeType === "while") return ["loop", "exit"]
  if (nodeType === "user_approval") return ["approve", "reject"]

  if (nodeType === "if_else") {
    const conditions = (config.conditions as Array<{ id?: string; name?: string }>) || []
    const handles = getStableBranchHandles(conditions, "condition")
    handles.push("else")
    return handles
  }

  if (nodeType === "classify") {
    const categories = (config.categories as Array<{ id?: string; name?: string }>) || []
    return getClassifyHandleIds(categories)
  }

  if (nodeType === "join") {
    return ["completed", "completed_with_errors", "failed", "timed_out", "pending"]
  }

  if (nodeType === "replan") {
    return ["replan", "continue"]
  }

  if (nodeType === "judge") {
    const outcomesFromTable = routeTableRowsToOutcomes(config.route_table)
    const outcomes = outcomesFromTable.length > 0
      ? outcomesFromTable
      : Array.isArray(config.outcomes)
        ? config.outcomes.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
        : []
    if (outcomes.length > 0) return outcomes
    const passOutcome = typeof config.pass_outcome === "string" && config.pass_outcome.trim()
      ? config.pass_outcome.trim()
      : "pass"
    const failOutcome = typeof config.fail_outcome === "string" && config.fail_outcome.trim()
      ? config.fail_outcome.trim()
      : "fail"
    return [passOutcome, failOutcome]
  }

  if (nodeType === "router") {
    const routes = Array.isArray(config.route_table)
      ? routeTableRowsToRouterRoutes(config.route_table)
      : config.routes
    return getRouterHandleIds(routes)
  }

  return []
}
