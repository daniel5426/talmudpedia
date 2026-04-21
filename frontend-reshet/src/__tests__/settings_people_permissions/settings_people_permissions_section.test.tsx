import { render, screen } from "@testing-library/react"

import { PeoplePermissionsSection } from "@/app/admin/settings/components/PeoplePermissionsSection"
import { DirectionProvider } from "@/components/direction-provider"
import { settingsPeoplePermissionsService, settingsProjectsService } from "@/services"

jest.mock("@/services", () => ({
  settingsPeoplePermissionsService: {
    listMembers: jest.fn(),
    listInvitations: jest.fn(),
    listGroups: jest.fn(),
    listRoles: jest.fn(),
    listRoleAssignments: jest.fn(),
    removeMember: jest.fn(),
    revokeInvitation: jest.fn(),
    deleteGroup: jest.fn(),
    deleteRole: jest.fn(),
    deleteRoleAssignment: jest.fn(),
    createInvitation: jest.fn(),
    createGroup: jest.fn(),
    createRole: jest.fn(),
    updateRole: jest.fn(),
    createRoleAssignment: jest.fn(),
  },
  settingsProjectsService: {
    listProjects: jest.fn(),
  },
}))

jest.mock("@/contexts/OrganizationContext", () => ({
  useOrganization: () => ({ currentOrganization: { id: "organization-1" } }),
}))

describe("PeoplePermissionsSection", () => {
  beforeEach(() => {
    ;(settingsPeoplePermissionsService.listMembers as jest.Mock).mockResolvedValue([
      {
        membership_id: "membership-1",
        user_id: "user-1",
        email: "reader@example.com",
        full_name: "Reader Example",
        avatar: null,
        organization_role: "Reader",
        org_unit_id: "org-unit-1",
        org_unit_name: "Root",
        joined_at: new Date().toISOString(),
      },
    ])
    ;(settingsPeoplePermissionsService.listInvitations as jest.Mock).mockResolvedValue([])
    ;(settingsPeoplePermissionsService.listGroups as jest.Mock).mockResolvedValue([])
    ;(settingsPeoplePermissionsService.listRoles as jest.Mock).mockResolvedValue([
      {
        id: "org-owner",
        family: "organization",
        name: "Owner",
        description: "Owner role",
        permissions: ["organizations.write"],
        is_system: true,
        is_preset: true,
        created_at: new Date().toISOString(),
      },
      {
        id: "org-reader",
        family: "organization",
        name: "Reader",
        description: "Reader role",
        permissions: ["organizations.read"],
        is_system: true,
        is_preset: true,
        created_at: new Date().toISOString(),
      },
      {
        id: "project-member",
        family: "project",
        name: "Member",
        description: "Project member role",
        permissions: ["apps.read", "apps.write"],
        is_system: true,
        is_preset: true,
        created_at: new Date().toISOString(),
      },
    ])
    ;(settingsPeoplePermissionsService.listRoleAssignments as jest.Mock).mockResolvedValue([])
    ;(settingsProjectsService.listProjects as jest.Mock).mockResolvedValue([])
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it("renders the assignment-derived organization role from the members payload", async () => {
    render(
      <DirectionProvider>
        <PeoplePermissionsSection />
      </DirectionProvider>
    )

    expect(await screen.findByText("Reader Example")).toBeInTheDocument()
    expect(await screen.findByText("reader@example.com")).toBeInTheDocument()
    expect(await screen.findByText("Reader")).toBeInTheDocument()
  })
})
