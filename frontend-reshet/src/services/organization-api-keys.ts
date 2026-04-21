import { httpClient } from "./http"

export type OrganizationAPIKeyStatus = "active" | "revoked"

export interface OrganizationAPIKey {
  id: string
  organization_id: string
  name: string
  key_prefix: string
  scopes: string[]
  status: OrganizationAPIKeyStatus
  created_by: string | null
  created_at: string
  revoked_at: string | null
  last_used_at: string | null
}

export interface OrganizationAPIKeyListResponse {
  items: OrganizationAPIKey[]
}

export interface OrganizationAPIKeyCreateResponse {
  api_key: OrganizationAPIKey
  token: string
  token_type: string
}

export interface OrganizationAPIKeyRevokeResponse {
  api_key: OrganizationAPIKey
}

class OrganizationAPIKeysService {
  async listAPIKeys(): Promise<OrganizationAPIKeyListResponse> {
    return httpClient.get("/admin/organizations/api-keys")
  }

  async createAPIKey(input: {
    name: string
    scopes?: string[]
  }): Promise<OrganizationAPIKeyCreateResponse> {
    return httpClient.post("/admin/organizations/api-keys", {
      name: input.name,
      scopes: input.scopes ?? ["agents.embed"],
    })
  }

  async revokeAPIKey(keyId: string): Promise<OrganizationAPIKeyRevokeResponse> {
    return httpClient.post(`/admin/organizations/api-keys/${keyId}/revoke`)
  }

  async deleteAPIKey(keyId: string): Promise<void> {
    return httpClient.delete(`/admin/organizations/api-keys/${keyId}`)
  }
}

export const organizationAPIKeysService = new OrganizationAPIKeysService()
