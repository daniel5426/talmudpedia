import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import SettingsPage from "@/app/admin/settings/page"
import { credentialsService, orgUnitsService, modelsService } from "@/services"

let mockUser: any = { role: "admin", org_role: "owner" }
let mockSearch = ""
const replaceMock = jest.fn((href: string) => {
  mockSearch = href.split("?")[1] ?? ""
})

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => "/admin/settings",
  useSearchParams: () => new URLSearchParams(mockSearch),
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
  useAuthStore: (selector: (state: any) => any) => selector({ user: mockUser }),
}))

describe("Tenant Profile Tab", () => {
  beforeEach(() => {
    mockUser = { role: "admin", org_role: "owner" }
    mockSearch = ""
    replaceMock.mockReset()
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
    ;(modelsService.listModels as jest.Mock).mockResolvedValue({ models: [], total: 0 })
    ;(orgUnitsService.updateTenant as jest.Mock).mockResolvedValue({
      id: "tenant-1",
      name: "Tenant Updated",
      slug: "tenant-1",
      status: "active",
      created_at: "",
    })
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it("saves tenant profile changes", async () => {
    render(<SettingsPage />)

    await waitFor(() => expect(orgUnitsService.getTenant).toHaveBeenCalled())
    await waitFor(() => expect(screen.getAllByRole("button", { name: "General" }).length).toBeGreaterThan(0))
    await waitFor(() => expect(screen.getByText("Save")).toBeInTheDocument())

    const nameInput = screen.getAllByRole("textbox")[0]
    fireEvent.change(nameInput, { target: { value: "Tenant Updated" } })

    const saveButton = screen.getByText("Save")
    fireEvent.click(saveButton)

    await waitFor(() => expect(orgUnitsService.updateTenant).toHaveBeenCalledWith("tenant-1", {
      name: "Tenant Updated",
      slug: "tenant-1",
      status: "active",
    }))
  })

  it("renders read-only mode when user is not tenant admin", async () => {
    mockUser = { role: "user", org_role: "member" }

    render(<SettingsPage />)

    await waitFor(() => expect(orgUnitsService.getTenant).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText("Read-only access. Contact an admin to make changes.")).toBeInTheDocument())

    expect(screen.getByText("Save")).toBeDisabled()
  })
})
