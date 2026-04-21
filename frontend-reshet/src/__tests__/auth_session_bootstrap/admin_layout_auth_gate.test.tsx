import { render, waitFor } from "@testing-library/react"

import AdminLayout from "@/app/admin/layout"
import { useAuthStore } from "@/lib/store/useAuthStore"

const replaceMock = jest.fn()
const pathnameMock = jest.fn(() => "/admin/dashboard")

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => pathnameMock(),
}))

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}))

jest.mock("@/components/ui/sidebar", () => ({
  SidebarProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SidebarInset: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

jest.mock("@/components/navigation/app-sidebar", () => ({
  AppSidebar: () => <div data-testid="app-sidebar" />,
}))

describe("AdminLayout auth gate", () => {
  beforeEach(() => {
    replaceMock.mockReset()
    pathnameMock.mockReturnValue("/admin/dashboard")
    localStorage.clear()
    useAuthStore.setState({
      authenticated: true,
      onboardingRequired: false,
      user: { id: "user-1", role: "user" } as any,
      activeOrganization: { id: "org-1", name: "Org 1", status: "active" } as any,
      activeProject: { id: "project-1", name: "Project 1", organization_id: "org-1", status: "active", is_default: true } as any,
      organizations: [],
      projects: [],
      effectiveScopes: [],
      hydrated: true,
      sessionChecked: true,
    })
  })

  it("does not bounce authenticated users with empty scopes back to landing", async () => {
    render(
      <AdminLayout>
        <div>dashboard content</div>
      </AdminLayout>
    )

    await waitFor(() => {
      expect(replaceMock).not.toHaveBeenCalled()
    })
  })
})
