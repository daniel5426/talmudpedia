import { ArtifactScope, ArtifactSourceFile } from "@/services/artifacts"

export const CATEGORIES = [
  { value: "source", label: "Source" },
  { value: "normalization", label: "Normalization" },
  { value: "enrichment", label: "Enrichment" },
  { value: "chunking", label: "Chunking" },
  { value: "transform", label: "Transform" },
  { value: "custom", label: "Custom" },
]

export const SCOPES = [
  { value: "rag", label: "RAG" },
  { value: "agent", label: "Agent" },
  { value: "both", label: "Both" },
  { value: "tool", label: "Tool" },
]

export const DATA_TYPES = [
  { value: "none", label: "None" },
  { value: "raw_documents", label: "Raw" },
  { value: "normalized_documents", label: "Normalized" },
  { value: "enriched_documents", label: "Enriched" },
  { value: "chunks", label: "Chunks" },
  { value: "embeddings", label: "Embeddings" },
  { value: "any", label: "Any (Agent)" },
]

export const DEFAULT_PYTHON_CODE = `async def execute(inputs, config, context):
    """
    Process artifact inputs and return a JSON-serializable result.
    """
    items = inputs.get("items") if isinstance(inputs, dict) else inputs
    return {
        "items": items,
        "config": config,
        "tenant_id": context.get("tenant_id"),
    }
`

export interface ArtifactFormData {
  name: string
  display_name: string
  description: string
  category: string
  scope: ArtifactScope
  input_type: string
  output_type: string
  source_files: ArtifactSourceFile[]
  entry_module_path: string
  config_schema: string
  inputs: string
  outputs: string
  reads: string[]
  writes: string[]
}

export const initialFormData: ArtifactFormData = {
  name: "",
  display_name: "",
  description: "",
  category: "custom",
  scope: "rag",
  input_type: "raw_documents",
  output_type: "raw_documents",
  source_files: [{ path: "main.py", content: DEFAULT_PYTHON_CODE }],
  entry_module_path: "main.py",
  config_schema: "[]",
  inputs: "[]",
  outputs: "[]",
  reads: [],
  writes: [],
}
