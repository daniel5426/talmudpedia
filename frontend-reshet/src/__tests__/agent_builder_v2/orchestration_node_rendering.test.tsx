import { render } from "@testing-library/react"

import { BaseNode } from "@/components/agent-builder/nodes/BaseNode"
import { nodeTypes } from "@/components/agent-builder/nodes"
import type { AgentNodeData } from "@/components/agent-builder/types"

jest.mock("@xyflow/react", () => ({
  __esModule: true,
  Handle: ({ id, type }: any) => <div data-handleid={id} data-handletype={type} />,
  Position: { Left: "left", Right: "right" },
}))

const buildNodeData = (overrides: Partial<AgentNodeData>): AgentNodeData => ({
  nodeType: "join",
  category: "orchestration",
  displayName: "Test Node",
  config: {},
  inputType: "context",
  outputType: "decision",
  isConfigured: true,
  hasErrors: false,
  ...overrides,
})

const renderNode = (data: AgentNodeData) =>
  render(<BaseNode {...({ id: "node-1", data, selected: false } as any)} />)

const collectSourceHandleIds = (container: HTMLElement) =>
  Array.from(container.querySelectorAll("[data-handletype='source']"))
    .map((el) => el.getAttribute("data-handleid"))
    .filter((id): id is string => id !== null)

describe("orchestration node rendering", () => {
  it("registers v2 orchestration node types in the renderer map", () => {
    expect(nodeTypes.spawn_run).toBe(BaseNode)
    expect(nodeTypes.spawn_group).toBe(BaseNode)
    expect(nodeTypes.join).toBe(BaseNode)
    expect(nodeTypes.router).toBe(BaseNode)
    expect(nodeTypes.judge).toBe(BaseNode)
    expect(nodeTypes.replan).toBe(BaseNode)
    expect(nodeTypes.cancel_subtree).toBe(BaseNode)
  })

  it("renders join/router/judge/replan branch handles", () => {
    const join = renderNode(buildNodeData({ nodeType: "join", config: {} }))
    expect(collectSourceHandleIds(join.container)).toEqual([
      "completed",
      "completed_with_errors",
      "failed",
      "timed_out",
      "pending",
    ])

    const router = renderNode(buildNodeData({
      nodeType: "router",
      config: {
        routes: [
          { name: "replan" },
          { name: "continue" },
        ],
      },
    }))
    expect(collectSourceHandleIds(router.container)).toEqual(["replan", "continue", "default"])

    const judge = renderNode(buildNodeData({
      nodeType: "judge",
      config: { outcomes: ["accept", "reject"] },
    }))
    expect(collectSourceHandleIds(judge.container)).toEqual(["accept", "reject"])

    const replan = renderNode(buildNodeData({ nodeType: "replan", config: {} }))
    expect(collectSourceHandleIds(replan.container)).toEqual(["replan", "continue"])
  })
})
