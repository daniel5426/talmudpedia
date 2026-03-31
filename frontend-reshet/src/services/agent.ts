import { httpClient } from "./http";
import type { FileUIPart } from "ai";

// ============================================================================
// Types
// ============================================================================

export interface Agent {
  id: string;
  tenant_id: string;
  name: string;
  slug: string;
  description?: string;
  status: 'draft' | 'published' | 'deprecated' | 'archived';
  version: number;
  show_in_playground: boolean;
  default_embed_policy_set_id?: string | null;
  tool_binding_status?: string | null;
  is_tool_enabled?: boolean;
  graph_definition?: AgentGraphDefinition;
  created_at: string;
  updated_at: string;
  published_at?: string;
}

export interface AgentGraphDefinition {
  spec_version?: string;
  workflow_contract?: {
    inputs: Array<{
      key: string;
      type: string;
      enabled?: boolean;
      required?: boolean;
      label?: string;
      description?: string;
      semantic_type?: string | null;
      readonly?: boolean;
      derived?: boolean;
    }>;
  };
  state_contract?: {
    variables: Array<{
      key: string;
      type: string;
      description?: string;
      schema?: Record<string, unknown>;
      default_value?: unknown;
    }>;
  };
  nodes: any[];
  edges: any[];
}

export interface AgentGraphInventoryItem {
  namespace: "workflow_input" | "state" | "node_output";
  key: string;
  type: string;
  label?: string;
  description?: string | null;
  node_id?: string;
  enabled?: boolean;
  readonly?: boolean;
  default_value?: unknown;
  required?: boolean;
  derived?: boolean;
  semantic_type?: string | null;
}

export interface AgentGraphNodeOutputGroup {
  node_id: string;
  node_type: string;
  node_label: string;
  fields: AgentGraphInventoryItem[];
}

export interface AgentGraphTemplateSuggestion {
  id: string;
  display_label: string;
  insert_text: string;
  type: string;
  namespace: string;
  key: string;
  node_id?: string;
}

export interface AgentGraphAnalysis {
  spec_version: string;
  inventory: {
    workflow_input: AgentGraphInventoryItem[];
    state: AgentGraphInventoryItem[];
    node_outputs: AgentGraphNodeOutputGroup[];
    accessible_node_outputs_by_node: Record<string, AgentGraphNodeOutputGroup[]>;
    template_suggestions: {
      global: AgentGraphTemplateSuggestion[];
      by_node: Record<string, AgentGraphTemplateSuggestion[]>;
    };
  };
  operator_contracts: Record<string, Record<string, unknown>>;
  errors: Array<Record<string, unknown>>;
  warnings: Array<Record<string, unknown>>;
}

export type ModelStatus = 'active' | 'deprecated' | 'disabled';
export type ModelProviderType = 'openai' | 'azure' | 'anthropic' | 'google' | 'xai' | 'cohere' | 'groq' | 'mistral' | 'together' | 'local' | 'gemini' | 'huggingface' | 'custom';
export type ModelCapabilityType = 'chat' | 'completion' | 'embedding' | 'image' | 'vision' | 'audio' | 'rerank' | 'speech_to_text' | 'text_to_speech';

export interface LogicalModel {
  id: string;
  name: string;
  description?: string;
  capability_type: ModelCapabilityType;
  metadata: Record<string, unknown>;
  default_resolution_policy: Record<string, unknown>;
  version: number;
  status: ModelStatus;
  is_active?: boolean;
  is_default?: boolean;
  tenant_id: string | null;
  created_at: string;
  updated_at: string;
  providers: ModelProviderSummary[];
}

export interface ModelProviderSummary {
  id: string;
  provider: ModelProviderType;
  provider_model_id: string;
  priority: number;
  is_enabled: boolean;
  config?: Record<string, unknown>;
  credentials_ref?: string | null;
  pricing_config?: PricingConfig;
}

export type PricingBillingMode = "per_token" | "per_1k_tokens" | "flat_per_request" | "manual" | "unknown";

