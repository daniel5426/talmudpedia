import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import SettingsPage from "@/app/admin/settings/page"
import { credentialsService, orgUnitsService, modelsService } from "@/services"

jest.mock("@/components/ui/tabs", () => {
  const React = require("react")
  const TabsContext = React.createContext({ value: "", setValue: (_v: string) => {} })
  return {
    Tabs: ({ value, onValueChange, children }: any) => (
      <TabsContext.Provider value={{ value, setValue: onValueChange }}>
        <div>{children}</div>
      </TabsContext.Provider>
    ),
    TabsList: ({ children }: any) => <div>{children}</div>,
    TabsTrigger: ({ value, children }: any) => {
      const ctx = React.useContext(TabsContext)
      return (
        <button role="tab" onClick={() => ctx.setValue(value)}>
          {children}
        </button>
      )
    },
    TabsContent: ({ value, children }: any) => {
      const ctx = React.useContext(TabsContext)
      if (ctx.value !== value) return null
      return <div>{children}</div>
    },
  }
})

jest.mock("@/components/ui/select", () => ({
  Select: ({ children, onValueChange }: any) => (
    <div>
      <button type="button" data-testid="mock-select" onClick={() => onValueChange?.("chat-model-1")}>
        mock-select
      </button>
      {children}
    </div>
  ),
  SelectContent: ({ children }: any) => <div>{children}</div>,
  SelectItem: ({ children }: any) => <div>{children}</div>,
  SelectTrigger: ({ children }: any) => <div>{children}</div>,
  SelectValue: ({ placeholder }: any) => <span>{placeholder}</span>,
}))

jest.mock("@/services", () => ({
  credentialsService: {
    listCredentials: jest.fn(),
    deleteCredential: jest.fn(),
    createCredential: jest.fn(),
    updateCredential: jest.fn(),
  },
  orgUnitsService: {
    getTenant: jest.fn(),
    getTenantSettings: jest.fn(),
    updateTenant: jest.fn(),
    updateTenantSettings: jest.fn(),
  },
  modelsService: {
    listModels: jest.fn(),
  },
}))

jest.mock("@/contexts/TenantContext", () => ({
  useTenant: () => ({
    currentTenant: { id: "tenant-1", slug: "tenant-1", name: "Tenant One", status: "active", created_at: "" },
    setCurrentTenant: jest.fn(),
    refreshTenants: jest.fn(),
  }),
}))

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}))

jest.mock("@/lib/store/useAuthStore", () => ({
  useAuthStore: (selector: (state: any) => any) => selector({ user: { role: "admin", org_role: "owner" } }),
}))

describe("Defaults Tab", () => {
  beforeEach(() => {
    ;(orgUnitsService.getTenant as jest.Mock).mockResolvedValue({
      id: "tenant-1",
      name: "Tenant One",
      slug: "tenant-1",
      status: "active",
      created_at: "",
    })
    ;(orgUnitsService.getTenantSettings as jest.Mock).mockResolvedValue({
      default_chat_model_id: null,
      default_embedding_model_id: null,
      default_retrieval_policy: null,
    })
    ;(credentialsService.listCredentials as jest.Mock).mockResolvedValue([])
    ;(modelsService.listModels as jest.Mock).mockImplementation((capability: string) => {
      if (capability === "chat") {
        return Promise.resolve({
          models: [{ id: "chat-model-1", name: "Chat A" }],
          total: 1,
        })
      }
      return Promise.resolve({
        models: [{ id: "embed-model-1", name: "Embed A" }],
        total: 1,
      })
    })
    ;(orgUnitsService.updateTenantSettings as jest.Mock).mockResolvedValue({
      default_chat_model_id: "chat-model-1",
      default_embedding_model_id: null,
      default_retrieval_policy: null,
    })
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it("saves defaults payload", async () => {
    render(<SettingsPage />)

    await waitFor(() => expect(orgUnitsService.getTenant).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByRole("tab", { name: "Defaults" })).toBeInTheDocument())

    const defaultsTab = screen.getByRole("tab", { name: "Defaults" })
    fireEvent.click(defaultsTab)
    await waitFor(() => expect(screen.getByText("Save Defaults")).toBeInTheDocument())

    fireEvent.click(screen.getAllByTestId("mock-select")[0])

    fireEvent.click(screen.getByText("Save Defaults"))

    await waitFor(() => {
      expect(orgUnitsService.updateTenantSettings).toHaveBeenCalledWith("tenant-1", {
        default_chat_model_id: "chat-model-1",
        default_embedding_model_id: null,
        default_retrieval_policy: null,
      })
    })
  })
})
