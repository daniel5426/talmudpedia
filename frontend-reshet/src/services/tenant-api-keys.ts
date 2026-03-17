import { httpClient } from "./http"

export type TenantAPIKeyStatus = "active" | "revoked"

export interface TenantAPIKey {
  id: string
  tenant_id: string
  name: string
  key_prefix: string
  scopes: string[]
  status: TenantAPIKeyStatus
  created_by: string | null
  created_at: string
  revoked_at: string | null
  last_used_at: string | null
}

export interface TenantAPIKeyListResponse {
  items: TenantAPIKey[]
}

export interface TenantAPIKeyCreateResponse {
  api_key: TenantAPIKey
  token: string
  token_type: string
}

export interface TenantAPIKeyRevokeResponse {
  api_key: TenantAPIKey
}

class TenantAPIKeysService {
  async listAPIKeys(): Promise<TenantAPIKeyListResponse> {
    return httpClient.get("/admin/security/api-keys")
  }

  async createAPIKey(input: {
    name: string
    scopes?: string[]
  }): Promise<TenantAPIKeyCreateResponse> {
    return httpClient.post("/admin/security/api-keys", {
      name: input.name,
      scopes: input.scopes ?? ["agents.embed"],
    })
  }

  async revokeAPIKey(keyId: string): Promise<TenantAPIKeyRevokeResponse> {
    return httpClient.post(`/admin/security/api-keys/${keyId}/revoke`)
  }

  async deleteAPIKey(keyId: string): Promise<void> {
    return httpClient.delete(`/admin/security/api-keys/${keyId}`)
  }
}

export const tenantAPIKeysService = new TenantAPIKeysService()