export interface PricingConfig {
  currency?: string;
  billing_mode?: PricingBillingMode;
  rates?: Record<string, number>;
  minimum_charge?: number;
  flat_amount?: number;
  manual_total_cost?: number;
}

export interface CreateModelRequest {
  name: string;
  description?: string;
  capability_type: ModelCapabilityType;
  metadata?: Record<string, unknown>;
  default_resolution_policy?: Record<string, unknown>;
  is_default?: boolean;
  is_active?: boolean;
  status?: ModelStatus;
}

export interface UpdateModelRequest {
  name?: string;
  description?: string;
  metadata?: Record<string, unknown>;
  default_resolution_policy?: Record<string, unknown>;
  status?: ModelStatus;
  is_active?: boolean;
  is_default?: boolean;
}

export interface CreateProviderRequest {
  provider: ModelProviderType;
  provider_model_id: string;
  config?: Record<string, unknown>;
  credentials_ref?: string;
  priority?: number;
  pricing_config?: PricingConfig;
}

export interface UpdateProviderRequest {
  provider_model_id?: string;
  priority?: number;
  is_enabled?: boolean;
  config?: Record<string, unknown>;
  credentials_ref?: string | null;
  pricing_config?: PricingConfig;
}

export interface ModelsListResponse {
  models: LogicalModel[];
  total: number;
}

// Tool Types
export type ToolImplementationType = "internal" | "http" | "rag_pipeline" | "agent_call" | "function" | "custom" | "artifact" | "mcp";
export type ToolStatus = "draft" | "published" | "deprecated" | "disabled";
export type ToolTypeBucket = "built_in" | "mcp" | "artifact" | "custom";
export type ToolOwnership = "manual" | "artifact_bound" | "pipeline_bound" | "agent_bound" | "system";
export type ToolManager = "tools" | "artifacts" | "pipelines" | "agents" | "system";

export interface ToolDefinition {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  config_schema: Record<string, unknown>;
  implementation_type: ToolImplementationType;
  implementation_config?: Record<string, unknown>;
  execution_config?: Record<string, unknown>;
  version: string;
  status: ToolStatus;
  tool_type?: ToolTypeBucket;
  ownership: ToolOwnership;
  managed_by: ToolManager;
  source_object_type?: "artifact" | "pipeline" | "agent" | null;
  source_object_id?: string | null;
  can_edit_in_registry: boolean;
  can_publish_in_registry: boolean;
  can_delete_in_registry: boolean;
  tenant_id: string | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  artifact_id?: string;
  artifact_version?: string;
  artifact_revision_id?: string;
  visual_pipeline_id?: string;
  executable_pipeline_id?: string;
  builtin_key?: string | null;
  builtin_template_id?: string | null;
  is_builtin_template?: boolean;
  is_builtin_instance?: boolean;
  frontend_requirements?: {
    required: boolean;
    renderer_kind: string;
    package_name: string;
    contract_package_name: string;
    hosted_template_support?: Record<string, boolean>;
    install_docs_url?: string;
  } | null;
}

export interface CreateToolRequest {
  name: string;
  slug: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  implementation_type: ToolImplementationType;
  config_schema?: Record<string, unknown>;
  implementation_config?: Record<string, unknown>;
  execution_config?: Record<string, unknown>;
  artifact_id?: string;
  artifact_version?: string;
  status?: ToolStatus;
}

export interface UpdateToolRequest {
    name?: string;
    description?: string;
    input_schema?: Record<string, unknown>;
    output_schema?: Record<string, unknown>;
    config_schema?: Record<string, unknown>;
    implementation_type?: ToolImplementationType;
    implementation_config?: Record<string, unknown>;
    execution_config?: Record<string, unknown>;
    is_active?: boolean;
    artifact_id?: string;
    artifact_version?: string;
    status?: ToolStatus;
}

export interface ToolsListResponse {
  tools: ToolDefinition[];
  total: number;
}

export interface ExportAgentToolRequest {
  name?: string;
  description?: string;
}

export interface ExportAgentToolResponse {
  tool_id: string;
  tool_slug: string;
  tool_name: string;
  status: string;
}

