import { httpClient } from "./http";

export type IntegrationCredentialCategory = "llm_provider" | "vector_store" | "artifact_secret" | "custom";

export interface IntegrationCredential {
  id: string;
  tenant_id: string;
  category: IntegrationCredentialCategory;
  provider_key: string;
  provider_variant?: string | null;
  display_name: string;
  credential_keys: string[];
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateCredentialRequest {
  category: IntegrationCredentialCategory;
  provider_key: string;
  provider_variant?: string | null;
  display_name: string;
  credentials: Record<string, unknown>;
  is_enabled?: boolean;
}

export interface UpdateCredentialRequest {
  category?: IntegrationCredentialCategory;
  provider_key?: string;
  provider_variant?: string | null;
  display_name?: string;
  credentials?: Record<string, unknown>;
  is_enabled?: boolean;
}

export interface CredentialStatus {
  id: string;
  category: IntegrationCredentialCategory;
  provider_key: string;
  provider_variant?: string | null;
  is_enabled: boolean;
  updated_at: string;
}

export const credentialsService = {
  async listCredentials(category?: IntegrationCredentialCategory): Promise<IntegrationCredential[]> {
    const query = new URLSearchParams();
    if (category) query.set("category", category);
    const queryString = query.toString();
    const path = `/admin/settings/credentials${queryString ? `?${queryString}` : ""}`;
    return httpClient.get<IntegrationCredential[]>(path);
  },

  async createCredential(data: CreateCredentialRequest): Promise<IntegrationCredential> {
    return httpClient.post<IntegrationCredential>("/admin/settings/credentials", data);
  },

  async updateCredential(id: string, data: UpdateCredentialRequest): Promise<IntegrationCredential> {
    return httpClient.patch<IntegrationCredential>(`/admin/settings/credentials/${id}`, data);
  },

  async deleteCredential(id: string): Promise<void> {
    await httpClient.delete(`/admin/settings/credentials/${id}`);
  },

  async listCredentialStatus(): Promise<CredentialStatus[]> {
    return httpClient.get<CredentialStatus[]>("/admin/settings/credentials/status");
  },
};
