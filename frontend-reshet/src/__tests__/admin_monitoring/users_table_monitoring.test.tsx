import { render, screen, waitFor } from "@testing-library/react"

import { UsersTable } from "@/components/admin/users-table"

jest.mock("@/contexts/OrganizationContext", () => ({
  useOrganization: () => ({ currentOrganization: null }),
}))

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}))

jest.mock("@/services", () => ({
  adminService: {
    updateUser: jest.fn(),
    bulkDeleteUsers: jest.fn(),
  },
}))

describe("users table monitored actor rendering", () => {
  it("marks external actors as read only and keeps platform rows manageable", async () => {
    render(
      <UsersTable
        data={[
          {
            id: "platform-user-1",
            actor_id: "platform-user-1",
            actor_type: "platform_user",
            display_name: "Platform User",
            email: "platform@example.com",
            role: "user",
            is_manageable: true,
            threads_count: 2,
            source_app_count: 1,
          },
          {
            id: "app_account:account-1",
            actor_id: "app_account:account-1",
            actor_type: "published_app_account",
            display_name: "Standalone User",
            email: "standalone@example.com",
            is_manageable: false,
            threads_count: 1,
            source_app_count: 1,
          },
        ]}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText("Platform User")).toBeInTheDocument()
      expect(screen.getByText("Standalone User")).toBeInTheDocument()
    })

    expect(screen.getByText("Read only")).toBeInTheDocument()
    expect(screen.getByText("Platform")).toBeInTheDocument()
    expect(screen.getByText("App Account")).toBeInTheDocument()
  })
})
