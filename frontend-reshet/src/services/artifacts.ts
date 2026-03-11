import { httpClient } from "./http";

export type ArtifactType = "draft" | "promoted" | "builtin";
export type ArtifactScope = "rag" | "agent" | "both" | "tool";
export type ArtifactRunStatus = "queued" | "running" | "completed" | "failed" | "cancel_requested" | "cancelled";

export interface ArtifactSourceFile {
  path: string;
  content: string;
}

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
  source_files?: ArtifactSourceFile[];
  entry_module_path?: string;
  dependencies?: string[];
  path?: string;
  reads: string[];
  writes: string[];
  inputs: any[];
  outputs: any[];
}

export interface ArtifactCreateRequest {
  name: string;
  display_name: string;
  description?: string;
  category?: string;
  input_type?: string;
  output_type?: string;
  scope?: ArtifactScope;
  source_files: ArtifactSourceFile[];
  entry_module_path: string;
  dependencies?: string[];
  config_schema?: any[];
  reads?: string[];
  writes?: string[];
  inputs?: any[];
  outputs?: any[];
}

export interface ArtifactUpdateRequest {
  display_name?: string;
  description?: string;
  category?: string;
  input_type?: string;
  output_type?: string;
  scope?: ArtifactScope;
  source_files?: ArtifactSourceFile[];
  entry_module_path?: string;
  dependencies?: string[];
  config_schema?: any[];
  reads?: string[];
  writes?: string[];
  inputs?: any[];
  outputs?: any[];
}

export interface ArtifactTestRequest {
  artifact_id?: string;
  source_files?: ArtifactSourceFile[];
  entry_module_path?: string;
  dependencies?: string[];
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
  run_id?: string;
  error_payload?: Record<string, any>;
  stdout_excerpt?: string;
  stderr_excerpt?: string;
}

export interface ArtifactRun {
  id: string;
  artifact_id?: string;
  revision_id: string;
  domain: string;
  status: ArtifactRunStatus;
  queue_class: string;
  result_payload?: Record<string, any>;
  error_payload?: Record<string, any>;
  stdout_excerpt?: string;
  stderr_excerpt?: string;
  duration_ms?: number;
  created_at: string;
  started_at?: string;
  finished_at?: string;
}

export interface ArtifactRunEvent {
  id: string;
  sequence: number;
  timestamp?: string;
  event_type: string;
  payload: Record<string, any>;
}

export interface ArtifactRunCreateResponse {
  run_id: string;
  status: ArtifactRunStatus;
}

export interface ArtifactRunEventsResponse {
  run_id: string;
  event_count: number;
  events: ArtifactRunEvent[];
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

  createTestRun: async (data: ArtifactTestRequest, tenantSlug?: string): Promise<ArtifactRunCreateResponse> => {
    const url = tenantSlug ? `/admin/artifacts/test-runs?tenant_slug=${tenantSlug}` : "/admin/artifacts/test-runs";
    return httpClient.post<ArtifactRunCreateResponse>(url, data);
  },

  getRun: async (runId: string, tenantSlug?: string): Promise<ArtifactRun> => {
    const url = tenantSlug ? `/admin/artifact-runs/${runId}?tenant_slug=${tenantSlug}` : `/admin/artifact-runs/${runId}`;
    return httpClient.get<ArtifactRun>(url);
  },

  getRunEvents: async (runId: string, tenantSlug?: string): Promise<ArtifactRunEventsResponse> => {
    const url = tenantSlug
      ? `/admin/artifact-runs/${runId}/events?tenant_slug=${tenantSlug}`
      : `/admin/artifact-runs/${runId}/events`;
    return httpClient.get<ArtifactRunEventsResponse>(url);
  },
};
