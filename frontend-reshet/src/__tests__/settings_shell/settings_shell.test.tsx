import { render, screen, waitFor } from "@testing-library/react"

import SettingsPage from "@/app/admin/settings/page"
import { credentialsService, modelsService, settingsOrgService, settingsProfileService } from "@/services"

let mockSearch = ""
const replaceMock = jest.fn((href: string) => {
  mockSearch = href.split("?")[1] ?? ""
})

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => "/admin/settings",
  useSearchParams: () => new URLSearchParams(mockSearch),
}))

jest.mock("@/app/admin/settings/components/GovernanceSections", () => ({
  PeoplePermissionsSection: () => <div>People section</div>,
  ProjectsSection: ({ onOpenAudit }: { onOpenAudit: (resourceId: string) => void }) => (
    <button onClick={() => onOpenAudit("proj-1")}>Projects section</button>
  ),
  ApiKeysSection: () => <div>API Keys section</div>,
  LimitsSection: () => <div>Limits section</div>,
  AuditLogsSection: ({ initialResourceId }: { initialResourceId?: string | null }) => <div>Audit section {initialResourceId}</div>,
}))

jest.mock("@/app/admin/settings/mcp/page", () => () => <div>MCP section</div>)

jest.mock("@/app/admin/settings/components/CredentialFormDialog", () => ({
  CredentialFormDialog: () => <div>CredentialFormDialog</div>,
}))

jest.mock("@/app/admin/settings/components/CredentialDeleteDialog", () => ({
  CredentialDeleteDialog: () => <div>CredentialDeleteDialog</div>,
}))

jest.mock("@/services", () => ({
  credentialsService: { listCredentials: jest.fn() },
  modelsService: { listModels: jest.fn() },
  settingsOrgService: { getOrganization: jest.fn(), updateOrganization: jest.fn() },
  settingsProfileService: { getProfile: jest.fn(), updateProfile: jest.fn() },
}))

jest.mock("@/lib/store/useAuthStore", () => ({
  useAuthStore: (selector: (state: any) => any) =>
    selector({
      hasScope: () => true,
    }),
}))

describe("settings shell", () => {
  beforeEach(() => {
    mockSearch = ""
    replaceMock.mockReset()
    ;(settingsOrgService.getOrganization as jest.Mock).mockResolvedValue({
      id: "org-1",
      name: "Acme",
      slug: "acme",
      status: "active",
      default_chat_model_id: null,
      default_embedding_model_id: null,
      default_retrieval_policy: null,
    })
    ;(settingsProfileService.getProfile as jest.Mock).mockResolvedValue({
      id: "user-1",
      email: "user@example.com",
      full_name: "User Example",
      avatar: null,
      role: "admin",
    })
    ;(credentialsService.listCredentials as jest.Mock).mockResolvedValue({ items: [], total: 0, has_more: false, skip: 0, limit: 100, view: "summary" })
    ;(modelsService.listModels as jest.Mock).mockResolvedValue({ items: [], total: 0, has_more: false, skip: 0, limit: 100, view: "full" })
  })

  it("renders the canonical settings tabs", async () => {
    render(<SettingsPage />)

    await waitFor(() => expect(settingsOrgService.getOrganization).toHaveBeenCalled())
    expect(screen.getByRole("tab", { name: /Organization/ })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: /People & Permissions/ })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: /Projects/ })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: /API Keys/ })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: /MCP Servers/ })).toBeInTheDocument()
  })

  it("restores the active tab from the query string", async () => {
    mockSearch = "tab=audit_logs"
    render(<SettingsPage />)

    await waitFor(() => expect(settingsOrgService.getOrganization).toHaveBeenCalled())
    expect(screen.getByText("Audit section")).toBeInTheDocument()
  })

  it("switches from projects to audit with a resource filter seed", async () => {
    mockSearch = "tab=projects"
    render(<SettingsPage />)

    await waitFor(() => expect(settingsOrgService.getOrganization).toHaveBeenCalled())
    ;(await screen.findByRole("button", { name: "Projects section" })).click()

    await waitFor(() => expect(screen.getByText("Audit section proj-1")).toBeInTheDocument())
  })
})
