import { Node, Edge } from "@xyflow/react"

// Node categories for the agent builder
export type AgentNodeCategory = 
  | "control"     // Start, End
  | "reasoning"   // Agent, LLM
  | "action"      // Tool, RAG
  | "logic"       // If/Else, While, Parallel
  | "orchestration" // GraphSpec v2 orchestration nodes
  | "interaction" // User Approval
  | "data"        // Transform, Set State

// Data types that flow between nodes
export type AgentDataType = 
  | "any"         // Accepts any input
  | "message"     // Chat messages
  | "context"     // Structured context object
  | "decision"    // Boolean or branch selection
  | "result"      // Tool/RAG result

// Specific node types
export type AgentNodeType = 
  // Control
  | "start"
  | "end"
  // Reasoning
  | "agent"
  | "llm"
  // Actions  
  | "tool"
  | "rag"
  // Logic
  | "if_else"
  | "while"
  | "conditional"
  | "parallel"
  // Orchestration
  | "spawn_run"
  | "spawn_group"
  | "join"
  | "router"
  | "judge"
  | "replan"
  | "cancel_subtree"
  // Interaction
  | "user_approval"
  | "human_input"
  // Data
  | "transform"
  | "set_state"
  | "classify"
  | "vector_search"
  | (string & {}) // Allow dynamic artifact types

export interface AgentNodeData {
  nodeType: AgentNodeType
  category: AgentNodeCategory
  displayName: string
  config: Record<string, unknown>
  inputType: AgentDataType
  outputType: AgentDataType
  isConfigured: boolean
  hasErrors: boolean
  // For nodes with multiple output handles (If/Else, While, User Approval)
  outputHandles?: string[]
  // For dynamic handles generated from config (If/Else conditions)
  dynamicHandles?: boolean
  // Static handles that are always present (While: loop/exit, User Approval: approve/reject)
  staticHandles?: string[]
  // Field mappings for artifact nodes: maps input field names to expressions
  // Example: { "documents": "{{ upstream.ingest_node.output }}", "query": "{{ messages[-1].content }}" }
  inputMappings?: Record<string, string>
  // Index signature for ReactFlow compatibility
  [key: string]: unknown
}

// Catalog item shown in the node palette
export interface AgentNodeSpec {
  nodeType: AgentNodeType
  displayName: string
  description: string
  category: AgentNodeCategory
  inputType: AgentDataType
  outputType: AgentDataType
  icon: string // Lucide icon name
  configFields: ConfigFieldSpec[]
  // UI hints
  dynamicHandles?: boolean
  staticHandles?: string[]
  // Artifact-specific: explicit input/output field definitions for field mapping
  inputs?: ArtifactInputField[]
  outputs?: ArtifactOutputField[]
  // Artifact metadata (populated for artifact nodes)
  isArtifact?: boolean
  artifactId?: string
  artifactVersion?: string
}

// Artifact input field definition
export interface ArtifactInputField {
  name: string
  type: string
  required?: boolean
  default?: unknown
  description?: string
}

// Artifact output field definition
export interface ArtifactOutputField {
  name: string
  type: string
  description?: string
}

// Extended field types for new operators
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
    // New field types for enhanced operators
    | "variable_list"      // List of variable definitions (name, type, default)
    | "variable_selector"  // Dropdown to select from defined state variables
    | "template_string"    // Text with {{ variable }} interpolation
    | "expression"         // CEL expression input
    | "condition_list"     // List of conditions for If/Else
    | "mapping_list"       // Key-value mappings for Transform
    | "assignment_list"    // Variable assignments for Set State
    | "tool_list"          // Multi-select for tools
    | "category_list"      // Categories for Classify
    | "field_mapping"      // Field mapping editor for artifacts
    | "scope_subset"       // Orchestration scope subset list
    | "spawn_targets"      // Orchestration spawn-group targets
    | "route_table"        // Router/Judge visual branch rows
    | "advanced_toggle"    // Optional advanced UX toggle
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
  // Artifact-specific metadata for field mapping UI
  artifactInputs?: ArtifactInputField[]
}

