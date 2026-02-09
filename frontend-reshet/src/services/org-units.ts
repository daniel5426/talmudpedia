import { httpClient } from "./http"

export interface Tenant {
  id: string
  name: string
  slug: string
  status: string
  created_at: string
}

export type TenantStatus = "active" | "suspended" | "pending"
export type RetrievalPolicy = "semantic_only" | "hybrid" | "keyword_only" | "recency_boosted"

export interface TenantSettings {
  default_chat_model_id: string | null
  default_embedding_model_id: string | null
  default_retrieval_policy: RetrievalPolicy | null
}

export interface OrgUnit {
  id: string
  tenant_id: string
  parent_id: string | null
  name: string
  slug: string
  type: "org" | "dept" | "team"
  created_at: string
}

export interface OrgUnitTree {
  id: string
  name: string
  slug: string
  type: string
  children: OrgUnitTree[]
}

export interface OrgMember {
  membership_id: string
  user_id: string
  org_unit_id: string
  email: string
  full_name: string
  joined_at: string
}

class OrgUnitsService {
  async createTenant(data: { name: string; slug: string }): Promise<Tenant> {
    return httpClient.post("/api/tenants", data)
  }

  async listTenants(): Promise<Tenant[]> {
    return httpClient.get("/api/tenants")
  }

  async getTenant(tenantSlug: string): Promise<Tenant> {
    return httpClient.get(`/api/tenants/${tenantSlug}`)
  }

  async updateTenant(
    tenantSlug: string,
    data: { name?: string; slug?: string; status?: TenantStatus }
  ): Promise<Tenant> {
    return httpClient.patch(`/api/tenants/${tenantSlug}`, data)
  }

  async getTenantSettings(tenantSlug: string): Promise<TenantSettings> {
    return httpClient.get(`/api/tenants/${tenantSlug}/settings`)
  }

  async updateTenantSettings(
    tenantSlug: string,
    data: {
      default_chat_model_id?: string | null
      default_embedding_model_id?: string | null
      default_retrieval_policy?: RetrievalPolicy | null
    }
  ): Promise<TenantSettings> {
    return httpClient.patch(`/api/tenants/${tenantSlug}/settings`, data)
  }

  async listOrgUnits(tenantSlug: string): Promise<OrgUnit[]> {
    return httpClient.get(`/api/tenants/${tenantSlug}/org-units`)
  }

  async getOrgUnitTree(tenantSlug: string): Promise<OrgUnitTree[]> {
    return httpClient.get(`/api/tenants/${tenantSlug}/org-units/tree`)
  }

  async createOrgUnit(
    tenantSlug: string,
    data: {
      name: string
      slug: string
      type: "org" | "dept" | "team"
      parent_id?: string
    }
  ): Promise<OrgUnit> {
    return httpClient.post(`/api/tenants/${tenantSlug}/org-units`, data)
  }

  async getOrgUnit(tenantSlug: string, orgUnitId: string): Promise<OrgUnit> {
    return httpClient.get(`/api/tenants/${tenantSlug}/org-units/${orgUnitId}`)
  }

  async updateOrgUnit(
    tenantSlug: string,
    orgUnitId: string,
    data: { name?: string; slug?: string }
  ): Promise<OrgUnit> {
    return httpClient.put(`/api/tenants/${tenantSlug}/org-units/${orgUnitId}`, data)
  }

  async deleteOrgUnit(
    tenantSlug: string,
    orgUnitId: string
  ): Promise<{ status: string }> {
    return httpClient.delete(`/api/tenants/${tenantSlug}/org-units/${orgUnitId}`)
  }

  async listMembers(
    tenantSlug: string,
    orgUnitId?: string
  ): Promise<{ members: OrgMember[] }> {
    const params = orgUnitId ? `?org_unit_id=${orgUnitId}` : ""
    return httpClient.get(`/api/tenants/${tenantSlug}/members${params}`)
  }

  async addMember(
    tenantSlug: string,
    data: { user_id: string; org_unit_id: string }
  ): Promise<{ membership_id: string; status: string }> {
    return httpClient.post(`/api/tenants/${tenantSlug}/members`, data)
  }

  async removeMember(
    tenantSlug: string,
    membershipId: string
  ): Promise<{ status: string }> {
    return httpClient.delete(`/api/tenants/${tenantSlug}/members/${membershipId}`)
  }
}

export const orgUnitsService = new OrgUnitsService()
