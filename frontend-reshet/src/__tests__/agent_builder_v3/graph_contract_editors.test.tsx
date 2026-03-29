import { fireEvent, render, screen } from "@testing-library/react"

import { EndContractEditor, SetStateAssignmentsEditor, StartContractEditor } from "@/components/agent-builder/GraphContractEditors"
import type { AgentGraphAnalysis } from "@/services/agent"

const analysis: AgentGraphAnalysis = {
  spec_version: "3.0",
  inventory: {
    workflow_input: [{ namespace: "workflow_input", key: "input_as_text", type: "string", label: "Input as text" }],
    state: [{ namespace: "state", key: "customer_name", type: "string", label: "customer_name" }],
    node_outputs: [
      {
        node_id: "classify_1",
        node_type: "classify",
        node_label: "Classifier",
        fields: [
          { namespace: "node_output", key: "category", type: "string", label: "category", node_id: "classify_1" },
          { namespace: "node_output", key: "confidence", type: "number", label: "confidence", node_id: "classify_1" },
        ],
      },
    ],
    template_suggestions: { global: [], by_node: {} },
  },
  operator_contracts: {},
  errors: [],
  warnings: [],
}

describe("graph contract editors", () => {
  it("renders built-in workflow input and appends state variables from the Start editor", () => {
    const onChange = jest.fn()

    render(<StartContractEditor value={[{ key: "customer_name", type: "string" }]} onChange={onChange} />)

    expect(screen.getByText("input_as_text")).toBeInTheDocument()
    expect(screen.getByText("Built-in chat workflow input")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /add/i }))

    expect(onChange).toHaveBeenLastCalledWith([
      { key: "customer_name", type: "string" },
      { key: "", type: "string" },
    ])
  })

  it("filters End editor binding options by property type and emits structured value refs", () => {
    const onChange = jest.fn()
    render(
      <EndContractEditor
        value={{
          output_schema: {
            name: "result",
            mode: "simple",
            schema: {
              type: "object",
              additionalProperties: false,
              properties: { reply: { type: "string" } },
              required: ["reply"],
            },
          },
          output_bindings: [],
        }}
        analysis={analysis}
        onChange={onChange}
      />
    )

    fireEvent.click(screen.getByRole("combobox", { name: /select value/i }))

    expect(screen.getByText("Workflow Input")).toBeInTheDocument()
    expect(screen.getByText("Input as text (string)")).toBeInTheDocument()
    expect(screen.getByText("customer_name (string)")).toBeInTheDocument()
    expect(screen.getByText("Classifier / category (string)")).toBeInTheDocument()
    expect(screen.queryByText("Classifier / confidence (number)")).not.toBeInTheDocument()

    fireEvent.click(screen.getByText("customer_name (string)"))

    expect(onChange).toHaveBeenLastCalledWith({
      output_schema: {
        name: "result",
        mode: "simple",
        schema: {
          type: "object",
          additionalProperties: false,
          properties: { reply: { type: "string" } },
          required: ["reply"],
        },
      },
      output_bindings: [
        {
          json_pointer: "/reply",
          value_ref: {
            namespace: "state",
            key: "customer_name",
            expected_type: "string",
            label: "customer_name",
          },
        },
      ],
    })
  })

  it("shows the saved node-output binding label in the End picker trigger", () => {
    render(
      <EndContractEditor
        value={{
          output_schema: {
            name: "result",
            mode: "simple",
            schema: {
              type: "object",
              additionalProperties: false,
              properties: { reply: { type: "string" } },
              required: ["reply"],
            },
          },
          output_bindings: [
            {
              json_pointer: "/reply",
              value_ref: {
                label: "stale label",
                expected_type: "string",
                key: "category",
                node_id: "classify_1",
                namespace: "node_output",
              },
            },
          ],
        }}
        analysis={analysis}
        onChange={jest.fn()}
      />,
    )

    expect(screen.getByRole("combobox", { name: /select value/i })).toHaveTextContent("Classifier / category (string)")
  })

  it("appends a new property row in the End simple editor", () => {
    const onChange = jest.fn()

    render(
      <EndContractEditor
        value={{
          output_schema: {
            name: "result",
            mode: "simple",
            schema: {
              type: "object",
              additionalProperties: false,
              properties: { reply: { type: "string" } },
              required: ["reply"],
            },
          },
          output_bindings: [],
        }}
        analysis={analysis}
        onChange={onChange}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: /add property/i }))

    expect(onChange).toHaveBeenLastCalledWith({
      output_schema: {
        name: "result",
        mode: "simple",
        schema: {
          type: "object",
          additionalProperties: false,
          properties: { reply: { type: "string" } },
          required: ["reply"],
        },
      },
      output_bindings: [],
    })

    expect(screen.getAllByPlaceholderText("property name")).toHaveLength(2)
  })

  it("supports typed set-state assignments with ValueRef sources", () => {
    const onChange = jest.fn()
    const { rerender, container } = render(<SetStateAssignmentsEditor value={[]} analysis={analysis} onChange={onChange} />)

    fireEvent.click(screen.getByRole("button", { name: /add/i }))
    expect(onChange).toHaveBeenLastCalledWith([{ key: "", type: "string" }])

    rerender(
      <SetStateAssignmentsEditor
        value={[{ key: "selected_name", type: "string" }]}
        analysis={analysis}
        onChange={onChange}
      />
    )

    const selects = container.querySelectorAll("select")
    fireEvent.change(selects[1] as HTMLSelectElement, { target: { value: "value_ref" } })

    expect(onChange).toHaveBeenLastCalledWith([
      { key: "selected_name", type: "string", value: undefined, value_ref: undefined },
    ])
  })
})
