import { Node, Edge } from "@xyflow/react"

// =============================================================================
// OPERATOR CATEGORIES
// =============================================================================

export type OperatorCategory = 
  | "source" 
  | "normalization"
  | "enrichment"
  | "chunking"
  | "transform" 
  | "embedding" 
  | "storage"
  | "retrieval"
  | "reranking"
  | "custom"

// =============================================================================
// DATA TYPES
// =============================================================================

export type DataType = 
  | "none" 
  | "raw_documents" 
  | "normalized_documents"
  | "enriched_documents"
  | "chunks" 
  | "embeddings" 
  | "vectors"
  | "search_results"
  | "reranked_results"

// =============================================================================
// CONFIG FIELD TYPES
// =============================================================================

export type ConfigFieldType = 
  | "string" 
  | "integer" 
  | "float" 
  | "boolean" 
  | "secret" 
  | "select" 
  | "model_select"
  | "json"
  | "code"
  | "file_path"

export interface ConfigFieldSpec {
  name: string
  field_type: ConfigFieldType
  required: boolean
  runtime?: boolean
  default?: unknown
  description?: string
  options?: string[]
  required_capability?: string
  json_schema?: Record<string, unknown>
  min_value?: number
  max_value?: number
  placeholder?: string
}

// =============================================================================
// OPERATOR SPECIFICATION
// =============================================================================

export interface OperatorSpec {
  operator_id: string
  display_name: string
  category: OperatorCategory
  version: string
  description?: string
  input_type: DataType
  output_type: DataType
  required_config: ConfigFieldSpec[]
  optional_config: ConfigFieldSpec[]
  dimension?: number
  supports_parallelism?: boolean
  supports_streaming?: boolean
}

// =============================================================================
// PIPELINE NODE DATA
// =============================================================================

export interface PipelineNodeData {
  operator: string
  category: OperatorCategory
  displayName: string
  config: Record<string, unknown>
  inputType: DataType
  outputType: DataType
  isConfigured: boolean
  hasErrors: boolean
  executionStatus?: "pending" | "running" | "completed" | "failed" | "skipped"
  // Index signature for ReactFlow compatibility
  [key: string]: unknown
}

export type PipelineNode = Node<PipelineNodeData, string>

export type PipelineEdge = Edge

// =============================================================================
// CATEGORY COLORS
// =============================================================================

export const CATEGORY_COLORS: Record<OperatorCategory, string> = {
  source: "var(--pipeline-source)",
  normalization: "var(--pipeline-transform)",
  enrichment: "var(--pipeline-transform)",
  chunking: "var(--pipeline-transform)",
  transform: "var(--pipeline-transform)",
  embedding: "var(--pipeline-embedding)",
  storage: "var(--pipeline-storage)",
  retrieval: "var(--pipeline-source)",
  reranking: "var(--pipeline-transform)",
  custom: "var(--pipeline-embedding)",
}

export const CATEGORY_LABELS: Record<OperatorCategory, string> = {
  source: "Source",
  normalization: "Normalization",
  enrichment: "Enrichment",
  chunking: "Chunking",
  transform: "Transform",
  embedding: "Embedding",
  storage: "Storage",
  retrieval: "Retrieval",
  reranking: "Reranking",
  custom: "Custom",
}

// =============================================================================
// DATA TYPE COLORS
// =============================================================================

export const DATA_TYPE_COLORS: Record<DataType, string> = {
  none: "#6b7280",
  raw_documents: "#bbf7d0",
  normalized_documents: "#86efac",
  enriched_documents: "#4ade80",
  chunks: "#bfdbfe",
  embeddings: "#e9d5ff",
  vectors: "#fed7aa",
  search_results: "#fbcfe8",
  reranked_results: "#f9a8d4",
}

// =============================================================================
// CONNECTION VALIDATION
// =============================================================================

export function canConnect(sourceType: DataType, targetType: DataType): boolean {
  if (targetType === "none") return false
  if (sourceType === targetType) return true
  
  // Compatible flows matching backend/app/rag/pipeline/registry.py
  const compatibleFlows: [DataType, DataType][] = [
    ["raw_documents", "normalized_documents"],
    ["raw_documents", "enriched_documents"],  // Skip normalization
    ["raw_documents", "chunks"],              // Skip all preprocessing
    ["normalized_documents", "enriched_documents"],
    ["normalized_documents", "chunks"],       // Skip enrichment
    ["enriched_documents", "chunks"],
    ["chunks", "embeddings"],
    ["embeddings", "vectors"],
    ["search_results", "reranked_results"],
  ]
  
  return compatibleFlows.some(([src, tgt]) => src === sourceType && tgt === targetType)
}

export function getHandleColor(dataType: DataType): string {
  return DATA_TYPE_COLORS[dataType] || "#6b7280"
}

// =============================================================================
// OPERATOR CATALOG TYPES
// =============================================================================

export interface OperatorCatalogItem {
  operator_id: string
  display_name: string
  input_type: DataType
  output_type: DataType
  dimension?: number
}

export type OperatorCatalog = Record<OperatorCategory, OperatorCatalogItem[]>


// =============================================================================
// EXECUTION & INPUT SCHEMA TYPES
// =============================================================================

export type PipelineStepStatus = 
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped"

export interface PipelineStepExecution {
  id: string
  job_id: string
  step_id: string
  operator_id: string
  status: PipelineStepStatus
  input_data?: unknown
  output_data?: unknown
  metadata: Record<string, unknown>
  error_message?: string
  execution_order: number
  created_at: string
  started_at?: string
  completed_at?: string
}

export interface ExecutablePipelineInputField extends ConfigFieldSpec {
  operator_id: string
  operator_display_name?: string
  step_id: string
}

export interface ExecutablePipelineInputStep {
  step_id: string
  operator_id: string
  operator_display_name?: string
  category?: string
  config: Record<string, unknown>
  fields: ExecutablePipelineInputField[]
}

export interface ExecutablePipelineInputSchema {
  steps: ExecutablePipelineInputStep[]
}