export type AgentNode = Node<AgentNodeData, string>
export type AgentEdge = Edge

// Category styling
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

// Node specifications for the catalog (static fallback)
// NOTE: The backend provides the authoritative list via API
export const AGENT_NODE_SPECS: AgentNodeSpec[] = [
  // ==========================================================================
  // Control
  // ==========================================================================
  {
    nodeType: "start",
    displayName: "Start",
    description: "Entry point. Initialize variables here.",
    category: "control",
    inputType: "any",
    outputType: "message",
    icon: "Play",
    configFields: [
      { name: "input_variables", label: "Input Variables", fieldType: "variable_list", required: false, description: "Define expected input variables" },
      { name: "state_variables", label: "State Variables", fieldType: "variable_list", required: false, description: "Initialize persistent state variables" },
    ],
  },
  {
    nodeType: "end",
    displayName: "End",
    description: "Exit point. Specify what to return.",
    category: "control",
    inputType: "any",
    outputType: "any",
    icon: "Square",
    configFields: [
      { name: "output_variable", label: "Output Variable", fieldType: "variable_selector", required: false, description: "Select a state variable to return" },
      { name: "output_message", label: "Output Message", fieldType: "template_string", required: false, description: "Template with {{ variable }} interpolation" },
    ],
  },
  
  // ==========================================================================
  // Reasoning
  // ==========================================================================
  {
    nodeType: "agent",
    displayName: "Agent",
    description: "Primary reasoning node with tools and structured output.",
    category: "reasoning",
    inputType: "message",
    outputType: "message",
    icon: "Bot",
    configFields: [
      { name: "name", label: "Name", fieldType: "string", required: false, description: "Agent display name" },
      { name: "model_id", label: "Model", fieldType: "model", required: true, description: "Select a chat model" },
      { name: "instructions", label: "Instructions", fieldType: "text", required: false, description: "System prompt with {{ variable }} support" },
      { name: "include_chat_history", label: "Include Chat History", fieldType: "boolean", required: false, default: true },
      { name: "reasoning_effort", label: "Reasoning Effort", fieldType: "select", required: false, default: "medium",
        options: [
          { value: "low", label: "Low" },
          { value: "medium", label: "Medium" },
          { value: "high", label: "High" },
        ]
      },
      { name: "output_format", label: "Output Format", fieldType: "select", required: false, default: "text",
        options: [
          { value: "text", label: "Text" },
          { value: "json", label: "JSON" },
        ]
      },
      { name: "tools", label: "Tools", fieldType: "tool_list", required: false, description: "Attach tools to the agent" },
      { name: "temperature", label: "Temperature", fieldType: "number", required: false, description: "Override reasoning effort temperature" },
    ],
  },
  {
    nodeType: "llm",
    displayName: "LLM",
    description: "Simple LLM completion for basic text generation.",
    category: "reasoning",
    inputType: "message",
    outputType: "message",
    icon: "Brain",
    configFields: [
      { name: "model_id", label: "Model", fieldType: "model", required: true, description: "Select a chat model" },
      { name: "system_prompt", label: "System Prompt", fieldType: "text", required: false, description: "Instructions for the LLM" },
      { name: "temperature", label: "Temperature", fieldType: "number", required: false, default: 0.7, description: "Creativity (0-1)" },
    ],
  },
  
  // ==========================================================================
  // Actions
  // ==========================================================================
  {
    nodeType: "tool",
    displayName: "Tool",
    description: "Invoke a registered tool.",
    category: "action",
    inputType: "context",
    outputType: "result",
    icon: "Wrench",
    configFields: [
      { name: "tool_id", label: "Tool", fieldType: "tool", required: true, description: "Select a tool to invoke" },
    ],
  },
  {
    nodeType: "rag",
    displayName: "Retrieval",
    description: "Execute a Retrieval Pipeline.",
    category: "action",
    inputType: "message",
    outputType: "context",
    icon: "Search",
    configFields: [
      { name: "pipeline_id", label: "Retrieval Pipeline", fieldType: "retrieval_pipeline_select", required: true, description: "Select a Retrieval Pipeline" },
      { name: "query", label: "Query Template", fieldType: "template_string", required: false, description: "Query with {{ variable }} interpolation" },
      { name: "top_k", label: "Max Results", fieldType: "number", required: false, default: 10, description: "Number of results to retrieve" },
    ],
  },
  {
    nodeType: "vector_search",
    displayName: "Vector Search",
    description: "Search a Knowledge Store directly.",
    category: "action",
    inputType: "message",
    outputType: "context",
    icon: "Database", // Using Database icon
    configFields: [
      { name: "knowledge_store_id", label: "Knowledge Store", fieldType: "knowledge_store_select", required: true, description: "Select the Knowledge Store to search." },
      { name: "query", label: "Query Template", fieldType: "template_string", required: false, description: "Query with {{ variable }} interpolation" },
      { name: "top_k", label: "Max Results", fieldType: "number", required: false, default: 10, description: "Number of results to retrieve" },
    ],
  },
  
  // ==========================================================================
  // Reasoning
  // ==========================================================================
  {
    nodeType: "classify",
    displayName: "Classify",
    description: "Classify input into categories using LLM.",
    category: "reasoning",
    inputType: "message",
    outputType: "decision",
    icon: "ListFilter",
    dynamicHandles: true,
    configFields: [
      { name: "name", label: "Name", fieldType: "string", required: false },
      { name: "model_id", label: "Model", fieldType: "model", required: true, description: "Model used for classification" },
      { name: "instructions", label: "Instructions", fieldType: "text", required: false, description: "Additional context for classification" },
      { name: "categories", label: "Categories", fieldType: "category_list", required: true, description: "Define classification categories" },
    ],
  },
  
  // ==========================================================================
  // Data
  // ==========================================================================
  {
    nodeType: "transform",
    displayName: "Transform",
    description: "Reshape data using expressions.",
    category: "data",
    inputType: "any",
    outputType: "any",
    icon: "Sparkles",
    configFields: [
      { name: "name", label: "Name", fieldType: "string", required: false },
      { name: "mode", label: "Mode", fieldType: "select", required: false, default: "expressions",
        options: [
          { value: "expressions", label: "Expressions (CEL)" },
          { value: "object", label: "Literal Values" },
        ]
      },
      { name: "mappings", label: "Mappings", fieldType: "mapping_list", required: true, description: "Key-value mappings" },
    ],
  },
  {
    nodeType: "set_state",
    displayName: "Set State",
    description: "Explicitly set state variables.",
    category: "data",
    inputType: "any",
    outputType: "any",
    icon: "Database",
    configFields: [
      { name: "name", label: "Name", fieldType: "string", required: false },
      { name: "assignments", label: "Assignments", fieldType: "assignment_list", required: true, description: "Variable assignments" },
      { name: "is_expression", label: "Values are Expressions", fieldType: "boolean", required: false, default: true },
    ],
  },
  
  // ==========================================================================
  // Logic
  // ==========================================================================
  {
    nodeType: "if_else",
    displayName: "If/Else",
    description: "Multi-condition branching with CEL expressions.",
    category: "logic",
    inputType: "any",
    outputType: "decision",
    icon: "GitBranch",
    dynamicHandles: true,
    configFields: [
      { name: "conditions", label: "Conditions", fieldType: "condition_list", required: false, description: "Conditions evaluated in order" },
    ],
  },
  {
    nodeType: "while",
    displayName: "While",
    description: "Loop while condition is true.",
    category: "logic",
    inputType: "any",
    outputType: "decision",
    icon: "RefreshCw",
    staticHandles: ["loop", "exit"],
    configFields: [
      { name: "name", label: "Name", fieldType: "string", required: false },
      { name: "condition", label: "Condition", fieldType: "expression", required: true, description: "CEL expression - loop while true" },
      { name: "max_iterations", label: "Max Iterations", fieldType: "number", required: false, default: 10, description: "Safety limit" },
    ],
  },

  {
    nodeType: "parallel",
    displayName: "Parallel",
    description: "Execute multiple branches concurrently.",
    category: "logic",
    inputType: "any",
    outputType: "context",
    icon: "GitFork",
    configFields: [
      { name: "wait_all", label: "Wait for All", fieldType: "boolean", required: false, default: true, description: "Wait for all branches" },
    ],
  },

  // ==========================================================================
  // Orchestration (GraphSpec v2)
  // ==========================================================================
  {
    nodeType: "spawn_run",
    displayName: "Spawn Run",
    description: "Spawn a single child run through the orchestration kernel.",
    category: "orchestration",
    inputType: "context",
    outputType: "context",
    icon: "GitBranch",
    configFields: [
      { name: "target_agent_slug", label: "Target Agent", fieldType: "agent_select", required: false, visibility: "simple", group: "what_to_run" },
      { name: "target_agent_id", label: "Target Agent (ID)", fieldType: "agent_select", required: false, visibility: "advanced", group: "what_to_run", helpKind: "runtime-internal" },
      { name: "scope_subset", label: "Scope Subset", fieldType: "scope_subset", required: true, visibility: "simple", group: "permissions", helpKind: "required-for-compile", description: "Scopes delegated to spawned child run(s)." },
      { name: "idempotency_key", label: "Idempotency Key", fieldType: "string", required: false, visibility: "advanced", group: "reliability", helpKind: "runtime-internal" },
      {
        name: "failure_policy",
        label: "Failure Policy",
        fieldType: "select",
        required: false,
        default: "best_effort",
        visibility: "advanced",
        group: "reliability",
        helpKind: "runtime-internal",
        options: [
          { value: "best_effort", label: "Best Effort" },
          { value: "fail_fast", label: "Fail Fast" },
        ],
      },
      { name: "timeout_s", label: "Timeout (seconds)", fieldType: "number", required: false, visibility: "advanced", group: "reliability" },
      { name: "start_background", label: "Start in Background", fieldType: "boolean", required: false, default: true, visibility: "advanced", group: "reliability", helpKind: "runtime-internal" },
    ],
  },
  {
    nodeType: "spawn_group",
    displayName: "Spawn Group",
    description: "Spawn a fanout group of child runs through the orchestration kernel.",
    category: "orchestration",
    inputType: "context",
    outputType: "context",
    icon: "GitMerge",
    configFields: [
      { name: "targets", label: "Targets", fieldType: "spawn_targets", required: true, visibility: "simple", group: "what_to_run", helpKind: "required-for-compile", description: "One or more target agents and optional payload mappings." },
      { name: "scope_subset", label: "Scope Subset", fieldType: "scope_subset", required: true, visibility: "simple", group: "permissions", helpKind: "required-for-compile", description: "Scopes delegated to all spawned child runs." },
      {
        name: "join_mode",
        label: "Join Mode",
        fieldType: "select",
        required: false,
        default: "all",
        visibility: "simple",
        group: "routing",
        options: [
          { value: "all", label: "All" },
          { value: "best_effort", label: "Best Effort" },
          { value: "fail_fast", label: "Fail Fast" },
          { value: "quorum", label: "Quorum" },
          { value: "first_success", label: "First Success" },
        ],
      },
      {
        name: "quorum_threshold",
        label: "Quorum Threshold",
        fieldType: "number",
        required: false,
        visibility: "simple",
        group: "routing",
        dependsOn: { field: "join_mode", equals: "quorum" },
      },
      { name: "timeout_s", label: "Timeout (seconds)", fieldType: "number", required: false, visibility: "advanced", group: "reliability" },
      { name: "idempotency_key_prefix", label: "Idempotency Key Prefix", fieldType: "string", required: false, visibility: "advanced", group: "reliability", helpKind: "runtime-internal" },
      {
        name: "failure_policy",
        label: "Failure Policy",
        fieldType: "select",
        required: false,
        default: "best_effort",
        visibility: "advanced",
        group: "reliability",
        helpKind: "runtime-internal",
        options: [
          { value: "best_effort", label: "Best Effort" },
          { value: "fail_fast", label: "Fail Fast" },
        ],
      },
      { name: "start_background", label: "Start in Background", fieldType: "boolean", required: false, default: true, visibility: "advanced", group: "reliability", helpKind: "runtime-internal" },
    ],
  },
  {
    nodeType: "join",
    displayName: "Join",
    description: "Join an orchestration group and route by completion status.",
    category: "orchestration",
    inputType: "context",
    outputType: "decision",
    icon: "Link",
    dynamicHandles: true,
    configFields: [
      { name: "orchestration_group_id", label: "Group ID", fieldType: "string", required: false, visibility: "advanced", group: "what_to_run", helpKind: "runtime-internal" },
      {
        name: "mode",
        label: "Mode",
        fieldType: "select",
        required: false,
        default: "all",
        visibility: "simple",
        group: "routing",
        options: [
          { value: "all", label: "All" },
          { value: "best_effort", label: "Best Effort" },
          { value: "fail_fast", label: "Fail Fast" },
          { value: "quorum", label: "Quorum" },
          { value: "first_success", label: "First Success" },
        ],
      },
      {
        name: "quorum_threshold",
        label: "Quorum Threshold",
        fieldType: "number",
        required: false,
        visibility: "simple",
        group: "routing",
        dependsOn: { field: "mode", equals: "quorum" },
      },
      { name: "timeout_s", label: "Timeout (seconds)", fieldType: "number", required: false, visibility: "advanced", group: "reliability" },
    ],
  },
  {
    nodeType: "router",
    displayName: "Router",
    description: "Route orchestration payload to named branches.",
    category: "orchestration",
    inputType: "context",
    outputType: "decision",
    icon: "Route",
    dynamicHandles: true,
    configFields: [
      { name: "route_key", label: "Route Key", fieldType: "string", required: false, default: "status", visibility: "simple", group: "routing" },
      { name: "routes", label: "Routes", fieldType: "route_table", required: false, visibility: "simple", group: "routing", description: "Named branch routes and match values." },
    ],
  },
  {
    nodeType: "judge",
    displayName: "Judge",
    description: "Decide orchestration pass/fail branches.",
    category: "orchestration",
    inputType: "context",
    outputType: "decision",
    icon: "Scale",
    dynamicHandles: true,
    configFields: [
      { name: "outcomes", label: "Outcomes", fieldType: "route_table", required: false, visibility: "simple", group: "routing", description: "Outcome branch names (pass/fail by default)." },
      { name: "pass_outcome", label: "Pass Branch Label", fieldType: "string", required: false, default: "pass", visibility: "advanced", group: "routing", helpKind: "runtime-internal" },
      { name: "fail_outcome", label: "Fail Branch Label", fieldType: "string", required: false, default: "fail", visibility: "advanced", group: "routing", helpKind: "runtime-internal" },
    ],
  },
  {
    nodeType: "replan",
    displayName: "Replan",
    description: "Evaluate subtree and decide replan vs continue.",
    category: "orchestration",
    inputType: "context",
    outputType: "decision",
    icon: "RefreshCw",
    dynamicHandles: true,
    configFields: [
      { name: "run_id", label: "Run ID", fieldType: "string", required: false, visibility: "advanced", group: "what_to_run", helpKind: "runtime-internal" },
    ],
  },
  {
    nodeType: "cancel_subtree",
    displayName: "Cancel Subtree",
    description: "Cancel a child run subtree through the orchestration kernel.",
    category: "orchestration",
    inputType: "context",
    outputType: "context",
    icon: "Ban",
    configFields: [
      { name: "run_id", label: "Run ID", fieldType: "string", required: false, visibility: "advanced", group: "what_to_run", helpKind: "runtime-internal" },
      { name: "include_root", label: "Include Root Run", fieldType: "boolean", required: false, default: true, visibility: "advanced", group: "reliability", helpKind: "runtime-internal" },
      { name: "reason", label: "Reason", fieldType: "string", required: false, visibility: "advanced", group: "reliability" },
    ],
  },
  
  // ==========================================================================
  // Interaction
  // ==========================================================================
  {
    nodeType: "user_approval",
    displayName: "User Approval",
    description: "Pause for user approval or rejection.",
    category: "interaction",
    inputType: "any",
    outputType: "decision",
    icon: "UserCheck",
    staticHandles: ["approve", "reject"],
    configFields: [
      { name: "name", label: "Name", fieldType: "string", required: false },
      { name: "message", label: "Message", fieldType: "template_string", required: false, description: "Message with {{ variable }} support" },
      { name: "timeout_seconds", label: "Timeout (seconds)", fieldType: "number", required: false, default: 300 },
      { name: "require_comment", label: "Require Comment", fieldType: "boolean", required: false, default: false },
    ],
  },
  {
    nodeType: "human_input",
    displayName: "Human Input",
    description: "Wait for human text input.",
    category: "interaction",
    inputType: "any",
    outputType: "message",
    icon: "UserCheck",
    configFields: [
      { name: "prompt", label: "Prompt", fieldType: "text", required: false, description: "Message shown to the human reviewer" },
      { name: "timeout_seconds", label: "Timeout (seconds)", fieldType: "number", required: false, default: 300, description: "Max wait time" },
    ],
  },
]

