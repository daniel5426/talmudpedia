import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import ResourcePoliciesPage from "@/app/admin/resource-policies/page"

const listPolicySetsMock = jest.fn()
const getPolicySetMock = jest.fn()
const createPolicySetMock = jest.fn()
const updateRuleMock = jest.fn()
const upsertAssignmentMock = jest.fn()
const listAssignmentsMock = jest.fn()
const setPublishedAppDefaultPolicyMock = jest.fn()
const setEmbeddedAgentDefaultPolicyMock = jest.fn()

const listAgentsMock = jest.fn()
const listModelsMock = jest.fn()
const listToolsMock = jest.fn()
const listKnowledgeStoresMock = jest.fn()
const listPublishedAppsMock = jest.fn()
const getUsersMock = jest.fn()
const routerReplaceMock = jest.fn()
let mockSearchParams = new URLSearchParams()

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

jest.mock("@/services/resource-policies", () => ({
  resourcePoliciesService: {
    listPolicySets: (...args: unknown[]) => listPolicySetsMock(...args),
    getPolicySet: (...args: unknown[]) => getPolicySetMock(...args),
    createPolicySet: (...args: unknown[]) => createPolicySetMock(...args),
    updatePolicySet: jest.fn(),
    deletePolicySet: jest.fn(),
    addInclude: jest.fn(),
    removeInclude: jest.fn(),
    createRule: jest.fn(),
    updateRule: (...args: unknown[]) => updateRuleMock(...args),
    deleteRule: jest.fn(),
    listAssignments: (...args: unknown[]) => listAssignmentsMock(...args),
    upsertAssignment: (...args: unknown[]) => upsertAssignmentMock(...args),
    deleteAssignment: jest.fn(),
    setPublishedAppDefaultPolicy: (...args: unknown[]) => setPublishedAppDefaultPolicyMock(...args),
    setEmbeddedAgentDefaultPolicy: (...args: unknown[]) => setEmbeddedAgentDefaultPolicyMock(...args),
  },
}))

jest.mock("@/services/agent", () => ({
  agentService: {
    listAgents: (...args: unknown[]) => listAgentsMock(...args),
  },
}))

jest.mock("@/services/models", () => ({
  modelsService: {
    listModels: (...args: unknown[]) => listModelsMock(...args),
  },
}))

jest.mock("@/services/tools", () => ({
  toolsService: {
    listTools: (...args: unknown[]) => listToolsMock(...args),
  },
}))

jest.mock("@/services/knowledge-stores", () => ({
  knowledgeStoresService: {
    list: (...args: unknown[]) => listKnowledgeStoresMock(...args),
  },
}))

jest.mock("@/services/published-apps", () => ({
  publishedAppsService: {
    list: (...args: unknown[]) => listPublishedAppsMock(...args),
  },
}))

jest.mock("@/services/admin", () => ({
  adminService: {
    getUsers: (...args: unknown[]) => getUsersMock(...args),
  },
}))

jest.mock("next/navigation", () => ({
  usePathname: () => "/admin/resource-policies",
  useRouter: () => ({ replace: routerReplaceMock }),
  useSearchParams: () => mockSearchParams,
}))

jest.mock("@/components/admin/AdminPageHeader", () => ({
  AdminPageHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

jest.mock("@/components/ui/custom-breadcrumb", () => ({
  CustomBreadcrumb: () => <div>breadcrumb</div>,
}))

jest.mock("@/components/ui/skeleton", () => ({
  Skeleton: () => <div data-testid="skeleton" />,
}))

jest.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: { open: boolean; children: React.ReactNode }) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

jest.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
  DropdownMenuSeparator: () => <hr />,
}))

