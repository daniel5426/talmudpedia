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

  it("marks the single classify branch from branch_taken output", () => {
    const classifyNodes: Node<AgentNodeData>[] = [
      {
        id: "classify_1",
        type: "classify",
        position: { x: 0, y: 0 },
        data: {
          nodeType: "classify",
          category: "reasoning",
          displayName: "Classify",
          config: {},
          inputType: "message",
          outputType: "decision",
          isConfigured: true,
          hasErrors: false,
        },
      },
    ]

    const classifyEdges: Edge[] = [
      { id: "e-support", source: "classify_1", target: "support_node", sourceHandle: "cat_support" },
      { id: "e-else", source: "classify_1", target: "fallback_node", sourceHandle: "else" },
    ]

    const events: AgentExecutionEvent[] = [
      {
        event: "node_end",
        run_id: "run-root",
        span_id: "classify_1",
        data: { output: { selected: "support", branch_taken: "cat_support" } },
      },
    ]

    const state = applyRuntimeEvents(createEmptyRuntimeGraphState(), events, classifyNodes, classifyEdges)

    expect(state.takenStaticEdgeIds).toEqual(["e-support"])
  })

  it("tracks static node status and marks linear executed edges from node events", () => {
    const nodes: Node<AgentNodeData>[] = [
      {
        id: "start",
        type: "start",
        position: { x: 0, y: 0 },
        data: {
          nodeType: "start",
          category: "control",
          displayName: "Start",
          config: {},
          inputType: "any",
          outputType: "message",
          isConfigured: true,
          hasErrors: false,
        },
      },
      {
        id: "agent_1",
        type: "agent",
        position: { x: 200, y: 0 },
        data: {
          nodeType: "agent",
          category: "reasoning",
          displayName: "Agent",
          config: {},
          inputType: "message",
          outputType: "message",
          isConfigured: true,
          hasErrors: false,
        },
      },
      {
        id: "end",
        type: "end",
        position: { x: 400, y: 0 },
        data: {
          nodeType: "end",
          category: "control",
          displayName: "End",
          config: {},
          inputType: "any",
          outputType: "any",
          isConfigured: true,
          hasErrors: false,
        },
      },
    ]

    const edges: Edge[] = [
      { id: "e-start-agent", source: "start", target: "agent_1" },
      { id: "e-agent-end", source: "agent_1", target: "end" },
    ]

    const events: AgentExecutionEvent[] = [
      { event: "node_start", run_id: "run-root", span_id: "start", data: {} },
      { event: "node_end", run_id: "run-root", span_id: "start", data: { output: {} } },
      { event: "node_start", run_id: "run-root", span_id: "agent_1", data: {} },
      { event: "node_end", run_id: "run-root", span_id: "agent_1", data: { output: {} } },
      { event: "node_start", run_id: "run-root", span_id: "end", data: {} },
    ]

    const state = applyRuntimeEvents(createEmptyRuntimeGraphState(), events, nodes, edges)

    expect(state.runtimeStatusByNodeId.start).toBe("completed")
    expect(state.runtimeStatusByNodeId.agent_1).toBe("completed")
    expect(state.runtimeStatusByNodeId.end).toBe("running")
    expect(state.takenStaticEdgeIds).toEqual(["e-start-agent", "e-agent-end"])
  })

  it("treats on_chain events as live node execution events", () => {
    const nodes: Node<AgentNodeData>[] = [
      {
        id: "agent_1",
        type: "agent",
        position: { x: 0, y: 0 },
        data: {
          nodeType: "agent",
          category: "reasoning",
          displayName: "Agent",
          config: {},
          inputType: "message",
          outputType: "message",
          isConfigured: true,
          hasErrors: false,
        },
      },
    ]

    const state = applyRuntimeEvents(
      createEmptyRuntimeGraphState(),
      [
        { event: "on_chain_start", run_id: "run-root", span_id: "agent_1", data: {} },
        { event: "on_chain_end", run_id: "run-root", span_id: "agent_1", data: { output: {} } },
      ],
      nodes,
      [],
    )

    expect(state.runtimeStatusByNodeId.agent_1).toBe("completed")
  })

  it("clears stuck running nodes when the run fails", () => {
    const nodes: Node<AgentNodeData>[] = [
      {
        id: "end",
        type: "end",
        position: { x: 0, y: 0 },
        data: {
          nodeType: "end",
          category: "control",
          displayName: "End",
          config: {},
          inputType: "any",
          outputType: "any",
          isConfigured: true,
          hasErrors: false,
        },
      },
    ]

    const events: AgentExecutionEvent[] = [
      { event: "node_start", run_id: "run-root", span_id: "end", data: {} },
      { event: "run.failed", run_id: "run-root", data: { error: "Speech-to-text source resolved to no attachments" } },
    ]

    const state = applyRuntimeEvents(createEmptyRuntimeGraphState(), events, nodes, [])

    expect(state.runtimeStatusByNodeId.end).toBe("failed")
    expect(state.runtimeNotesByNodeId.end).toBe("Speech-to-text source resolved to no attachments")
  })
})
