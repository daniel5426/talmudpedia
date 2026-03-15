import { httpClient } from "./http";
import { useAuthStore } from "@/lib/store/useAuthStore";

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
  capabilities?: ArtifactCapabilityConfig;
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

export interface ArtifactVersionListItem {
  id: string;
  artifact_id: string;
  revision_number: number;
  version_label: string;
  is_published: boolean;
  is_current_draft: boolean;
  is_current_published: boolean;
  source_file_count: number;
  created_at: string;
  created_by?: string | null;
}

export interface ArtifactVersion extends ArtifactVersionListItem {
  slug: string;
  display_name: string;
  description?: string | null;
  kind: ArtifactKind;
  config_schema: Record<string, unknown>;
  runtime: ArtifactRuntimeConfig;
  capabilities: ArtifactCapabilityConfig;
  agent_contract?: AgentArtifactContract | null;
  rag_contract?: RAGArtifactContract | null;
  tool_contract?: ToolArtifactContract | null;
}

export interface ArtifactWorkingDraft {
  artifact_id?: string | null;
  draft_key?: string | null;
  draft_snapshot: Record<string, unknown>;
  updated_at?: string | null;
}

export interface ArtifactWorkingDraftUpdateRequest {
  artifact_id?: string;
  draft_key?: string;
  draft_snapshot: Record<string, unknown>;
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

export interface ArtifactCodingStreamEvent {
  version?: string;
  event: string;
  run_id: string;
  seq: number;
  ts: string;
  stage: string;
  payload?: Record<string, unknown>;
  diagnostics?: Array<Record<string, unknown>>;
}

export interface ArtifactCodingRun {
  run_id: string;
  status: string;
  chat_session_id?: string | null;
  artifact_id?: string | null;
  draft_key?: string | null;
  surface?: string | null;
  requested_model_id?: string | null;
  resolved_model_id?: string | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export type ArtifactCodingScopeMode = "locked" | "standalone";

export interface ArtifactCodingChatSession {
  id: string;
  title: string;
  artifact_id?: string | null;
  draft_key?: string | null;
  scope_mode: ArtifactCodingScopeMode;
  active_run_id?: string | null;
  last_run_id?: string | null;
  created_at: string;
  updated_at: string;
  last_message_at: string;
}

export interface ArtifactCodingChatMessage {
  id: string;
  run_id: string;
  role: "user" | "assistant" | string;
  content: string;
  created_at: string;
}

export interface ArtifactCodingRunEvent {
  run_id: string;
  event: string;
  stage: string;
  payload: Record<string, unknown>;
  diagnostics: Array<Record<string, unknown>>;
  ts?: string | null;
}

export interface ArtifactCodingChatSessionDetail {
  session: ArtifactCodingChatSession;
  messages: ArtifactCodingChatMessage[];
  run_events: ArtifactCodingRunEvent[];
  draft_snapshot: Record<string, unknown>;
  paging: {
    has_more: boolean;
    next_before_message_id?: string | null;
  };
}

export interface ArtifactCodingActiveRunState {
  run_id: string;
  status: string;
}

export interface ArtifactCodingAnswerQuestionRequest {
  question_id: string;
  answers: string[][];
}

export interface ArtifactCodingRevertRequest {
  run_id: string;
}

export interface ArtifactCodingPromptRequest {
  input: string;
  chat_session_id?: string;
  artifact_id?: string;
  draft_key?: string;
  scope_mode?: ArtifactCodingScopeMode;
  model_id?: string | null;
  client_message_id?: string;
  draft_snapshot: Record<string, unknown>;
}

export interface ArtifactCodingPromptSubmissionResponse {
  submission_status: "started";
  chat_session_id: string;
  run: ArtifactCodingRun;
}

export interface ArtifactCodingModelOption {
  id: string | null;
  label: string;
  description?: string;
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

  listVersions: async (artifactId: string, tenantSlug?: string): Promise<ArtifactVersionListItem[]> => {
    const url = tenantSlug
      ? `/admin/artifacts/${artifactId}/versions?tenant_slug=${tenantSlug}`
      : `/admin/artifacts/${artifactId}/versions`;
    return httpClient.get<ArtifactVersionListItem[]>(url);
  },

