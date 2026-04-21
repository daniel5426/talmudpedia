import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import AgentsPage from "@/app/admin/agents/page"

const pushMock = jest.fn()
const replaceMock = jest.fn()
const listAgentsMock = jest.fn()
const exportAgentToolMock = jest.fn()
const getStatsSummaryMock = jest.fn()

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  useSearchParams: () => ({
    get: (key: string) => (key === "create" ? null : null),
  }),
}))

jest.mock("@/components/agents/CreateAgentDialog", () => ({
  CreateAgentDialog: () => null,
}))

jest.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({
    children,
    onClick,
    disabled,
  }: {
    children: React.ReactNode
    onClick?: () => void
    disabled?: boolean
  }) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  DropdownMenuSeparator: () => null,
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

describe("agents page tool binding flow", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    listAgentsMock.mockResolvedValue({
      items: [
        {
          id: "agent-1",
          organization_id: "organization-1",
          name: "Export Candidate",
          slug: "export-candidate",
          description: "agent description",
          status: "published",
          version: 2,
          is_tool_enabled: false,
          tool_binding_status: null,
          created_at: "2026-03-18T00:00:00Z",
          updated_at: "2026-03-18T00:00:00Z",
        },
      ],
      total: 1,
      has_more: false,
      skip: 0,
      limit: 100,
      view: "summary",
    })
    getStatsSummaryMock.mockResolvedValue({
      agents: {
        agents: [],
      },
    })
    exportAgentToolMock.mockResolvedValue({
      tool_id: "tool-1",
      tool_slug: "agent-tool-1",
      tool_name: "Export Candidate",
      status: "draft",
    })
  })

  it("makes an agent a tool from the card menu", async () => {
    render(<AgentsPage />)

    expect(await screen.findByText("Export Candidate")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /agent actions for export candidate/i }))
    fireEvent.click(screen.getByText("Make tool"))

    await waitFor(() => {
      expect(exportAgentToolMock).toHaveBeenCalledWith("agent-1")
    })
    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalledTimes(2)
    })
  })

  it("shows tool status in the card footer", async () => {
    listAgentsMock.mockResolvedValueOnce({
      items: [
        {
          id: "agent-1",
          organization_id: "organization-1",
          name: "Bound Agent",
          slug: "bound-agent",
          description: "agent description",
          status: "published",
          version: 2,
          is_tool_enabled: true,
          tool_binding_status: "published",
          created_at: "2026-03-18T00:00:00Z",
          updated_at: "2026-03-18T00:00:00Z",
        },
      ],
      total: 1,
      has_more: false,
      skip: 0,
      limit: 100,
      view: "summary",
    })

    render(<AgentsPage />)

    expect(await screen.findByText("Tool published")).toBeInTheDocument()
  })
})