jest.mock("@/components/ui/select", () => {
  const React = require("react")
  const SelectContext = React.createContext({ onValueChange: (_value: string) => {}, disabled: false })

  return {
    Select: ({
      children,
      onValueChange,
      disabled,
    }: {
      children: React.ReactNode
      onValueChange?: (value: string) => void
      disabled?: boolean
    }) => (
      <SelectContext.Provider value={{ onValueChange: onValueChange || (() => {}), disabled: !!disabled }}>
        <div>{children}</div>
      </SelectContext.Provider>
    ),
    SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder || ""}</span>,
    SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    SelectItem: ({
      children,
      value,
      disabled,
    }: {
      children: React.ReactNode
      value: string
      disabled?: boolean
    }) => {
      const ctx = React.useContext(SelectContext)
      return (
        <button
          type="button"
          disabled={disabled || ctx.disabled}
          onClick={() => ctx.onValueChange(value)}
        >
          {children}
        </button>
      )
    },
  }
})

describe("resource policy sets page", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockSearchParams = new URLSearchParams()
    listPolicySetsMock.mockResolvedValue([])
    getPolicySetMock.mockResolvedValue({ id: "set-1" })
    createPolicySetMock.mockResolvedValue({ id: "set-1", name: "Base Policy" })
    updateRuleMock.mockResolvedValue({ id: "rule-1" })
    listAssignmentsMock.mockResolvedValue([])
    upsertAssignmentMock.mockResolvedValue({ id: "assignment-1" })
    setPublishedAppDefaultPolicyMock.mockResolvedValue(undefined)
    setEmbeddedAgentDefaultPolicyMock.mockResolvedValue(undefined)
    listAgentsMock.mockResolvedValue({
      agents: [{ id: "agent-1", name: "Embed Agent", default_embed_policy_set_id: null }],
      total: 1,
    })
    listModelsMock.mockResolvedValue({ models: [{ id: "model-1", name: "GPT" }] })
    listToolsMock.mockResolvedValue({ tools: [{ id: "tool-1", name: "Search Tool" }] })
    listKnowledgeStoresMock.mockResolvedValue([{ id: "store-1", name: "Private Store" }])
    listPublishedAppsMock.mockResolvedValue([{ id: "app-1", name: "Support App", default_policy_set_id: null }])
    getUsersMock.mockResolvedValue({ items: [{ id: "user-1", email: "owner@example.com", display_name: "Owner" }] })
  })

  it("shows loading state first and then the empty state", async () => {
    const policySetsDeferred = deferred<Array<Record<string, unknown>>>()
    listPolicySetsMock.mockReturnValueOnce(policySetsDeferred.promise)

    render(<ResourcePoliciesPage />)

    expect(screen.getAllByTestId("skeleton").length).toBeGreaterThan(0)
    policySetsDeferred.resolve([])

    expect(await screen.findByText("No policy sets yet")).toBeInTheDocument()
  })

  it("creates a policy set and surfaces backend validation errors", async () => {
    createPolicySetMock
      .mockRejectedValueOnce(new Error("Policy set name already exists"))
      .mockResolvedValueOnce({ id: "set-1", name: "Base Policy" })
    listPolicySetsMock
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ id: "set-1", name: "Base Policy", description: null, is_active: true, included_policy_set_ids: [], rules: [] }])

    render(<ResourcePoliciesPage />)

    expect(await screen.findByText("No policy sets yet")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /new policy set/i }))
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Base Policy" } })
    fireEvent.click(screen.getByRole("button", { name: "Create" }))

    expect(await screen.findByText("Policy set name already exists")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Create" }))

    await waitFor(() => {
      expect(createPolicySetMock).toHaveBeenCalledWith({
        name: "Base Policy",
        description: undefined,
        is_active: true,
      })
    })
    await waitFor(() => expect(listPolicySetsMock).toHaveBeenCalledTimes(2))
    expect(await screen.findByText("Base Policy")).toBeInTheDocument()
  })

  it("creates a organization user assignment from the assignments section", async () => {
    listPolicySetsMock.mockResolvedValue([
      { id: "set-1", name: "Base Policy", description: null, is_active: true, included_policy_set_ids: [], rules: [] },
    ])

    render(<ResourcePoliciesPage />)

    await screen.findByText("Base Policy")
    fireEvent.click(screen.getByRole("button", { name: /assignments/i }))
    fireEvent.click(screen.getByRole("button", { name: /new assignment/i }))
    fireEvent.click(screen.getByRole("button", { name: "Base Policy" }))
    fireEvent.click(screen.getByRole("button", { name: /Owner/i }))
    fireEvent.click(screen.getAllByRole("button", { name: "Create Assignment" }).at(-1)!)

    await waitFor(() => {
      expect(upsertAssignmentMock).toHaveBeenCalledWith({
        principal_type: "organization_user",
        policy_set_id: "set-1",
        user_id: "user-1",
      })
    })
  })

  it("restores the selected section from the query string", async () => {
    mockSearchParams = new URLSearchParams("section=assignments")
    listPolicySetsMock.mockResolvedValue([
      { id: "set-1", name: "Base Policy", description: null, is_active: true, included_policy_set_ids: [], rules: [] },
    ])

    render(<ResourcePoliciesPage />)

    expect(await screen.findByRole("button", { name: /new assignment/i })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /new policy set/i })).not.toBeInTheDocument()
  })

  it("sets published app and embedded agent defaults from the defaults section", async () => {
    listPolicySetsMock.mockResolvedValue([
      { id: "set-1", name: "Base Policy", description: null, is_active: true, included_policy_set_ids: [], rules: [] },
    ])

    render(<ResourcePoliciesPage />)

    await screen.findByText("Base Policy")
    fireEvent.click(screen.getByRole("button", { name: /defaults/i }))

    const defaultButtons = screen.getAllByRole("button", { name: "Base Policy" })
    fireEvent.click(defaultButtons[0])
    fireEvent.click(defaultButtons[1])

    await waitFor(() => {
      expect(setPublishedAppDefaultPolicyMock).toHaveBeenCalledWith("app-1", "set-1")
      expect(setEmbeddedAgentDefaultPolicyMock).toHaveBeenCalledWith("agent-1", "set-1")
    })
  })

  it("edits a quota rule from the detail modal", async () => {
    listPolicySetsMock.mockResolvedValue([
      {
        id: "set-1",
        name: "Base Policy",
        description: null,
        is_active: true,
        included_policy_set_ids: [],
        rules: [
          {
            id: "rule-1",
            resource_type: "model",
            resource_id: "model-1",
            rule_type: "quota",
            quota_unit: "tokens",
            quota_window: "monthly",
            quota_limit: 123,
          },
        ],
      },
    ])
    getPolicySetMock.mockResolvedValue({
      id: "set-1",
      name: "Base Policy",
      description: null,
      is_active: true,
      included_policy_set_ids: [],
      rules: [
        {
          id: "rule-1",
          resource_type: "model",
          resource_id: "model-1",
          rule_type: "quota",
          quota_unit: "tokens",
          quota_window: "monthly",
          quota_limit: 456,
        },
      ],
    })

    render(<ResourcePoliciesPage />)

    await screen.findByText("Base Policy")
    fireEvent.click(screen.getByText("Base Policy"))
    fireEvent.click(screen.getByRole("button", { name: /edit rule gpt/i }))
    fireEvent.change(screen.getByLabelText("Token Limit (monthly)"), { target: { value: "456" } })
    fireEvent.click(screen.getByRole("button", { name: "Save Rule" }))

    await waitFor(() => {
      expect(updateRuleMock).toHaveBeenCalledWith("rule-1", {
        resource_id: "model-1",
        quota_unit: "tokens",
        quota_window: "monthly",
        quota_limit: 456,
      })
    })
    await waitFor(() => expect(getPolicySetMock).toHaveBeenCalledWith("set-1"))
  })
})
