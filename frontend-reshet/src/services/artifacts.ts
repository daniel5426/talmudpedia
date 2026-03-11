import { httpClient } from "./http";

export type ArtifactType = "draft" | "published";
export type ArtifactKind = "agent_node" | "rag_operator" | "tool_impl";
export type ArtifactOwnerType = "tenant" | "system";
export type ArtifactRunStatus = "queued" | "running" | "completed" | "failed" | "cancel_requested" | "cancelled";

export interface ArtifactSourceFile {
  path: string;
  content: string;
}

export interface ArtifactRuntimeConfig {
  source_files: ArtifactSourceFile[];
  entry_module_path: string;
  python_dependencies: string[];
  runtime_target: string;
}

export interface ArtifactCapabilityConfig {
  network_access: boolean;
  allowed_hosts: string[];
  secret_refs: string[];
  storage_access: string[];
  side_effects: string[];
}

export interface AgentArtifactContract {
  state_reads: string[];
  state_writes: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  node_ui: Record<string, unknown>;
}

export interface RAGArtifactContract {
  operator_category: string;
  pipeline_role: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  execution_mode: string;
}

export interface ToolArtifactContract {
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  side_effects: string[];
  execution_mode: string;
  tool_ui: Record<string, unknown>;
}

export interface Artifact {
  id: string;
  slug: string;
  display_name: string;
  description?: string;
  kind: ArtifactKind;
  owner_type: ArtifactOwnerType;
  type: ArtifactType;
  version: string;
  config_schema: Record<string, unknown>;
  runtime: ArtifactRuntimeConfig;
  capabilities: ArtifactCapabilityConfig;
  agent_contract?: AgentArtifactContract | null;
  rag_contract?: RAGArtifactContract | null;
  tool_contract?: ToolArtifactContract | null;
  created_at?: string;
  updated_at: string;
  system_key?: string | null;
  author?: string | null;
  tags: string[];
}

export interface ArtifactCreateRequest {
  slug: string;
  display_name: string;
  description?: string;
  kind: ArtifactKind;
  runtime: ArtifactRuntimeConfig;
  capabilities: ArtifactCapabilityConfig;
  config_schema: Record<string, unknown>;
  agent_contract?: AgentArtifactContract;
  rag_contract?: RAGArtifactContract;
  tool_contract?: ToolArtifactContract;
}

export interface ArtifactUpdateRequest {
  display_name?: string;
  description?: string;
  runtime?: ArtifactRuntimeConfig;
  capabilities?: ArtifactCapabilityConfig;
  config_schema?: Record<string, unknown>;
  agent_contract?: AgentArtifactContract;
  rag_contract?: RAGArtifactContract;
  tool_contract?: ToolArtifactContract;
}

export interface ArtifactConvertKindRequest {
  kind: ArtifactKind;
  agent_contract?: AgentArtifactContract;
  rag_contract?: RAGArtifactContract;
  tool_contract?: ToolArtifactContract;
}

export interface ArtifactPublishResponse {
  artifact_id: string;
  revision_id: string;
  version: string;
  status: "published";
}

export interface ArtifactTestRequest {
  artifact_id?: string;
  source_files?: ArtifactSourceFile[];
  entry_module_path?: string;
  dependencies?: string[];
  input_data: unknown;
  config?: Record<string, unknown>;
  kind?: ArtifactKind;
  runtime_target?: string;
  capabilities?: Record<string, unknown>;
  config_schema?: Record<string, unknown>;
  agent_contract?: AgentArtifactContract;
  rag_contract?: RAGArtifactContract;
  tool_contract?: ToolArtifactContract;
}

export interface ArtifactTestResponse {
  success: boolean;
  data?: unknown;
  error_message?: string;
  execution_time_ms: number;
  run_id?: string;
  error_payload?: Record<string, unknown>;
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
  result_payload?: Record<string, unknown>;
  error_payload?: Record<string, unknown>;
  stdout_excerpt?: string;
  stderr_excerpt?: string;
  duration_ms?: number;
  runtime_metadata?: Record<string, unknown>;
  created_at: string;
  started_at?: string;
  finished_at?: string;
}

export interface ArtifactRunEvent {
  id: string;
  sequence: number;
  timestamp?: string;
  event_type: string;
  payload: Record<string, unknown>;
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

  publish: async (id: string, tenantSlug?: string): Promise<ArtifactPublishResponse> => {
    const url = tenantSlug ? `/admin/artifacts/${id}/publish?tenant_slug=${tenantSlug}` : `/admin/artifacts/${id}/publish`;
    return httpClient.post<ArtifactPublishResponse>(url, {});
  },

  convertKind: async (id: string, data: ArtifactConvertKindRequest, tenantSlug?: string): Promise<Artifact> => {
    const url = tenantSlug ? `/admin/artifacts/${id}/convert-kind?tenant_slug=${tenantSlug}` : `/admin/artifacts/${id}/convert-kind`;
    return httpClient.post<Artifact>(url, data);
  },

  delete: async (id: string, tenantSlug?: string): Promise<void> => {
    const url = tenantSlug ? `/admin/artifacts/${id}?tenant_slug=${tenantSlug}` : `/admin/artifacts/${id}`;
    await httpClient.delete(url);
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
