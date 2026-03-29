import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import { getTemplateSuggestionsForNode } from "@/components/agent-builder/template-suggestions"
import { PromptMentionInput } from "@/components/shared/PromptMentionInput"
import type { AgentGraphAnalysis } from "@/services/agent"

jest.mock("@/services/prompts", () => ({
  promptsService: {
    searchMentions: jest.fn(async () => []),
    getPrompt: jest.fn(async () => ({ id: "prompt-1", name: "Prompt" })),
  },
}))

beforeAll(() => {
  Object.defineProperty(Range.prototype, "getBoundingClientRect", {
    configurable: true,
    value: () => ({
      top: 16,
      left: 16,
      bottom: 32,
      right: 48,
      width: 32,
      height: 16,
      x: 16,
      y: 16,
      toJSON: () => ({}),
    }),
  })
})

const analysis: AgentGraphAnalysis = {
  spec_version: "3.0",
  inventory: {
    workflow_input: [{ namespace: "workflow_input", key: "input_as_text", type: "string", label: "Input as text" }],
    state: [{ namespace: "state", key: "customer_name", type: "string", label: "customer_name" }],
    node_outputs: [
      {
        node_id: "agent_1",
        node_type: "agent",
        node_label: "Reply Agent",
        fields: [{ namespace: "node_output", key: "output_text", type: "string", label: "Output Text", node_id: "agent_1" }],
      },
      {
        node_id: "classify_1",
        node_type: "classify",
        node_label: "Classifier",
        fields: [{ namespace: "node_output", key: "category", type: "string", label: "category", node_id: "classify_1" }],
      },
    ],
    template_suggestions: {
      global: [
        {
          id: "workflow_input:input_as_text",
          display_label: "Input as text",
          insert_text: "workflow_input.input_as_text",
          type: "string",
          namespace: "workflow_input",
          key: "input_as_text",
        },
        {
          id: "state:customer_name",
          display_label: "customer_name",
          insert_text: "state.customer_name",
          type: "string",
          namespace: "state",
          key: "customer_name",
        },
      ],
      by_node: {
        end_1: [
          {
            id: "node_output:agent_1:output_text",
            display_label: "Reply Agent / Output Text",
            insert_text: "upstream.agent_1.output_text",
            type: "string",
            namespace: "node_output",
            key: "output_text",
            node_id: "agent_1",
          },
        ],
        classify_1: [
          {
            id: "node_output:start:input",
            display_label: "Start / Output",
            insert_text: "upstream.start.output",
            type: "string",
            namespace: "node_output",
            key: "output",
            node_id: "start",
          },
        ],
      },
    },
  },
  operator_contracts: {},
  errors: [],
  warnings: [],
}

function setEditorValue(editor: HTMLElement, text: string) {
  editor.textContent = text
  const textNode = editor.firstChild
  if (!textNode) return
  const selection = window.getSelection()
  const range = document.createRange()
  range.setStart(textNode, text.length)
  range.collapse(true)
  selection?.removeAllRanges()
  selection?.addRange(range)
}

describe("builder template suggestions", () => {
  it("returns global suggestions plus only direct-input node suggestions for the selected node", () => {
    const suggestions = getTemplateSuggestionsForNode(analysis, "end_1")

    expect(suggestions.map((item) => item.displayLabel)).toEqual([
      "Input as text",
      "customer_name",
      "Reply Agent / Output Text",
    ])
    expect(suggestions.map((item) => item.insertText)).toEqual([
      "workflow_input.input_as_text",
      "state.customer_name",
      "upstream.agent_1.output_text",
    ])
    expect(suggestions.some((item) => item.displayLabel.includes("Classifier"))).toBe(false)
  })

  it("shows friendly labels in the mention menu and inserts the stable token", async () => {
    const onChange = jest.fn()

    render(
      <PromptMentionInput
        value=""
        onChange={onChange}
        availableVariables={getTemplateSuggestionsForNode(analysis, "end_1")}
        multiline={false}
      />,
    )

    const editor = screen.getByRole("textbox")
    fireEvent.focus(editor)
    setEditorValue(editor, "Use @")
    fireEvent.input(editor)

    await waitFor(() => {
      expect(screen.getByText("Input as text")).toBeInTheDocument()
      expect(screen.getByText("Reply Agent / Output Text")).toBeInTheDocument()
    })

    expect(screen.queryByText("workflow_input.input_as_text")).not.toBeInTheDocument()
    expect(screen.queryByText("upstream.agent_1.output_text")).not.toBeInTheDocument()

    fireEvent.mouseDown(screen.getByText("Reply Agent / Output Text"))

    expect(onChange).toHaveBeenLastCalledWith("Use {{ upstream.agent_1.output_text }}")
  })
})
