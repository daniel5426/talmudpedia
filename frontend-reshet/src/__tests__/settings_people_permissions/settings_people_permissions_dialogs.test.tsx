import { fireEvent, render, screen } from "@testing-library/react"

import { MemberRoleAssignmentsDialog } from "@/app/admin/settings/components/MemberRoleAssignmentsDialog"
import { RolePermissionDialog, RoleFormState } from "@/app/admin/settings/components/RolePermissionDialog"
import { DirectionProvider } from "@/components/direction-provider"

const organizationForm: RoleFormState = {
  id: "",
  family: "organization",
  name: "Support Admin",
  description: "",
  permissions: [],
}

const renderWithDirection = (ui: React.ReactElement) => render(<DirectionProvider>{ui}</DirectionProvider>)

describe("settings people permissions dialogs", () => {
  it("renders organization-only permission resources for organization custom roles", () => {
    renderWithDirection(
      <RolePermissionDialog
        open
        form={organizationForm}
        saving={false}
        assignmentCount={0}
        onFormChange={() => undefined}
        onOpenChange={() => undefined}
        onSave={() => undefined}
      />
    )

    expect(screen.getByText("Organization Settings")).toBeInTheDocument()
    expect(screen.getByText("Members")).toBeInTheDocument()
    expect(screen.queryByText("Project API Keys")).not.toBeInTheDocument()
  })

  it("renders project-only permission resources for project custom roles", () => {
    renderWithDirection(
      <RolePermissionDialog
        open
        form={{ ...organizationForm, family: "project", name: "Workflow Builder" }}
        saving={false}
        assignmentCount={0}
        onFormChange={() => undefined}
        onOpenChange={() => undefined}
        onSave={() => undefined}
      />
    )

    expect(screen.getByText("Project Settings")).toBeInTheDocument()
    expect(screen.getByText("Project Members")).toBeInTheDocument()
    expect(screen.getByText("Project API Keys")).toBeInTheDocument()
    expect(screen.getByText("Publish")).toBeInTheDocument()
    expect(screen.getByText("Exposure")).toBeInTheDocument()
    expect(screen.getByText("Agents")).toBeInTheDocument()
    expect(screen.queryByText("Organization Settings")).not.toBeInTheDocument()
  })

  it("renders combined member access editing with org role and project access", () => {
    const onSelectedOrganizationRoleIdChange = jest.fn()
    const onProjectAccessRowsChange = jest.fn()

    renderWithDirection(
      <MemberRoleAssignmentsDialog
        open
        member={{
          membership_id: "m1",
          user_id: "u1",
          email: "member@example.com",
          full_name: "Member Example",
          avatar: null,
          organization_role: "Reader",
          org_unit_id: "ou1",
          org_unit_name: "Root",
          joined_at: new Date().toISOString(),
        }}
        organizationRoles={[
          {
            id: "r-reader",
            family: "organization",
            name: "Reader",
            description: "Baseline access",
            permissions: ["organizations.read"],
            is_system: true,
            is_preset: true,
            created_at: new Date().toISOString(),
          },
          {
            id: "r-support",
            family: "organization",
            name: "Support Admin",
            description: "Support access",
            permissions: ["organizations.read", "organization_members.read"],
            is_system: false,
            is_preset: false,
            created_at: new Date().toISOString(),
          },
        ]}
        projectRoles={[
          {
            id: "p-member",
            family: "project",
            name: "Member",
            description: "Standard project access",
            permissions: ["apps.read", "apps.write"],
            is_system: true,
            is_preset: true,
            created_at: new Date().toISOString(),
          },
        ]}
        projects={[
          {
            id: "proj-1",
            organization_id: "org-1",
            name: "Project One",
            description: null,
            status: "active",
            is_default: false,
            created_at: new Date().toISOString(),
            member_count: 1,
          },
        ]}
        selectedOrganizationRoleId="r-reader"
        projectAccessRows={[]}
        orgOwnerImplicit={false}
        saving={false}
        onSelectedOrganizationRoleIdChange={onSelectedOrganizationRoleIdChange}
        onProjectAccessRowsChange={onProjectAccessRowsChange}
        onOpenChange={() => undefined}
        onSave={() => undefined}
      />
    )

    expect(screen.getByText("Organization role")).toBeInTheDocument()
    expect(screen.getByText("Project access")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Support Admin/ }))
    expect(onSelectedOrganizationRoleIdChange).toHaveBeenCalledWith("r-support")
    fireEvent.click(screen.getByRole("button", { name: /Add Project/ }))
    expect(onProjectAccessRowsChange).toHaveBeenCalledWith([{ projectId: "", roleId: "p-member" }])
  })
})
