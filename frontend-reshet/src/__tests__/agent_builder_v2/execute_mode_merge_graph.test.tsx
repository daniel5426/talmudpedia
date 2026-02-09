import { Edge, Node } from "@xyflow/react"

import { AgentNodeData } from "@/components/agent-builder/types"
import { getRenderGraphForMode } from "@/components/agent-builder/runtime-merge"

const staticNodes: Node<AgentNodeData>[] = [
  {
    id: "n1",
    type: "join",
    position: { x: 0, y: 0 },
    data: {
      nodeType: "join",
      category: "orchestration",
      displayName: "Join",
      config: {},
      inputType: "context",
      outputType: "decision",
      isConfigured: true,
      hasErrors: false,
    },
  },
]

const staticEdges: Edge[] = [
  {
    id: "e1",
    source: "n1",
    target: "n2",
    sourceHandle: "completed",
  },
]

const overlay = {
  runtimeNodes: [
    {
      id: "runtime-run:child-a",
      type: "agent",
      position: { x: 240, y: 80 },
      data: {
        nodeType: "agent",
        category: "orchestration",
        displayName: "Child Run",
        config: {},
        inputType: "context",
        outputType: "context",
        isConfigured: true,
        hasErrors: false,
        executionStatus: "running",
      },
    } as Node<AgentNodeData>,
  ],
  runtimeEdges: [
    {
      id: "re1",
      source: "n1",
      target: "runtime-run:child-a",
    },
  ] as Edge[],
  runtimeStatusByNodeId: { n1: "failed" as const },
  runtimeNotesByNodeId: { n1: "Denied by policy" },
  takenStaticEdgeIds: ["e1"],
}

describe("execute mode graph merging", () => {
  it("returns static-only graph in build mode", () => {
    const result = getRenderGraphForMode("build", staticNodes, staticEdges, overlay)
    expect(result.nodes).toEqual(staticNodes)
    expect(result.edges).toEqual(staticEdges)
  })

  it("merges runtime overlay in execute mode", () => {
    const result = getRenderGraphForMode("execute", staticNodes, staticEdges, overlay)

    expect(result.nodes).toHaveLength(2)
    expect((result.nodes[0].data as AgentNodeData).executionStatus).toBe("failed")
    expect((result.nodes[0].data as AgentNodeData).hasErrors).toBe(true)

    expect(result.edges).toHaveLength(2)
    expect(result.edges[0].animated).toBe(true)
    expect((result.edges[0].style as Record<string, any>).stroke).toBe("#16a34a")
    expect((result.edges[0].style as Record<string, any>).strokeWidth).toBe(3)
  })
})
