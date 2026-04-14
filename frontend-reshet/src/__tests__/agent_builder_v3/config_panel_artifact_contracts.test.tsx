import { render, screen, waitFor } from "@testing-library/react"

import { ConfigPanel } from "@/components/agent-builder/ConfigPanel"

const artifactType = "11111111-1111-1111-1111-111111111111"

jest.mock("@/services", () => ({
  modelsService: {
    listModels: jest.fn(async () => ({ items: [], total: 0, has_more: false, skip: 0, limit: 100, view: "full" })),
  },
  toolsService: {
    listTools: jest.fn(async () => ({ items: [], total: 0, has_more: false, skip: 0, limit: 100, view: "summary" })),
  },
  ragAdminService: {
    listVisualPipelines: jest.fn(async () => ({ items: [], total: 0, has_more: false, skip: 0, limit: 100, view: "summary" })),
  },
  agentService: {
    listAgents: jest.fn(async () => ({ items: [], total: 0, has_more: false, skip: 0, limit: 100, view: "summary" })),
    listOperators: jest.fn(async () => ([
      {
        type: artifactType,
        category: "action",
        display_name: "Tenant Artifact",
        description: "Artifact-backed node",
        reads: [],
        writes: [],
        config_schema: {},
        output_contract: {
          fields: [{ key: "answer", type: "string", label: "Answer" }],
        },
        ui: {
          icon: "Package",
          inputType: "any",
          outputType: "context",
          configFields: [],
          inputs: [
            { name: "query", type: "string", required: true, description: "Question to answer" },
            { name: "user_id", type: "string", required: false, description: "Optional user id" },
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

describe("ConfigPanel artifact contracts", () => {
  it("renders artifact field-mapping inputs from the backend operator contract", async () => {
    render(
      <ConfigPanel
        nodeId={artifactType}
        data={{
          nodeType: artifactType as any,
          category: "action",
          displayName: "Tenant Artifact",
          config: {},
          inputType: "any",
          outputType: "context",
          isConfigured: true,
          hasErrors: false,
        }}
        onConfigChange={jest.fn()}
        onClose={jest.fn()}
        availableVariables={[]}
        graphAnalysis={null}
      />,
    )

    await waitFor(() => expect(screen.queryByText("Loading resources...")).not.toBeInTheDocument())

    expect(screen.getByText("Field Mapping")).toBeInTheDocument()
    expect(screen.getByText("query")).toBeInTheDocument()
    expect(screen.getByText("user_id")).toBeInTheDocument()
    expect(screen.getByText("string *")).toBeInTheDocument()
  })
})
