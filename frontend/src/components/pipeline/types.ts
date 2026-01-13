import { Node, Edge } from "@xyflow/react"

export type OperatorCategory = "source" | "transform" | "embedding" | "storage"

export type DataType = "none" | "raw_documents" | "chunks" | "embeddings" | "vectors"

export interface OperatorSpec {
  operator_id: string
  display_name: string
  category: OperatorCategory
  input_type: DataType
  output_type: DataType
  dimension?: number
  required_config: ConfigFieldSpec[]
  optional_config: ConfigFieldSpec[]
}

export interface ConfigFieldSpec {
  name: string
  field_type: "string" | "integer" | "float" | "boolean" | "secret" | "select"
  required: boolean
  default?: unknown
  description?: string
  options?: string[]
}

export interface PipelineNodeData {
  operator: string
  category: OperatorCategory
  displayName: string
  config: Record<string, unknown>
  inputType: DataType
  outputType: DataType
  isConfigured: boolean
  hasErrors: boolean
  // Index signature for ReactFlow compatibility
  [key: string]: unknown
}

export type PipelineNode = Node<PipelineNodeData, string>

export type PipelineEdge = Edge

export const CATEGORY_COLORS: Record<OperatorCategory, string> = {
  source: "#22c55e",
  transform: "#3b82f6",
  embedding: "#a855f7",
  storage: "#f97316",
}

export const CATEGORY_LABELS: Record<OperatorCategory, string> = {
  source: "Source",
  transform: "Transform",
  embedding: "Embedding",
  storage: "Storage",
}

export const DATA_TYPE_COLORS: Record<DataType, string> = {
  none: "#6b7280",
  raw_documents: "#22c55e",
  chunks: "#3b82f6",
  embeddings: "#a855f7",
  vectors: "#f97316",
}

export function canConnect(sourceType: DataType, targetType: DataType): boolean {
  if (targetType === "none") return false
  return sourceType === targetType || 
    (sourceType === "raw_documents" && targetType === "chunks") ||
    (sourceType === "chunks" && targetType === "embeddings") ||
    (sourceType === "embeddings" && targetType === "vectors")
}

export function getHandleColor(dataType: DataType): string {
  return DATA_TYPE_COLORS[dataType] || "#6b7280"
}