  getVersion: async (artifactId: string, revisionId: string, tenantSlug?: string): Promise<ArtifactVersion> => {
    const url = tenantSlug
      ? `/admin/artifacts/${artifactId}/versions/${revisionId}?tenant_slug=${tenantSlug}`
      : `/admin/artifacts/${artifactId}/versions/${revisionId}`;
    return httpClient.get<ArtifactVersion>(url);
  },

  getWorkingDraft: async (artifactId: string, tenantSlug?: string): Promise<ArtifactWorkingDraft> => {
    const url = tenantSlug
      ? `/admin/artifacts/${artifactId}/working-draft?tenant_slug=${tenantSlug}`
      : `/admin/artifacts/${artifactId}/working-draft`;
    return httpClient.get<ArtifactWorkingDraft>(url);
  },

  updateWorkingDraft: async (
    artifactId: string,
    payload: ArtifactWorkingDraftUpdateRequest,
    tenantSlug?: string,
  ): Promise<ArtifactWorkingDraft> => {
    const url = tenantSlug
      ? `/admin/artifacts/${artifactId}/working-draft?tenant_slug=${tenantSlug}`
      : `/admin/artifacts/${artifactId}/working-draft`;
    return httpClient.put<ArtifactWorkingDraft>(url, payload);
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

  submitCodingAgentPrompt: async (
    payload: ArtifactCodingPromptRequest,
    tenantSlug?: string,
  ): Promise<ArtifactCodingPromptSubmissionResponse> => {
    const url = tenantSlug
      ? `/admin/artifacts/coding-agent/v1/prompts?tenant_slug=${tenantSlug}`
      : "/admin/artifacts/coding-agent/v1/prompts";
    return httpClient.post<ArtifactCodingPromptSubmissionResponse>(url, payload);
  },

  listCodingAgentChatSessions: async (
    options: { artifactId?: string | null; draftKey?: string | null; scopeMode?: ArtifactCodingScopeMode | null; limit?: number },
    tenantSlug?: string,
  ): Promise<ArtifactCodingChatSession[]> => {
    const params = new URLSearchParams();
    if (options.artifactId) params.set("artifact_id", options.artifactId);
    if (options.draftKey) params.set("draft_key", options.draftKey);
    if (options.scopeMode) params.set("scope_mode", options.scopeMode);
    params.set("limit", String(Math.max(1, Number(options.limit || 25))));
    if (tenantSlug) params.set("tenant_slug", tenantSlug);
    return httpClient.get<ArtifactCodingChatSession[]>(
      `/admin/artifacts/coding-agent/v1/sessions?${params.toString()}`,
    );
  },

  getCodingAgentChatSession: async (
    sessionId: string,
    options: { limit?: number; before_message_id?: string | null; tenantSlug?: string } = {},
  ): Promise<ArtifactCodingChatSessionDetail> => {
    const params = new URLSearchParams();
    params.set("limit", String(Math.max(1, Number(options.limit || 10))));
    if (options.before_message_id) {
      params.set("before_message_id", options.before_message_id);
    }
    if (options.tenantSlug) {
      params.set("tenant_slug", options.tenantSlug);
    }
    return httpClient.get<ArtifactCodingChatSessionDetail>(
      `/admin/artifacts/coding-agent/v1/sessions/${sessionId}?${params.toString()}`,
    );
  },

  getCodingAgentChatSessionActiveRun: async (
    sessionId: string,
    tenantSlug?: string,
  ): Promise<ArtifactCodingActiveRunState> => {
    const url = tenantSlug
      ? `/admin/artifacts/coding-agent/v1/sessions/${sessionId}/active-run?tenant_slug=${tenantSlug}`
      : `/admin/artifacts/coding-agent/v1/sessions/${sessionId}/active-run`;
    return httpClient.get<ArtifactCodingActiveRunState>(url);
  },

  findCodingAgentChatSessionActiveRun: async (
    sessionId: string,
    tenantSlug?: string,
  ): Promise<ArtifactCodingActiveRunState | null> => {
    const url = tenantSlug
      ? `/admin/artifacts/coding-agent/v1/sessions/${sessionId}/active-run?tenant_slug=${tenantSlug}`
      : `/admin/artifacts/coding-agent/v1/sessions/${sessionId}/active-run`;
    const response = await httpClient.requestRaw(url, { method: "GET" });
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      let message = "Request failed";
      try {
        const data = await response.json();
        message = data?.detail || data?.message || message;
      } catch {
        message = response.statusText || message;
      }
      throw new Error(typeof message === "string" ? message : JSON.stringify(message));
    }
    return response.json() as Promise<ArtifactCodingActiveRunState>;
  },

