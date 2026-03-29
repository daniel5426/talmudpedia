import type { ReactElement } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import { ConfigPanel } from "@/components/agent-builder/ConfigPanel"
import { DirectionProvider } from "@/components/direction-provider"
import type { AgentGraphAnalysis } from "@/services/agent"

jest.mock("@/services", () => ({
  modelsService: {
    listModels: jest.fn(async () => ({ models: [], total: 0 })),
  },
  toolsService: {
    listTools: jest.fn(async () => ({ tools: [], total: 0 })),
  },
  ragAdminService: {
    listVisualPipelines: jest.fn(async () => ({ pipelines: [] })),
  },
  agentService: {
    listAgents: jest.fn(async () => ({ agents: [], total: 0 })),
    listOperators: jest.fn(async () => ([
      {
        type: "classify",
        category: "reasoning",
        display_name: "Classify",
        description: "Classify input",
        reads: [],
        writes: [],
        config_schema: {},
        field_contracts: {
          input_source: { type: "value_ref", allowed_types: ["string"] },
        },
        ui: {
          icon: "ListFilter",
          inputType: "message",
          outputType: "decision",
          configFields: [
            { name: "input_source", label: "Input Source", fieldType: "value_ref", required: false },
          ],
        },
      },
    ])),
  },
}))

jest.mock("@/contexts/TenantContext", () => ({
  useTenant: () => ({ currentTenant: null }),
}))

jest.mock("@/components/shared/PromptModal", () => ({
  PromptModal: () => null,
}))

jest.mock("@/components/shared/usePromptMentionModal", () => ({
  usePromptMentionModal: () => ({
    open: false,
    promptId: null,
    context: null,
    openPromptMentionModal: jest.fn(),
    handleOpenChange: jest.fn(),
  }),
}))

const analysis: AgentGraphAnalysis = {
  spec_version: "3.0",
  inventory: {
    workflow_input: [
      { namespace: "workflow_input", key: "input_as_text", type: "string", label: "Input as text" },
      { namespace: "workflow_input", key: "attempt_count", type: "number", label: "attempt_count" },
    ],
    state: [
      { namespace: "state", key: "customer_name", type: "string", label: "customer_name" },
    ],
    node_outputs: [],
    template_suggestions: { global: [], by_node: {} },
  },
  operator_contracts: {},
  errors: [],
  warnings: [],
}

function renderWithDirection(ui: ReactElement) {
  return render(<DirectionProvider initialDirection="ltr">{ui}</DirectionProvider>)
}

describe("ConfigPanel value_ref contracts", () => {
  it("filters value-ref options using backend field contracts", async () => {
    renderWithDirection(
      <ConfigPanel
        nodeId="classify_1"
        data={{
          nodeType: "classify",
          category: "reasoning",
          displayName: "Classify",
          config: {},
          inputType: "message",
          outputType: "decision",
          isConfigured: true,
          hasErrors: false,
        }}
        onConfigChange={jest.fn()}
        onClose={jest.fn()}
        availableVariables={[]}
        graphAnalysis={analysis}
      />,
    )

    await waitFor(() => expect(screen.queryByText("Loading resources...")).not.toBeInTheDocument())

    fireEvent.click(screen.getByRole("combobox", { name: /select value/i }))

    expect(screen.getByText("Input as text (string)")).toBeInTheDocument()
    expect(screen.queryByText("attempt_count")).not.toBeInTheDocument()
  })

  it("opens End structured output in a modal from the output row", async () => {
    renderWithDirection(
      <ConfigPanel
        nodeId="end_1"
        data={{
          nodeType: "end",
          category: "end",
          displayName: "End",
          config: {},
          inputType: "message",
          outputType: "final",
          isConfigured: true,
          hasErrors: false,
        }}
        onConfigChange={jest.fn()}
        onClose={jest.fn()}
        availableVariables={[]}
        graphAnalysis={analysis}
      />,
    )

    await waitFor(() => expect(screen.queryByText("Loading resources...")).not.toBeInTheDocument())

    fireEvent.click(screen.getByRole("button", { name: /add schema/i }))

    expect(screen.getByText("Structured output (JSON)")).toBeInTheDocument()
  })

  it("saves the selected End property binding from the modal", async () => {
    const onConfigChange = jest.fn()

    renderWithDirection(
      <ConfigPanel
        nodeId="end_1"
        data={{
          nodeType: "end",
          category: "end",
          displayName: "End",
          config: {},
          inputType: "message",
          outputType: "final",
          isConfigured: true,
          hasErrors: false,
        }}
        onConfigChange={onConfigChange}
        onClose={jest.fn()}
        availableVariables={[]}
        graphAnalysis={analysis}
      />,
    )

    await waitFor(() => expect(screen.queryByText("Loading resources...")).not.toBeInTheDocument())

    fireEvent.click(screen.getByRole("button", { name: /add schema/i }))
    fireEvent.click(screen.getByRole("combobox", { name: /select value/i }))
    fireEvent.click(screen.getByText("customer_name (string)"))
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }))

    expect(onConfigChange).toHaveBeenLastCalledWith(
      "end_1",
      expect.objectContaining({
        output_bindings: [
          {
            json_pointer: "/response",
            value_ref: expect.objectContaining({
              namespace: "state",
              key: "customer_name",
            }),
          },
        ],
      }),
    )
  })
})
