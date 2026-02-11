import { Edge, Node } from "@xyflow/react"

import { AgentNodeData } from "@/components/agent-builder/types"
import { applyRuntimeEvents, createEmptyRuntimeGraphState, reconcileRuntimeTree } from "@/services/agent-runtime-graph"
import { AgentExecutionEvent, AgentRunTreeResponse } from "@/services"

const staticNodes: Node<AgentNodeData>[] = [
  {
    id: "spawn_core_group",
    type: "spawn_group",
    position: { x: 100, y: 100 },
    data: {
      nodeType: "spawn_group",
      category: "orchestration",
      displayName: "Spawn Group",
      config: {},
      inputType: "context",
      outputType: "context",
      isConfigured: true,
      hasErrors: false,
    },
  },
]

const staticEdges: Edge[] = []

describe("run tree reconciliation", () => {
  it("lets tree status override stream-only divergence and keep terminal authority", () => {
    const streamEvents: AgentExecutionEvent[] = [
      {
        event: "orchestration.spawn_decision",
        run_id: "run-root",
        span_id: "spawn_core_group",
        data: { spawned_run_ids: ["child-a"] },
      },
      {
        event: "orchestration.child_lifecycle",
        run_id: "run-root",
        span_id: "spawn_core_group",
        data: { child_run_id: "child-a", status: "running" },
      },
    ]

    const treePayload: AgentRunTreeResponse = {
      root_run_id: "run-root",
      node_count: 2,
      tree: {
        run_id: "run-root",
        agent_id: "agent-root",
        status: "running",
        depth: 0,
        parent_run_id: null,
        parent_node_id: null,
        spawn_key: null,
        orchestration_group_id: null,
        children: [
          {
            run_id: "child-a",
            agent_id: "agent-child",
            status: "completed",
            depth: 1,
            parent_run_id: "run-root",
            parent_node_id: "spawn_core_group",
            spawn_key: "k1",
            orchestration_group_id: null,
            children: [],
            groups: [],
          },
        ],
        groups: [],
      },
    }

    let state = applyRuntimeEvents(createEmptyRuntimeGraphState(), streamEvents, staticNodes, staticEdges)
    const childBefore = state.runtimeNodes.find((node) => node.id === "runtime-run:child-a")
    expect(childBefore?.data.executionStatus).toBe("running")

    state = reconcileRuntimeTree(state, treePayload)
    const childAfterTree = state.runtimeNodes.find((node) => node.id === "runtime-run:child-a")
    expect(childAfterTree?.data.executionStatus).toBe("completed")
    expect(state.runtimeNodes.some((node) => node.id === "runtime-run:run-root")).toBe(false)

    const postTreeEvent: AgentExecutionEvent[] = [
      {
        event: "orchestration.child_lifecycle",
        run_id: "run-root",
        span_id: "spawn_core_group",
        data: { child_run_id: "child-a", status: "running" },
      },
    ]
    state = applyRuntimeEvents(state, postTreeEvent, staticNodes, staticEdges)
    const childAfterLateEvent = state.runtimeNodes.find((node) => node.id === "runtime-run:child-a")
    expect(childAfterLateEvent?.data.executionStatus).toBe("completed")
  })
})
