import { httpClient } from "./http"

export interface Permission {
  resource_type: string
  action: string
}

export interface Role {
  id: string
  tenant_id: string
  name: string
  description: string | null
  permissions: Permission[]
  is_system: boolean
  created_at: string
}

export interface RoleAssignment {
  id: string
  tenant_id: string
  user_id: string
  role_id: string
  role_name: string
  scope_id: string
  scope_type: string
  actor_type: string
  assigned_by: string
  assigned_at: string
}

export interface UserPermissions {
  permissions: Permission[]
  scopes: {
    scope_id: string
    scope_type: string
    role_name: string
    permissions: Permission[]
  }[]
}

class RBACService {
  async listRoles(tenantSlug: string): Promise<Role[]> {
    return httpClient.get(`/api/tenants/${tenantSlug}/roles`)
  }

  async createRole(
    tenantSlug: string,
    data: {
      name: string
      description?: string
      permissions: Permission[]
    }
  ): Promise<Role> {
    return httpClient.post(`/api/tenants/${tenantSlug}/roles`, data)
  }

  async getRole(tenantSlug: string, roleId: string): Promise<Role> {
    return httpClient.get(`/api/tenants/${tenantSlug}/roles/${roleId}`)
  }

  async updateRole(
    tenantSlug: string,
    roleId: string,
    data: {
      name?: string
      description?: string
      permissions?: Permission[]
    }
  ): Promise<Role> {
    return httpClient.put(`/api/tenants/${tenantSlug}/roles/${roleId}`, data)
  }

  async deleteRole(
    tenantSlug: string,
    roleId: string
  ): Promise<{ status: string }> {
    return httpClient.delete(`/api/tenants/${tenantSlug}/roles/${roleId}`)
  }

  async listRoleAssignments(
    tenantSlug: string,
    filters?: { user_id?: string; scope_id?: string }
  ): Promise<RoleAssignment[]> {
    const params = new URLSearchParams()
    if (filters?.user_id) params.set("user_id", filters.user_id)
    if (filters?.scope_id) params.set("scope_id", filters.scope_id)
    const query = params.toString() ? `?${params.toString()}` : ""
    return httpClient.get(`/api/tenants/${tenantSlug}/role-assignments${query}`)
  }

  async createRoleAssignment(
    tenantSlug: string,
    data: {
      user_id: string
      role_id: string
      scope_id: string
      scope_type: string
      actor_type?: "user" | "service" | "agent"
    }
  ): Promise<RoleAssignment> {
    return httpClient.post(`/api/tenants/${tenantSlug}/role-assignments`, data)
  }

  async deleteRoleAssignment(
    tenantSlug: string,
    assignmentId: string
  ): Promise<{ status: string }> {
    return httpClient.delete(
      `/api/tenants/${tenantSlug}/role-assignments/${assignmentId}`
    )
  }

  async getUserPermissions(
    tenantSlug: string,
    userId: string
  ): Promise<UserPermissions> {
    return httpClient.get(`/api/tenants/${tenantSlug}/users/${userId}/permissions`)
  }
}

export const rbacService = new RBACService()
