import { Edge, Node } from "@xyflow/react"

import { AgentNodeData } from "@/components/agent-builder/types"
import { applyRuntimeEvents, createEmptyRuntimeGraphState } from "@/services/agent-runtime-graph"
import { AgentExecutionEvent } from "@/services"

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

const staticEdges: Edge[] = [
  {
    id: "e-join-completed",
    source: "spawn_core_group",
    target: "join_core",
    sourceHandle: "completed",
  },
]

describe("runtime overlay reducer", () => {
  it("applies spawn/lifecycle/join/cancel/policy events", () => {
    const events: AgentExecutionEvent[] = [
      {
        event: "orchestration.spawn_decision",
        run_id: "run-root",
        span_id: "spawn_core_group",
        data: {
          spawned_run_ids: ["child-a", "child-b"],
          idempotent: false,
        },
      },
      {
        event: "orchestration.child_lifecycle",
        run_id: "run-root",
        span_id: "spawn_core_group",
        data: { child_run_id: "child-a", status: "running", orchestration_group_id: "group-1" },
      },
      {
        event: "orchestration.join_decision",
        run_id: "run-root",
        span_id: "spawn_core_group",
        data: {
          group_id: "group-1",
          status: "completed_with_errors",
          complete: true,
          success_count: 1,
          failure_count: 1,
          running_count: 0,
        },
      },
      {
        event: "orchestration.cancellation_propagation",
        run_id: "run-root",
        span_id: "spawn_core_group",
        data: { cancelled_run_ids: ["child-b"], reason: "cleanup" },
      },
      {
        event: "orchestration.policy_deny",
        run_id: "run-root",
        span_id: "spawn_core_group",
        data: { reason: "policy denied" },
      },
      {
        event: "node_end",
        run_id: "run-root",
        span_id: "spawn_core_group",
        data: { output: { next: "completed" } },
      },
    ]

    const state = applyRuntimeEvents(createEmptyRuntimeGraphState(), events, staticNodes, staticEdges)

    expect(state.runtimeNodes.some((node) => node.id.startsWith("runtime-event:run-root:orchestration.spawn_decision"))).toBe(true)
    expect(state.runtimeNodes.some((node) => node.id === "runtime-run:child-a")).toBe(true)
    expect(state.runtimeNodes.some((node) => node.id === "runtime-run:child-b")).toBe(true)
    expect(state.runtimeNodes.some((node) => node.id.startsWith("runtime-event:run-root:orchestration.join_decision"))).toBe(true)

    const cancelledChild = state.runtimeNodes.find((node) => node.id === "runtime-run:child-b")
    expect(cancelledChild?.data.executionStatus).toBe("failed")
    expect(state.runtimeStatusByNodeId.spawn_core_group).toBe("failed")
    expect(state.takenStaticEdgeIds).toContain("e-join-completed")
  })
})
