import { httpClient } from "./http";

export type ArtifactType = "draft" | "promoted" | "builtin";
export type ArtifactScope = "rag" | "agent" | "both";

export interface Artifact {
  id: string;
  name: string;
  display_name: string;
  description?: string;
  category: string;
  input_type: string;
  output_type: string;
  version: string;
  type: ArtifactType;
  scope: ArtifactScope;
  author?: string;
  tags: string[];
  config_schema: any[];
  created_at?: string;
  updated_at: string;
  python_code?: string;
  path?: string;
}

export interface ArtifactCreateRequest {
  name: string;
  display_name: string;
  description?: string;
  category?: string;
  input_type?: string;
  output_type?: string;
  scope?: ArtifactScope;
  python_code: string;
  config_schema?: any[];
}

export interface ArtifactUpdateRequest {
  display_name?: string;
  description?: string;
  category?: string;
  input_type?: string;
  output_type?: string;
  scope?: ArtifactScope;
  python_code?: string;
  config_schema?: any[];
}

export interface ArtifactTestRequest {
  artifact_id?: string;
  python_code?: string;
  input_data: any;
  config?: Record<string, any>;
  input_type?: string;
  output_type?: string;
}

export interface ArtifactTestResponse {
  success: boolean;
  data?: any;
  error_message?: string;
  execution_time_ms: number;
}

export const artifactsService = {
  list: async (tenantSlug?: string): Promise<Artifact[]> => {
    const url = tenantSlug ? `/admin/artifacts?tenant_slug=${tenantSlug}` : "/admin/artifacts";
    return httpClient.get<Artifact[]>(url);
  },

  get: async (id: string, tenantSlug?: string): Promise<Artifact> => {
    const url = tenantSlug ? `/admin/artifacts/${id}?tenant_slug=${tenantSlug}` : `/admin/artifacts/${id}`;
    return httpClient.get<Artifact>(url);
  },

  create: async (data: ArtifactCreateRequest, tenantSlug?: string): Promise<Artifact> => {
    const url = tenantSlug ? `/admin/artifacts?tenant_slug=${tenantSlug}` : "/admin/artifacts";
    return httpClient.post<Artifact>(url, data);
  },

  update: async (id: string, data: ArtifactUpdateRequest, tenantSlug?: string): Promise<Artifact> => {
    const url = tenantSlug ? `/admin/artifacts/${id}?tenant_slug=${tenantSlug}` : `/admin/artifacts/${id}`;
    return httpClient.put<Artifact>(url, data);
  },

  delete: async (id: string, tenantSlug?: string): Promise<void> => {
    const url = tenantSlug ? `/admin/artifacts/${id}?tenant_slug=${tenantSlug}` : `/admin/artifacts/${id}`;
    await httpClient.delete(url);
  },

  promote: async (id: string, namespace: string = "custom", version?: string, tenantSlug?: string): Promise<any> => {
    const params = new URLSearchParams();
    if (tenantSlug) params.set("tenant_slug", tenantSlug);
    const url = `/admin/artifacts/${id}/promote?${params.toString()}`;
    return httpClient.post(url, { namespace, version });
  },

  test: async (data: ArtifactTestRequest, tenantSlug?: string): Promise<ArtifactTestResponse> => {
    const url = tenantSlug ? `/admin/artifacts/test?tenant_slug=${tenantSlug}` : "/admin/artifacts/test";
    return httpClient.post<ArtifactTestResponse>(url, data);
  },
};
