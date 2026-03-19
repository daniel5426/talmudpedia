import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import AgentsPage from "@/app/admin/agents/page"

const pushMock = jest.fn()
const replaceMock = jest.fn()
const listAgentsMock = jest.fn()
const exportAgentToolMock = jest.fn()
const getStatsSummaryMock = jest.fn()

const searchParamsState = { mode: "export-tool" as string | null }

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  useSearchParams: () => ({
    get: (key: string) => (key === "mode" ? searchParamsState.mode : null),
  }),
}))

jest.mock("@/components/agents/CreateAgentDialog", () => ({
  CreateAgentDialog: () => null,
}))

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}))

jest.mock("@/services", () => ({
  agentService: {
    listAgents: (...args: unknown[]) => listAgentsMock(...args),
    exportAgentTool: (...args: unknown[]) => exportAgentToolMock(...args),
  },
  adminService: {
    getStatsSummary: (...args: unknown[]) => getStatsSummaryMock(...args),
  },
}))

describe("agents page export tool flow", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    searchParamsState.mode = "export-tool"
    listAgentsMock.mockResolvedValue({
      agents: [
        {
          id: "agent-1",
          tenant_id: "tenant-1",
          name: "Export Candidate",
          slug: "export-candidate",
          description: "agent description",
          status: "published",
          version: 2,
          created_at: "2026-03-18T00:00:00Z",
          updated_at: "2026-03-18T00:00:00Z",
        },
      ],
      total: 1,
    })
    getStatsSummaryMock.mockResolvedValue({
      agents: {
        agents: [],
      },
    })
    exportAgentToolMock.mockResolvedValue({
      tool_id: "tool-1",
      tool_slug: "agent-tool-1",
      tool_name: "Export Candidate Tool",
      status: "DRAFT",
    })
  })

  it("exports an agent as a tool from the export dialog", async () => {
    render(<AgentsPage />)

    expect(await screen.findByText("Export Agent As Tool")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Tool Name"), { target: { value: "Export Candidate Tool" } })
    fireEvent.click(screen.getByRole("button", { name: "Export Tool" }))

    await waitFor(() => {
      expect(exportAgentToolMock).toHaveBeenCalledWith(
        "agent-1",
        expect.objectContaining({
          name: "Export Candidate Tool",
          description: "agent description",
        })
      )
    })
    expect(pushMock).toHaveBeenCalledWith("/admin/tools")
  })

  it("lets the user switch schema playground modes and generate schema from an example payload", async () => {
    render(<AgentsPage />)

    expect(await screen.findByText("Input Schema Playground")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Example/i }))
    fireEvent.change(
      screen.getByPlaceholderText('{"text":"Summarize this sugya","context":{"tractate":"Berakhot"}}'),
      {
        target: {
          value: '{\n  "query": "What does Rashi say?",\n  "context": {\n    "tractate": "Berakhot"\n  }\n}',
        },
      }
    )
    fireEvent.click(screen.getByRole("button", { name: /Generate Schema From Example/i }))
    fireEvent.click(screen.getByRole("button", { name: "Export Tool" }))

    await waitFor(() => {
      expect(exportAgentToolMock).toHaveBeenCalledWith(
        "agent-1",
        expect.objectContaining({
          input_schema: {
            type: "object",
            properties: {
              query: { type: "string" },
              context: {
                type: "object",
                properties: {
                  tractate: { type: "string" },
                },
                required: ["tractate"],
                additionalProperties: false,
              },
            },
            required: ["query", "context"],
            additionalProperties: false,
          },
        })
      )
    })
  })
})
