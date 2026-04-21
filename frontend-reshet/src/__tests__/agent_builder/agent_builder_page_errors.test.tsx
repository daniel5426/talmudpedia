import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import AgentBuilderPage from "@/app/admin/agents/[id]/builder/page"
import { HttpRequestError } from "@/services/http"

const pushMock = jest.fn()
const getAgentMock = jest.fn()
const updateAgentMock = jest.fn()
const publishAgentMock = jest.fn()

jest.mock("next/navigation", () => ({
  useParams: () => ({ id: "agent-123" }),
  useRouter: () => ({ push: pushMock }),
}))

jest.mock("@/services", () => ({
  agentService: {
    getAgent: (...args: unknown[]) => getAgentMock(...args),
    updateAgent: (...args: unknown[]) => updateAgentMock(...args),
    publishAgent: (...args: unknown[]) => publishAgentMock(...args),
  },
}))

jest.mock("@/components/ui/custom-breadcrumb", () => ({
  CustomBreadcrumb: () => <div data-testid="breadcrumb" />,
}))

jest.mock("@/components/agent-builder", () => ({
  AgentBuilder: () => <div data-testid="agent-builder" />,
}))

jest.mock("@/components/builder", () => ({
  HeaderConfigEditor: () => null,
}))

describe("agent builder page errors", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    getAgentMock.mockResolvedValue({
      id: "agent-123",
      organization_id: "organization-1",
      name: "Draft Agent",
      slug: "draft-agent",
      status: "draft",
      version: 1,
      show_in_playground: true,
      graph_definition: { spec_version: "4.0", nodes: [], edges: [] },
      created_at: "2026-04-01T00:00:00Z",
      updated_at: "2026-04-01T00:00:00Z",
    })
    publishAgentMock.mockResolvedValue({})
  })

  it("shows the structured backend save error instead of a generic message", async () => {
    updateAgentMock.mockRejectedValue(
      new HttpRequestError("Graph write rejected", 422, {
        message: "Graph write rejected",
        errors: [{ message: "Config field 'temperature' is not valid for agent node type 'agent'" }],
      }),
    )

    render(<AgentBuilderPage />)

    await screen.findByTestId("agent-builder")
    fireEvent.click(screen.getByText("Save Draft"))

    await waitFor(() => {
      expect(screen.getByText("Config field 'temperature' is not valid for agent node type 'agent'")).toBeInTheDocument()
    })
  })
})