export interface AgentRunStatus {
  id: string
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "paused"
  result?: any
  error?: string
  checkpoint?: any
  run_usage?: {
    source?: string | null
    input_tokens?: number | null
    output_tokens?: number | null
    total_tokens?: number | null
    cached_input_tokens?: number | null
    cached_output_tokens?: number | null
    reasoning_tokens?: number | null
  }
  context_window?: {
    source?: string | null
    model_id?: string | null
    max_tokens?: number | null
    max_tokens_source?: string | null
    input_tokens?: number | null
    remaining_tokens?: number | null
    usage_ratio?: number | null
  }
  run_tree?: AgentRunTreeResponse
  lineage?: {
    root_run_id?: string | null
    parent_run_id?: string | null
    parent_node_id?: string | null
    depth?: number
    spawn_key?: string | null
    orchestration_group_id?: string | null
  }
}

export interface AgentRunTreeGroupMember {
  id: string
  run_id: string
  ordinal: number
  status: string
}

export interface AgentRunTreeGroup {
  group_id: string
  status: string
  failure_policy?: string | null
  join_mode?: string | null
  quorum_threshold?: number | null
  timeout_s?: number | null
  parent_node_id?: string | null
  members: AgentRunTreeGroupMember[]
}

export interface AgentRunTreeNode {
  run_id: string
  agent_id: string
  status: string
  depth: number
  parent_run_id?: string | null
  parent_node_id?: string | null
  spawn_key?: string | null
  orchestration_group_id?: string | null
  created_at?: string
  children: AgentRunTreeNode[]
  groups: AgentRunTreeGroup[]
}

export interface AgentRunTreeResponse {
  root_run_id: string
  tree: AgentRunTreeNode
  node_count: number
}

export interface AgentExecutionEvent {
  event?: string
  type?: string
  run_id?: string
  seq?: number
  ts?: string
  span_id?: string
  name?: string
  data?: Record<string, any>
  metadata?: Record<string, any>
  received_at?: number
}

