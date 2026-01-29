import { Node, Edge } from "@xyflow/react"

// Node categories for the agent builder
export type AgentNodeCategory = 
  | "control"     // Start, End
  | "reasoning"   // LLM
  | "action"      // Tool, RAG
  | "logic"       // Conditional, Parallel
  | "interaction" // Human Input

// Data types that flow between nodes
export type AgentDataType = 
  | "any"         // Accepts any input
  | "message"     // Chat messages
  | "context"     // Structured context object
  | "decision"    // Boolean or branch selection
  | "result"      // Tool/RAG result

// Specific node types
export type AgentNodeType = 
  | "start"
  | "end"
  | "llm"
  | "tool"
  | "rag"
  | "conditional"
  | "parallel"
  | "human_input"

export interface AgentNodeData {
  nodeType: AgentNodeType
  category: AgentNodeCategory
  displayName: string
  config: Record<string, unknown>
  inputType: AgentDataType
  outputType: AgentDataType
  isConfigured: boolean
  hasErrors: boolean
  // For conditional nodes - multiple output handles
  outputHandles?: string[]
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
}

export interface ConfigFieldSpec {
  name: string
  label: string
  fieldType: "string" | "text" | "number" | "boolean" | "select" | "model" | "tool" | "rag"
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
}

export const CATEGORY_LABELS: Record<AgentNodeCategory, string> = {
  control: "Control Flow",
  reasoning: "Reasoning",
  action: "Actions",
  logic: "Logic",
  interaction: "Interaction",
}

export const DATA_TYPE_COLORS: Record<AgentDataType, string> = {
  any: "var(--agent-control)",
  message: "var(--agent-reasoning)",
  context: "var(--agent-action)",
  decision: "var(--agent-logic)",
  result: "var(--agent-interaction)",
}

// Node specifications for the catalog
export const AGENT_NODE_SPECS: AgentNodeSpec[] = [
  // Control
  {
    nodeType: "start",
    displayName: "Start",
    description: "Entry point for the agent. Receives user input.",
    category: "control",
    inputType: "any",
    outputType: "message",
    icon: "Play",
    configFields: [],
  },
  {
    nodeType: "end",
    displayName: "End",
    description: "Exit point. Returns the final response.",
    category: "control",
    inputType: "any",
    outputType: "any",
    icon: "Square",
    configFields: [],
  },
  
  // Reasoning
  {
    nodeType: "llm",
    displayName: "LLM",
    description: "Call a language model for reasoning or generation.",
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
  
  // Actions
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
    displayName: "RAG Lookup",
    description: "Retrieve context from a knowledge base.",
    category: "action",
    inputType: "message",
    outputType: "context",
    icon: "Search",
    configFields: [
      { name: "pipeline_id", label: "RAG Pipeline", fieldType: "rag", required: true, description: "Select a RAG pipeline" },
      { name: "top_k", label: "Results", fieldType: "number", required: false, default: 5, description: "Number of results to retrieve" },
    ],
  },
  
  // Logic
  {
    nodeType: "conditional",
    displayName: "Conditional",
    description: "Branch based on a condition.",
    category: "logic",
    inputType: "any",
    outputType: "decision",
    icon: "GitBranch",
    configFields: [
      { name: "condition_type", label: "Condition Type", fieldType: "select", required: true, 
        options: [
          { value: "llm_decision", label: "LLM Decision" },
          { value: "contains", label: "Output Contains" },
          { value: "regex", label: "Regex Match" },
        ],
        description: "How to evaluate the condition"
      },
      { name: "condition_value", label: "Condition Value", fieldType: "string", required: false, description: "Value to check against" },
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
      { name: "wait_all", label: "Wait for All", fieldType: "boolean", required: false, default: true, description: "Wait for all branches to complete" },
    ],
  },
  
  // Interaction
  {
    nodeType: "human_input",
    displayName: "Human Input",
    description: "Pause for human review or input.",
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
    decision: ["any"],
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
