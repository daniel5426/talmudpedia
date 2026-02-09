import { BaseNode } from "./BaseNode"

// All agent node types use the same BaseNode component
// The visual differences are handled by the data.nodeType and data.category
const staticNodeTypes: Record<string, any> = {
  start: BaseNode,
  end: BaseNode,
  agent: BaseNode,
  llm: BaseNode,
  tool: BaseNode,
  rag: BaseNode,
  if_else: BaseNode,
  while: BaseNode,
  conditional: BaseNode,
  parallel: BaseNode,
  spawn_run: BaseNode,
  spawn_group: BaseNode,
  join: BaseNode,
  router: BaseNode,
  judge: BaseNode,
  replan: BaseNode,
  cancel_subtree: BaseNode,
  user_approval: BaseNode,
  human_input: BaseNode,
  transform: BaseNode,
  set_state: BaseNode,
  classify: BaseNode,
  vector_search: BaseNode,
}

// Use a Proxy to handle dynamic artifact types (e.g. "artifact:my_id")
// ReactFlow accesses properties on this object to find the component.
export const nodeTypes = new Proxy(staticNodeTypes, {
  get: (target, prop: string) => {
    if (prop in target) {
      return target[prop]
    }
    // Dynamic artifact support
    if (typeof prop === "string" && prop.startsWith("artifact:")) {
      return BaseNode
    }
    return undefined
  }
})
