import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import AgentsPage from "@/app/admin/agents/page"

const pushMock = jest.fn()
const listAgentsMock = jest.fn()
const deleteAgentMock = jest.fn()

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}))

jest.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: any) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick, disabled }: any) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
}))

jest.mock("@/services", () => ({
  agentService: {
    listAgents: (...args: unknown[]) => listAgentsMock(...args),
    deleteAgent: (...args: unknown[]) => deleteAgentMock(...args),
  },
}))

describe("agents page delete action", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    listAgentsMock.mockResolvedValue({
      agents: [
        {
          id: "agent-1",
          tenant_id: "tenant-1",
          name: "Delete Candidate",
          slug: "delete-candidate",
          status: "draft",
          version: 1,
          created_at: "2026-02-08T00:00:00Z",
          updated_at: "2026-02-08T00:00:00Z",
        },
      ],
      total: 1,
    })
    deleteAgentMock.mockResolvedValue({ success: true })
    jest.spyOn(window, "confirm").mockReturnValue(true)
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it("sends delete request when delete menu item is clicked", async () => {
    render(<AgentsPage />)

    await screen.findByText("Delete Candidate")
    fireEvent.click(await screen.findByText("Delete"))

    await waitFor(() => {
      expect(deleteAgentMock).toHaveBeenCalledWith("agent-1")
    })
  })
})
