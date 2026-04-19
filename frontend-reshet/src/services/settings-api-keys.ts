import { httpClient } from "./http"

export interface SettingsApiKey {
  id: string
  owner_scope: string
  owner_scope_id: string
  name: string
  key_prefix: string
  scopes: string[]
  status: string
  created_by: string | null
  created_at: string
  revoked_at: string | null
  last_used_at: string | null
}

export interface SettingsApiKeyCreateResponse {
  api_key: SettingsApiKey
  token: string
  token_type: string
}

class SettingsApiKeysService {
  async listApiKeys(input: { owner_scope: "organization" | "project"; project_slug?: string }): Promise<SettingsApiKey[]> {
    const params = new URLSearchParams({ owner_scope: input.owner_scope })
    if (input.project_slug) params.set("project_slug", input.project_slug)
    return httpClient.get(`/api/settings/api-keys?${params.toString()}`)
  }

  async createApiKey(input: {
    owner_scope: "organization" | "project"
    project_slug?: string
    name: string
    scopes?: string[]
  }): Promise<SettingsApiKeyCreateResponse> {
    return httpClient.post("/api/settings/api-keys", {
      owner_scope: input.owner_scope,
      project_slug: input.project_slug,
      name: input.name,
      scopes: input.scopes ?? ["agents.embed"],
    })
  }

  async revokeApiKey(keyId: string, input: { owner_scope: "organization" | "project"; project_slug?: string }): Promise<{ api_key: SettingsApiKey }> {
    const params = new URLSearchParams({ owner_scope: input.owner_scope })
    if (input.project_slug) params.set("project_slug", input.project_slug)
    return httpClient.post(`/api/settings/api-keys/${keyId}/revoke?${params.toString()}`)
  }

  async deleteApiKey(keyId: string, input: { owner_scope: "organization" | "project"; project_slug?: string }): Promise<void> {
    const params = new URLSearchParams({ owner_scope: input.owner_scope })
    if (input.project_slug) params.set("project_slug", input.project_slug)
    return httpClient.delete(`/api/settings/api-keys/${keyId}?${params.toString()}`)
  }
}

export const settingsApiKeysService = new SettingsApiKeysService()
