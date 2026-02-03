export { BaseNode } from "./BaseNode"
export { SourceNode } from "./SourceNode"
export { TransformNode } from "./TransformNode"
export { EmbeddingNode } from "./EmbeddingNode"
export { StorageNode } from "./StorageNode"

import { SourceNode } from "./SourceNode"
import { TransformNode } from "./TransformNode"
import { EmbeddingNode } from "./EmbeddingNode"
import { StorageNode } from "./StorageNode"

export const nodeTypes = {
  source: SourceNode,
  normalization: TransformNode,
  enrichment: TransformNode,
  chunking: TransformNode,
  transform: TransformNode,
  embedding: EmbeddingNode,
  storage: StorageNode,
  retrieval: SourceNode,
  reranking: TransformNode,
  pipeline_input: SourceNode,
  pipeline_output: StorageNode,
  custom: EmbeddingNode,
}