// Connection validation
export function canConnect(sourceType: AgentDataType, targetType: AgentDataType): boolean {
  // "any" accepts anything
  if (targetType === "any") return true
  if (sourceType === "any") return true
  
  // Same types can connect
  if (sourceType === targetType) return true
  
  // Specific allowed conversions
  const allowedConnections: Record<AgentDataType, AgentDataType[]> = {
    message: ["context", "any"],
    context: ["message", "any"],
    result: ["context", "message", "any"],
    decision: ["message", "context", "result", "any"], // Allow connecting decision branches to anything
    any: ["message", "context", "result", "decision", "any"],
  }
  
  return allowedConnections[sourceType]?.includes(targetType) ?? false
}

export function getHandleColor(dataType: AgentDataType): string {
  return DATA_TYPE_COLORS[dataType] || "#6b7280"
}

export function getNodeSpec(nodeType: AgentNodeType): AgentNodeSpec | undefined {
  return AGENT_NODE_SPECS.find(spec => spec.nodeType === nodeType)
}

export function getClassifyHandleIds(categories: Array<{ name?: string }>): string[] {
  return dedupeNamedHandles(categories, "category")
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

function dedupeNamedHandles(items: Array<{ name?: string }>, fallbackPrefix: string): string[] {
  const used = new Set<string>()
  return (items || []).map((c, i) => {
    const base = (c?.name ?? "").trim()
    const fallback = `${fallbackPrefix}_${i}`
    const rawId = base || fallback
    let uniqueId = rawId
    let suffix = 1
    while (used.has(uniqueId)) {
      uniqueId = `${rawId}_${suffix}`
      suffix += 1
    }
    used.add(uniqueId)
    return uniqueId
  })
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

// Helper to get output handles for a node based on its config
export function getNodeOutputHandles(nodeType: AgentNodeType, config: Record<string, unknown>): string[] {
  const spec = getNodeSpec(nodeType)
  
  // Static handles are always present
  if (spec?.staticHandles) {
    return spec.staticHandles
  }
  
  // Dynamic handles from config (If/Else)
  if (spec?.dynamicHandles && nodeType === "if_else") {
    const conditions = (config.conditions as Array<{ name?: string }>) || []
    const handles = dedupeNamedHandles(conditions, "condition")
    handles.push("else") // Always have else
    return handles
  }

  if (spec?.dynamicHandles && nodeType === "classify") {
    const categories = (config.categories as Array<{ name?: string }>) || []
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
    if (outcomes.length > 0) {
      return outcomes
    }
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
  
  // Default: single output
  return []
}
