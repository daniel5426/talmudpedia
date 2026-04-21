import { httpClient } from "./http"

export interface Organization {
  id: string
  name: string
  status: string
  created_at: string
}

export type OrganizationStatus = "active" | "suspended" | "pending"
export type RetrievalPolicy = "semantic_only" | "hybrid" | "keyword_only" | "recency_boosted"

export interface OrganizationSettings {
  default_chat_model_id: string | null
  default_embedding_model_id: string | null
  default_retrieval_policy: RetrievalPolicy | null
}

export interface OrgUnit {
  id: string
  organization_id: string
  parent_id: string | null
  name: string
  type: "org" | "dept" | "team"
  created_at: string
}

export interface OrgUnitTree {
  id: string
  name: string
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

class OrganizationUnitsService {
  async createOrganization(data: { name: string }): Promise<Organization> {
    return httpClient.post("/api/organizations", data)
  }

  async listOrganizations(): Promise<Organization[]> {
    return httpClient.get("/api/organizations")
  }

  async getOrganization(organizationId: string): Promise<Organization> {
    return httpClient.get(`/api/organizations/${organizationId}`)
  }

  async updateOrganization(
    organizationId: string,
    data: { name?: string; status?: OrganizationStatus }
  ): Promise<Organization> {
    return httpClient.patch(`/api/organizations/${organizationId}`, data)
  }

  async getOrganizationSettings(organizationId: string): Promise<OrganizationSettings> {
    return httpClient.get(`/api/organizations/${organizationId}/settings`)
  }

  async updateOrganizationSettings(
    organizationId: string,
    data: {
      default_chat_model_id?: string | null
      default_embedding_model_id?: string | null
      default_retrieval_policy?: RetrievalPolicy | null
    }
  ): Promise<OrganizationSettings> {
    return httpClient.patch(`/api/organizations/${organizationId}/settings`, data)
  }

  async listOrgUnits(organizationId: string): Promise<OrgUnit[]> {
    return httpClient.get(`/api/organizations/${organizationId}/org-units`)
  }

  async getOrgUnitTree(organizationId: string): Promise<OrgUnitTree[]> {
    return httpClient.get(`/api/organizations/${organizationId}/org-units/tree`)
  }

  async createOrgUnit(
    organizationId: string,
    data: {
      name: string
      type: "org" | "dept" | "team"
      parent_id?: string
    }
  ): Promise<OrgUnit> {
    return httpClient.post(`/api/organizations/${organizationId}/org-units`, data)
  }

  async getOrgUnit(organizationId: string, orgUnitId: string): Promise<OrgUnit> {
    return httpClient.get(`/api/organizations/${organizationId}/org-units/${orgUnitId}`)
  }

  async updateOrgUnit(
    organizationId: string,
    orgUnitId: string,
    data: { name?: string }
  ): Promise<OrgUnit> {
    return httpClient.put(`/api/organizations/${organizationId}/org-units/${orgUnitId}`, data)
  }

  async deleteOrgUnit(
    organizationId: string,
    orgUnitId: string
  ): Promise<{ status: string }> {
    return httpClient.delete(`/api/organizations/${organizationId}/org-units/${orgUnitId}`)
  }

  async listMembers(
    organizationId: string,
    orgUnitId?: string
  ): Promise<{ members: OrgMember[] }> {
    const params = orgUnitId ? `?org_unit_id=${orgUnitId}` : ""
    return httpClient.get(`/api/organizations/${organizationId}/members${params}`)
  }

  async addMember(
    organizationId: string,
    data: { user_id: string; org_unit_id: string }
  ): Promise<{ membership_id: string; status: string }> {
    return httpClient.post(`/api/organizations/${organizationId}/members`, data)
  }

  async removeMember(
    organizationId: string,
    membershipId: string
  ): Promise<{ status: string }> {
    return httpClient.delete(`/api/organizations/${organizationId}/members/${membershipId}`)
  }
}

export const organizationUnitsService = new OrganizationUnitsService()
