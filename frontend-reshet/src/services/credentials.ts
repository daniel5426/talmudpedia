import { httpClient } from "./http";
import type { ControlPlaneListResponse, ControlPlaneListView } from "./types";

export type IntegrationCredentialCategory = "llm_provider" | "vector_store" | "tool_provider" | "custom";

export interface IntegrationCredential {
  id: string;
  organization_id?: string | null;
  category: IntegrationCredentialCategory;
  provider_key: string;
  provider_variant?: string | null;
  display_name: string;
  credential_keys: string[];
  is_enabled: boolean;
  is_default: boolean;
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
  is_default?: boolean;
}

export interface UpdateCredentialRequest {
  category?: IntegrationCredentialCategory;
  provider_key?: string;
  provider_variant?: string | null;
  display_name?: string;
  credentials?: Record<string, unknown>;
  is_enabled?: boolean;
  is_default?: boolean;
}

export interface CredentialStatus {
  id: string;
  category: IntegrationCredentialCategory;
  provider_key: string;
  provider_variant?: string | null;
  is_enabled: boolean;
  is_default: boolean;
  updated_at: string;
}

export interface CredentialUsageModelProvider {
  binding_id: string;
  model_id: string;
  model_name: string;
  provider: string;
  provider_model_id: string;
}

export interface CredentialUsageKnowledgeStore {
  store_id: string;
  store_name: string;
  backend: string;
}

export interface CredentialUsageTool {
  tool_id: string;
  tool_name: string;
  builtin_key?: string | null;
  implementation_type?: string | null;
}

export interface CredentialUsageResponse {
  credential_id: string;
  model_providers: CredentialUsageModelProvider[];
  knowledge_stores: CredentialUsageKnowledgeStore[];
  tools: CredentialUsageTool[];
}

export const credentialsService = {
  async listCredentials(
    category?: IntegrationCredentialCategory,
    params?: { skip?: number; limit?: number; view?: ControlPlaneListView }
  ): Promise<ControlPlaneListResponse<IntegrationCredential>> {
    const query = new URLSearchParams();
    if (category) query.set("category", category);
    query.set("skip", String(params?.skip ?? 0));
    query.set("limit", String(params?.limit ?? 20));
    query.set("view", params?.view ?? "summary");
    const queryString = query.toString();
    const path = `/admin/settings/credentials${queryString ? `?${queryString}` : ""}`;
    return httpClient.get<ControlPlaneListResponse<IntegrationCredential>>(path);
  },

  async createCredential(data: CreateCredentialRequest): Promise<IntegrationCredential> {
    return httpClient.post<IntegrationCredential>("/admin/settings/credentials", data);
  },

  async updateCredential(id: string, data: UpdateCredentialRequest): Promise<IntegrationCredential> {
    return httpClient.patch<IntegrationCredential>(`/admin/settings/credentials/${id}`, data);
  },

  async getCredentialUsage(id: string): Promise<CredentialUsageResponse> {
    return httpClient.get<CredentialUsageResponse>(`/admin/settings/credentials/${id}/usage`);
  },

  async deleteCredential(id: string, opts?: { force_disconnect?: boolean }): Promise<void> {
    const query = new URLSearchParams();
    if (opts?.force_disconnect) query.set("force_disconnect", "true");
    const suffix = query.toString() ? `?${query.toString()}` : "";
    await httpClient.delete(`/admin/settings/credentials/${id}${suffix}`);
  },

  async listCredentialStatus(): Promise<CredentialStatus[]> {
    return httpClient.get<CredentialStatus[]>("/admin/settings/credentials/status");
  },
};