export interface AgentAttachmentDto {
  id: string;
  thread_id: string | null;
  kind: "image" | "document" | "audio";
  filename: string;
  mime_type: string;
  byte_size: number;
  status: string;
  processing_error: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AgentRunEventsResponse {
  run_id: string
  event_count: number
  events: Record<string, unknown>[]
}

export interface AgentOperatorSpec {
  type: string;
  category: string;
  display_name: string;
  description: string;
  reads: string[];
  writes: string[];
  config_schema: Record<string, any>;
  field_contracts?: Record<string, any>;
  output_contract?: Record<string, any>;
  ui: Record<string, any>;
}

async function filePartToFile(file: FileUIPart): Promise<File> {
  const response = await fetch(file.url);
  const blob = await response.blob();
  return new File([blob], file.filename || "attachment", {
    type: file.mediaType || blob.type || "application/octet-stream",
  });
}

// ============================================================================
// Services
// ============================================================================

export const agentService = {
  // Catalog / Metadata
  async listOperators(): Promise<AgentOperatorSpec[]> {
    return httpClient.get<AgentOperatorSpec[]>("/agents/operators");
  },

  async listAgents(params?: { status?: string, skip?: number, limit?: number, compact?: boolean }) {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    const compact = params?.compact ?? true;
    if (compact) query.set("compact", "true");
    const queryString = query.toString();
    const path = `/agents${queryString ? `?${queryString}` : ""}`;
    return httpClient.get<{ agents: Agent[], total: number }>(path);
  },

  async getAgent(id: string) {
    return httpClient.get<Agent>(`/agents/${id}`);
  },

  async analyzeGraph(id: string, graphDefinition: AgentGraphDefinition) {
    return httpClient.post<{ agent_id: string; graph_definition: AgentGraphDefinition; analysis: AgentGraphAnalysis }>(
      `/agents/${id}/graph/analyze`,
      { graph_definition: graphDefinition }
    );
  },

  async createAgent(data: Partial<Agent>) {
    return httpClient.post<Agent>('/agents', data);
  },

  async updateAgent(id: string, data: Partial<Agent>) {
    return httpClient.patch<Agent>(`/agents/${id}`, data);
  },

  async publishAgent(id: string) {
    return httpClient.post<Agent>(`/agents/${id}/publish`, {});
  },

  async deleteAgent(id: string) {
    return httpClient.delete<{ success?: boolean }>(`/agents/${id}`);
  },

  async exportAgentTool(id: string, data: ExportAgentToolRequest = {}) {
    return httpClient.post<ExportAgentToolResponse>(`/agents/${id}/export-tool`, data);
  },

  // Execution
  async startRun(agentId: string, input: string) {
    return httpClient.post<{ run_id: string }>(`/agents/${agentId}/run`, {
      input,
      messages: [] 
    });
  },

  async resumeRun(runId: string, payload: any) {
    return httpClient.post<{ status: string }>(`/agents/runs/${runId}/resume`, payload);
  },

  async cancelRun(runId: string, payload?: { assistantOutputText?: string }) {
    return httpClient.post<{ run_id: string; status: string; thread_id?: string | null }>(
      `/agents/runs/${runId}/cancel`,
      {
        assistant_output_text: payload?.assistantOutputText,
      }
    );
  },

  async getRunStatus(runId: string, includeTree = false) {
    const path = includeTree
      ? `/agents/runs/${runId}?include_tree=true`
      : `/agents/runs/${runId}`;
    return httpClient.get<AgentRunStatus>(path);
  },

  async getRunTree(runId: string) {
    return httpClient.get<AgentRunTreeResponse>(`/agents/runs/${runId}/tree`);
  },

  async getRunEvents(runId: string) {
    return httpClient.get<AgentRunEventsResponse>(`/agents/runs/${runId}/events`);
  },

  async executeAgent(id: string, input: Record<string, any>) {
    return httpClient.post(`/agents/${id}/execute`, { input_params: input });
  },

  async streamAgent(
    id: string,
    input: {
      text?: string;
      messages?: any[];
      runId?: string;
      threadId?: string;
      state?: Record<string, any>;
      context?: Record<string, any>;
      attachmentIds?: string[];
    },
    mode: 'debug' | 'production' = 'production'
  ) {
    // CRITICAL: Bypass Next.js dev proxy for SSE streaming.
    // The Next.js rewrite proxy buffers responses, causing all tokens to appear at once.
    // We call the backend directly for streaming endpoints only.
    const directBackendUrl = process.env.NEXT_PUBLIC_BACKEND_STREAM_URL || 'http://127.0.0.1:8026';
    const url = new URL(`${directBackendUrl}/agents/${id}/stream`);
    if (mode) {
        url.searchParams.append("mode", mode);
    }

    // Get auth token for direct request
    const { useAuthStore } = await import('@/lib/store/useAuthStore');
    const authState = useAuthStore.getState();
    const token = authState.token;
    const tenantId = authState.user?.tenant_id;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    } else {
      console.warn('[streamAgent] Missing bearer token; request may 401. Ensure login sets useAuthStore.token.');
    }
    if (tenantId) {
      headers['X-Tenant-ID'] = tenantId;
    }
    
    return fetch(url.toString(), {
      method: "POST",
      headers,
      credentials: "include", // allow cookies if available
      body: JSON.stringify({ 
        input: input.text, 
        messages: input.messages || [], 
        attachment_ids: input.attachmentIds || [],
        state: input.state || {},
        context: input.context || {},
        run_id: input.runId,
        thread_id: input.threadId,
      }),
    });
  },

  async uploadAgentAttachments(
    agentId: string,
    payload: { files: FileUIPart[]; threadId?: string }
  ): Promise<{ items: AgentAttachmentDto[] }> {
    const formData = new FormData();
    if (payload.threadId) {
      formData.set("thread_id", payload.threadId);
    }
    for (const item of payload.files) {
      const file = await filePartToFile(item);
      formData.append("files", file, item.filename || "attachment");
    }
    return httpClient.post<{ items: AgentAttachmentDto[] }>(
      `/agents/${agentId}/attachments/upload`,
      formData
    );
  }
};
