import { act, renderHook, waitFor } from "@testing-library/react"
import type { Edge, Node } from "@xyflow/react"

import { useAgentGraphAnalysis } from "@/components/agent-builder/useAgentGraphAnalysis"
import type { AgentNodeData } from "@/components/agent-builder/types"
import { agentService } from "@/services"

jest.mock("@/services", () => ({
  agentService: {
    analyzeGraph: jest.fn(),
  },
}))

const mockedAgentService = agentService as jest.Mocked<typeof agentService>

function buildNode(id: string, type: string, config: Record<string, unknown> = {}): Node<AgentNodeData> {
  return {
    id,
    type,
    position: { x: 0, y: 0 },
    data: {
      nodeType: type as AgentNodeData["nodeType"],
      category: type === "start" || type === "end" ? "control" : "reasoning",
      displayName: type,
      config,
      inputType: "any",
      outputType: "any",
      isConfigured: true,
      hasErrors: false,
    },
    config,
  } as Node<AgentNodeData>
}

describe("useAgentGraphAnalysis", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it("debounces analysis requests and sends a normalized v3 graph", async () => {
    mockedAgentService.analyzeGraph.mockResolvedValue({
      agent_id: "agent-1",
      graph_definition: { spec_version: "3.0", nodes: [], edges: [] },
      analysis: {
        spec_version: "3.0",
        inventory: {
          workflow_input: [{ key: "input_as_text", type: "string", namespace: "workflow_input" }],
          state: [],
          node_outputs: [],
          template_variables: [],
        },
        operator_contracts: {},
        errors: [],
        warnings: [],
      },
    } as any)

    const nodes = [buildNode("start", "start"), buildNode("end", "end")]
    const edges: Edge[] = []

    const { result } = renderHook(() => useAgentGraphAnalysis("agent-1", nodes, edges))

    expect(result.current.analysis).toBeNull()
    expect(mockedAgentService.analyzeGraph).not.toHaveBeenCalled()

    await act(async () => {
      jest.advanceTimersByTime(180)
    })

    await waitFor(() => {
      expect(mockedAgentService.analyzeGraph).toHaveBeenCalledWith(
        "agent-1",
        expect.objectContaining({
          spec_version: "3.0",
          nodes: expect.any(Array),
          edges: [],
        }),
      )
    })

    await waitFor(() => {
      expect(result.current.analysis?.spec_version).toBe("3.0")
    })
  })
})
