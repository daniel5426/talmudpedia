import { render } from "@testing-library/react"

import { BaseNode } from "@/components/agent-builder/nodes/BaseNode"
import type { AgentNodeData } from "@/components/agent-builder/types"

jest.mock("@xyflow/react", () => ({
  __esModule: true,
  Handle: ({ id, type }: any) => <div data-handleid={id} data-handletype={type} />,
  Position: { Left: "left", Right: "right" },
}))

const buildNodeData = (overrides: Partial<AgentNodeData>): AgentNodeData => ({
  nodeType: "classify",
  category: "reasoning",
  displayName: "Test Node",
  config: {},
  inputType: "any",
  outputType: "any",
  isConfigured: true,
  hasErrors: false,
  ...overrides,
})

const renderNode = (data: AgentNodeData) =>
  render(<BaseNode {...({ id: "node-1", data, selected: false } as any)} />)

const collectHandleIds = (container: HTMLElement) =>
  Array.from(container.querySelectorAll("[data-handleid]"))
    .map((el) => el.getAttribute("data-handleid"))
    .filter((id): id is string => id !== null)

describe("agent builder branch handles", () => {
  it("classify generates fallback and deduped handle ids", () => {
    const { container } = renderNode(
      buildNodeData({
        nodeType: "classify",
        config: {
          categories: [
            { name: "" },
            { name: "support" },
            { name: "support" },
            { name: "" },
          ],
        },
      })
    )

    expect(collectHandleIds(container)).toEqual([
      "category_0",
      "support",
      "support_1",
      "category_3",
    ])
  })

  it("if_else generates fallback, deduped handles and includes else", () => {
    const { container } = renderNode(
      buildNodeData({
        nodeType: "if_else",
        category: "logic",
        config: {
          conditions: [
            { name: "" },
            { name: "yes" },
            { name: "yes" },
          ],
        },
      })
    )

    expect(collectHandleIds(container)).toEqual([
      "condition_0",
      "yes",
      "yes_1",
      "else",
    ])
  })
})
