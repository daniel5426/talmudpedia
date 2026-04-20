import { fireEvent, render, screen } from "@testing-library/react"

import { MemberRoleAssignmentsDialog } from "@/app/admin/settings/components/MemberRoleAssignmentsDialog"
import { RolePermissionDialog, RoleFormState } from "@/app/admin/settings/components/RolePermissionDialog"

const organizationForm: RoleFormState = {
  id: "",
  family: "organization",
  name: "Support Admin",
  description: "",
  permissions: [],
}

describe("settings people permissions dialogs", () => {
  it("renders organization-only permission resources for organization custom roles", () => {
    render(
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
    render(
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

    expect(screen.getByText("Project API Keys")).toBeInTheDocument()
    expect(screen.getByText("Agents")).toBeInTheDocument()
    expect(screen.queryByText("Organization Settings")).not.toBeInTheDocument()
  })

  it("keeps member organization-role assignment single-select", () => {
    const onSelectedRoleIdChange = jest.fn()

    render(
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
        roles={[
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
        selectedRoleId="r-reader"
        saving={false}
        onSelectedRoleIdChange={onSelectedRoleIdChange}
        onOpenChange={() => undefined}
        onSave={() => undefined}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: /Support Admin/ }))
    expect(onSelectedRoleIdChange).toHaveBeenCalledWith("r-support")
    expect(screen.getByRole("button", { name: "Save role" })).toBeInTheDocument()
  })
})
