import { BaseNode } from "./BaseNode"
import { AGENT_NODE_SPECS } from "../types"

// All built-in agent node types use the same BaseNode component.
// Derive the registry from the canonical specs so renderer coverage can't drift.
const staticNodeTypes: Record<string, typeof BaseNode> = Object.fromEntries(
  AGENT_NODE_SPECS.map((spec) => [spec.nodeType, BaseNode])
)

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
