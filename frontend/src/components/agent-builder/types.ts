import { Node, Edge } from "@xyflow/react"

// Node categories for the agent builder
export type AgentNodeCategory = 
  | "control"     // Start, End
  | "reasoning"   // Agent, LLM
  | "action"      // Tool, RAG
  | "logic"       // If/Else, While, Parallel
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
  required: boolean
  default?: unknown
  description?: string
  options?: Array<{ value: string; label: string }>
}

export type AgentNode = Node<AgentNodeData, string>
export type AgentEdge = Edge

// Category styling
export const CATEGORY_COLORS: Record<AgentNodeCategory, string> = {
  control: "var(--agent-control)",
  reasoning: "var(--agent-reasoning)",
  action: "var(--agent-action)",
  logic: "var(--agent-logic)",
  interaction: "var(--agent-interaction)",
  data: "var(--agent-data, #06b6d4)",
}

export const CATEGORY_LABELS: Record<AgentNodeCategory, string> = {
  control: "Control Flow",
  reasoning: "Reasoning",
  action: "Actions",
  logic: "Logic",
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
    const handles = conditions.map((c, i) => c.name || `condition_${i}`)
    handles.push("else") // Always have else
    return handles
  }

  if (spec?.dynamicHandles && nodeType === "classify") {
    const categories = (config.categories as Array<{ name?: string }>) || []
    return categories.map((c, i) => c.name || `category_${i}`)
  }
  
  // Default: single output
  return []
}
