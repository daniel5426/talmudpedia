import { BaseNode } from "./BaseNode"

// All agent node types use the same BaseNode component
// The visual differences are handled by the data.nodeType and data.category
export const nodeTypes = {
  start: BaseNode,
  end: BaseNode,
  llm: BaseNode,
  tool: BaseNode,
  rag: BaseNode,
  conditional: BaseNode,
  parallel: BaseNode,
  human_input: BaseNode,
}
