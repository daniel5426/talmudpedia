import { Edge, Node } from "@xyflow/react"

import { normalizeBuilderNode, normalizeGraphSpecForSave } from "@/components/agent-builder/graphspec"
import { AgentNodeData } from "@/components/agent-builder/types"

describe("graphspec serialization", () => {
  it("normalizes legacy mappings and handle fields", () => {
    const nodes: Node<AgentNodeData>[] = [
      {
        id: "n1",
        type: "artifact:custom/tool",
        position: { x: 0, y: 0 },
        data: {
          nodeType: "artifact:custom/tool",
          category: "action",
          displayName: "Artifact",
          config: { input_mappings: { query: "{{ state.q }}" } },
          inputType: "any",
          outputType: "any",
          isConfigured: false,
          hasErrors: false,
        },
      },
    ]

    const edges: Edge[] = [
      {
        id: "e1",
        source: "n1",
        target: "n2",
        sourceHandle: "approve",
        targetHandle: "reject",
      },
    ]

    const normalized = normalizeGraphSpecForSave(nodes, edges)

    expect(normalized.spec_version).toBe("1.0")
    expect((normalized.nodes[0] as any).input_mappings).toEqual({ query: "{{ state.q }}" })
    expect((normalized.edges[0] as any).source_handle).toBe("approve")
    expect((normalized.edges[0] as any).target_handle).toBe("reject")
  })

  it("normalizes builder nodes for artifact input mappings", () => {
    const node = {
      id: "n2",
      type: "artifact:custom/tool",
      position: { x: 0, y: 0 },
      data: {},
      input_mappings: { documents: "{{ state.docs }}" },
    } as Node

    const normalized = normalizeBuilderNode(node)

    expect(normalized.data.category).toBe("action")
    expect(normalized.data.inputMappings).toEqual({ documents: "{{ state.docs }}" })
    expect(normalized.data.config).toHaveProperty("input_mappings")
  })
})
