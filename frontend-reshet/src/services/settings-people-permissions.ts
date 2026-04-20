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
  organization_role: string
  project_role: string | null
  accepted_at: string | null
  created_at: string | null
  expires_at: string | null
}

export interface SettingsGroup {
  id: string
  tenant_id: string
  parent_id: string | null
  name: string
  slug: string
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
  scope_id: string
  scope_type: string
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

  async createInvitation(input: { email: string; project_ids?: string[] }): Promise<SettingsInvitation> {
    return httpClient.post("/api/settings/people/invitations", {
      email: input.email,
      project_ids: input.project_ids ?? [],
    })
  }

  async revokeInvitation(inviteId: string): Promise<void> {
    return httpClient.delete(`/api/settings/people/invitations/${inviteId}`)
  }

  async listGroups(): Promise<SettingsGroup[]> {
    return httpClient.get("/api/settings/people/groups")
  }

  async createGroup(input: { name: string; slug: string; type: "org" | "dept" | "team"; parent_id?: string | null }): Promise<SettingsGroup> {
    return httpClient.post("/api/settings/people/groups", input)
  }

  async updateGroup(groupId: string, input: { name?: string; slug?: string; parent_id?: string | null }): Promise<SettingsGroup> {
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

  async listRoleAssignments(filters?: { scope_type?: string; scope_id?: string }): Promise<SettingsRoleAssignment[]> {
    const params = new URLSearchParams()
    if (filters?.scope_type) params.set("scope_type", filters.scope_type)
    if (filters?.scope_id) params.set("scope_id", filters.scope_id)
    const query = params.toString() ? `?${params.toString()}` : ""
    return httpClient.get(`/api/settings/people/role-assignments${query}`)
  }

  async createRoleAssignment(input: { user_id: string; role_id: string; scope_id: string; scope_type: string }): Promise<SettingsRoleAssignment> {
    return httpClient.post("/api/settings/people/role-assignments", input)
  }

  async deleteRoleAssignment(assignmentId: string): Promise<void> {
    return httpClient.delete(`/api/settings/people/role-assignments/${assignmentId}`)
  }
}

export const settingsPeoplePermissionsService = new SettingsPeoplePermissionsService()
