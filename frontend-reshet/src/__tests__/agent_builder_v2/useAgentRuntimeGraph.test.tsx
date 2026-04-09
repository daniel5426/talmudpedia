import { act, renderHook, waitFor } from "@testing-library/react"
import { Edge, Node } from "@xyflow/react"

import { AgentNodeData } from "@/components/agent-builder/types"
import { useAgentRuntimeGraph } from "@/hooks/useAgentRuntimeGraph"
import { agentService, AgentExecutionEvent, AgentRunTreeResponse } from "@/services"

jest.mock("@/services", () => ({
  agentService: {
    getRunTree: jest.fn(),
  },
}))

const mockedAgentService = agentService as jest.Mocked<typeof agentService>

const staticNodes: Node<AgentNodeData>[] = [
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

const staticEdges: Edge[] = []

describe("useAgentRuntimeGraph", () => {
  beforeEach(() => {
    jest.useFakeTimers()
    jest.clearAllMocks()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it("keeps reconciling after terminal status until the run tree is fully terminal", async () => {
    const staleTree: AgentRunTreeResponse = {
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
            status: "running",
            depth: 1,
            parent_run_id: "run-root",
            parent_node_id: "agent_1",
            spawn_key: null,
            orchestration_group_id: null,
            children: [],
            groups: [],
          },
        ],
        groups: [],
      },
    }

    const terminalTree: AgentRunTreeResponse = {
      ...staleTree,
      tree: {
        ...staleTree.tree,
        status: "cancelled",
        children: [
          {
            ...staleTree.tree.children[0],
            status: "cancelled",
          },
        ],
      },
    }

    mockedAgentService.getRunTree
      .mockResolvedValueOnce(staleTree)
      .mockResolvedValueOnce(terminalTree)

    const executionEvents: AgentExecutionEvent[] = [
      { event: "node_start", run_id: "run-root", span_id: "agent_1", data: {} },
      {
        event: "orchestration.child_lifecycle",
        run_id: "run-root",
        span_id: "agent_1",
        data: { child_run_id: "child-a", status: "running" },
      },
      { event: "run.cancelled", run_id: "run-root", data: {} },
    ]

    const { result } = renderHook(() =>
      useAgentRuntimeGraph({
        staticNodes,
        staticEdges,
        runId: "run-root",
        executionEvents,
        runStatus: "cancelled",
      }),
    )

    await waitFor(() => {
      expect(mockedAgentService.getRunTree).toHaveBeenCalledTimes(1)
    })

    act(() => {
      jest.advanceTimersByTime(600)
    })

    await waitFor(() => {
      expect(mockedAgentService.getRunTree).toHaveBeenCalledTimes(2)
    })

    await waitFor(() => {
      const childNode = result.current.runtimeNodes.find((node) => node.id === "runtime-run:child-a")
      expect(childNode?.data.executionStatus).toBe("failed")
      expect(result.current.runtimeStatusByNodeId.agent_1).toBe("failed")
    })
  })

  it("reconciles immediately on active runtime events and keeps polling aggressively while running", async () => {
    const runningTree: AgentRunTreeResponse = {
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
            run_id: "child-fast",
            agent_id: "agent-child",
            status: "completed",
            depth: 1,
            parent_run_id: "run-root",
            parent_node_id: "agent_1",
            spawn_key: null,
            orchestration_group_id: null,
            children: [],
            groups: [],
          },
        ],
        groups: [],
      },
    }

    mockedAgentService.getRunTree.mockResolvedValue(runningTree)

    const { result, rerender } = renderHook(
      ({ executionEvents }) =>
        useAgentRuntimeGraph({
          staticNodes,
          staticEdges,
          runId: "run-root",
          executionEvents,
          runStatus: "running",
        }),
      {
        initialProps: {
          executionEvents: [{ event: "node_start", run_id: "run-root", span_id: "agent_1", data: {} }] as AgentExecutionEvent[],
        },
      },
    )

    await waitFor(() => {
      expect(mockedAgentService.getRunTree).toHaveBeenCalledTimes(2)
    })

    rerender({
      executionEvents: [
        { event: "node_start", run_id: "run-root", span_id: "agent_1", data: {} },
        {
          event: "orchestration.child_lifecycle",
          run_id: "run-root",
          span_id: "agent_1",
          data: { child_run_id: "child-fast", status: "running" },
        },
      ] satisfies AgentExecutionEvent[],
    })

    await waitFor(() => {
      expect(mockedAgentService.getRunTree).toHaveBeenCalledTimes(3)
    })

    act(() => {
      jest.advanceTimersByTime(260)
    })

    await waitFor(() => {
      expect(mockedAgentService.getRunTree).toHaveBeenCalledTimes(4)
    })

    await waitFor(() => {
      const childNode = result.current.runtimeNodes.find((node) => node.id === "runtime-run:child-fast")
      expect(childNode?.data.executionStatus).toBe("completed")
    })
  })
})
