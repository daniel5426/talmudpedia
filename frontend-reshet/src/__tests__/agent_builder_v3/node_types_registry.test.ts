import { nodeTypes } from "@/components/agent-builder/nodes"
import { AGENT_NODE_SPECS } from "@/components/agent-builder/types"

describe("agent builder nodeTypes registry", () => {
  it("registers every built-in node spec with the shared BaseNode renderer", () => {
    for (const spec of AGENT_NODE_SPECS) {
      expect(nodeTypes[spec.nodeType]).toBeDefined()
    }
  })
})
