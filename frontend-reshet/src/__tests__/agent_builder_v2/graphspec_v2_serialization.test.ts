import { Node } from "@xyflow/react"

import { normalizeGraphSpecForSave, resolveGraphSpecVersion } from "@/components/agent-builder/graphspec"
import { AgentNodeData } from "@/components/agent-builder/types"

const buildNode = (id: string, type: string): Node<AgentNodeData> => ({
  id,
  type,
  position: { x: 0, y: 0 },
  data: {
    nodeType: type as any,
    category: "logic",
    displayName: type,
    config: {},
    inputType: "any",
    outputType: "any",
    isConfigured: true,
    hasErrors: false,
  },
})

describe("graphspec v2 serialization", () => {
  it("preserves loaded spec version when there are no v2 orchestration nodes", () => {
    const nodes = [buildNode("n1", "start"), buildNode("n2", "agent")]
    const saved = normalizeGraphSpecForSave(nodes, [], { specVersion: "2.0" })
    expect(saved.spec_version).toBe("2.0")
  })

  it("forces v2 when orchestration nodes exist", () => {
    const nodes = [buildNode("n1", "start"), buildNode("n2", "spawn_group")]
    const saved = normalizeGraphSpecForSave(nodes, [], { specVersion: "1.0" })
    expect(saved.spec_version).toBe("2.0")
  })

  it("never downgrades v2 orchestration graphs to v1", () => {
    const nodes = [buildNode("n1", "join"), buildNode("n2", "judge")]
    expect(resolveGraphSpecVersion(nodes, "1.0")).toBe("2.0")
    expect(normalizeGraphSpecForSave(nodes, [], { specVersion: "1.0" }).spec_version).toBe("2.0")
  })
})
