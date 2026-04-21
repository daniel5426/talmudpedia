import { httpClient } from "./http"

export interface SettingsMember {
  membership_id: string
  user_id: string
  email: string
  full_name: string | null
  avatar: string | null
  organization_role: string
  org_unit_id: string
  org_unit_name: string
  joined_at: string
}

export interface SettingsInvitation {
  id: string
  email: string | null
  project_ids: string[]
  project_role_id: string | null
  organization_role: string
  project_role: string | null
  accepted_at: string | null
  created_at: string | null
  expires_at: string | null
}

export interface SettingsGroup {
  id: string
  organization_id: string
  parent_id: string | null
  name: string
  type: string
  created_at: string
}

export interface SettingsRole {
  id: string
  family: "organization" | "project"
  name: string
  description: string | null
  permissions: string[]
  is_system: boolean
  is_preset: boolean
  created_at: string
}

export interface SettingsRoleAssignment {
  id: string
  user_id: string
  user_email: string | null
  role_id: string
  role_family: "organization" | "project"
  role_name: string
  assignment_kind: "organization" | "project"
  project_id: string | null
  assigned_at: string
}

class SettingsPeoplePermissionsService {
  async listMembers(): Promise<SettingsMember[]> {
    return httpClient.get("/api/settings/people/members")
  }

  async removeMember(membershipId: string): Promise<void> {
    return httpClient.delete(`/api/settings/people/members/${membershipId}`)
  }

  async listInvitations(): Promise<SettingsInvitation[]> {
    return httpClient.get("/api/settings/people/invitations")
  }

  async createInvitation(input: { email: string; project_ids?: string[]; project_role_id?: string | null }): Promise<SettingsInvitation> {
    return httpClient.post("/api/settings/people/invitations", {
      email: input.email,
      project_ids: input.project_ids ?? [],
      project_role_id: input.project_role_id ?? null,
    })
  }

  async revokeInvitation(inviteId: string): Promise<void> {
    return httpClient.delete(`/api/settings/people/invitations/${inviteId}`)
  }

  async listGroups(): Promise<SettingsGroup[]> {
    return httpClient.get("/api/settings/people/groups")
  }

  async createGroup(input: { name: string; type: "org" | "dept" | "team"; parent_id?: string | null }): Promise<SettingsGroup> {
    return httpClient.post("/api/settings/people/groups", input)
  }

  async updateGroup(groupId: string, input: { name?: string; parent_id?: string | null }): Promise<SettingsGroup> {
    return httpClient.patch(`/api/settings/people/groups/${groupId}`, input)
  }

  async deleteGroup(groupId: string): Promise<void> {
    return httpClient.delete(`/api/settings/people/groups/${groupId}`)
  }

  async listRoles(): Promise<SettingsRole[]> {
    return httpClient.get("/api/settings/people/roles")
  }

  async createRole(input: {
    family: SettingsRole["family"]
    name: string
    description?: string | null
    permissions: string[]
  }): Promise<SettingsRole> {
    return httpClient.post("/api/settings/people/roles", input)
  }

  async updateRole(
    roleId: string,
    input: {
      family?: SettingsRole["family"]
      name?: string
      description?: string | null
      permissions?: string[]
    }
  ): Promise<SettingsRole> {
    return httpClient.patch(`/api/settings/people/roles/${roleId}`, input)
  }

  async deleteRole(roleId: string): Promise<void> {
    return httpClient.delete(`/api/settings/people/roles/${roleId}`)
  }

  async listRoleAssignments(filters?: { assignment_kind?: "organization" | "project"; project_id?: string }): Promise<SettingsRoleAssignment[]> {
    const params = new URLSearchParams()
    if (filters?.assignment_kind) params.set("assignment_kind", filters.assignment_kind)
    if (filters?.project_id) params.set("project_id", filters.project_id)
    const query = params.toString() ? `?${params.toString()}` : ""
    return httpClient.get(`/api/settings/people/role-assignments${query}`)
  }

  async createRoleAssignment(input: {
    user_id: string
    role_id: string
    assignment_kind: "organization" | "project"
    project_id?: string | null
  }): Promise<SettingsRoleAssignment> {
    return httpClient.post("/api/settings/people/role-assignments", input)
  }

  async deleteRoleAssignment(assignmentId: string): Promise<void> {
    return httpClient.delete(`/api/settings/people/role-assignments/${assignmentId}`)
  }
}

export const settingsPeoplePermissionsService = new SettingsPeoplePermissionsService()