  streamCodingAgentRun: async (runId: string, tenantId?: string | null): Promise<Response> => {
    const streamBase = String(process.env.NEXT_PUBLIC_BACKEND_STREAM_URL || "").trim();
    const backendBase = String(process.env.NEXT_PUBLIC_BACKEND_URL || "").trim();
    const directBackendUrl = /^https?:\/\//i.test(streamBase)
      ? streamBase
      : /^https?:\/\//i.test(backendBase)
        ? backendBase
        : "http://127.0.0.1:8026";
    const authState = useAuthStore.getState();
    const token = authState.token;
    const headers: Record<string, string> = {
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    if (tenantId) {
      headers["X-Tenant-ID"] = tenantId;
    } else if (authState.user?.tenant_id) {
      headers["X-Tenant-ID"] = authState.user.tenant_id;
    }
    const url = new URL(
      `/admin/artifacts/coding-agent/v1/runs/${encodeURIComponent(runId)}/stream`,
      directBackendUrl,
    );
    return fetch(url.toString(), {
      method: "GET",
      headers,
      credentials: "include",
    });
  },

  getCodingAgentRun: async (runId: string, tenantSlug?: string): Promise<ArtifactCodingRun> => {
    const url = tenantSlug
      ? `/admin/artifacts/coding-agent/v1/runs/${runId}?tenant_slug=${tenantSlug}`
      : `/admin/artifacts/coding-agent/v1/runs/${runId}`;
    return httpClient.get<ArtifactCodingRun>(url);
  },

  cancelCodingAgentRun: async (runId: string, tenantSlug?: string): Promise<ArtifactCodingRun> => {
    const url = tenantSlug
      ? `/admin/artifacts/coding-agent/v1/runs/${runId}/cancel?tenant_slug=${tenantSlug}`
      : `/admin/artifacts/coding-agent/v1/runs/${runId}/cancel`;
    return httpClient.post<ArtifactCodingRun>(url, {});
  },

  answerCodingAgentRunQuestion: async (
    runId: string,
    payload: ArtifactCodingAnswerQuestionRequest,
    tenantSlug?: string,
  ): Promise<ArtifactCodingRun> => {
    const url = tenantSlug
      ? `/admin/artifacts/coding-agent/v1/runs/${runId}/answer-question?tenant_slug=${tenantSlug}`
      : `/admin/artifacts/coding-agent/v1/runs/${runId}/answer-question`;
    return httpClient.post<ArtifactCodingRun>(url, payload);
  },

  revertCodingAgentSession: async (
    sessionId: string,
    payload: ArtifactCodingRevertRequest,
    tenantSlug?: string,
  ): Promise<ArtifactCodingChatSessionDetail> => {
    const url = tenantSlug
      ? `/admin/artifacts/coding-agent/v1/sessions/${sessionId}/revert?tenant_slug=${tenantSlug}`
      : `/admin/artifacts/coding-agent/v1/sessions/${sessionId}/revert`;
    return httpClient.post<ArtifactCodingChatSessionDetail>(url, payload);
  },

  listCodingAgentModels: async (): Promise<ArtifactCodingModelOption[]> => {
    return [{ id: null, label: "Auto", description: "Use the default artifact coding model" }];
  },
};
