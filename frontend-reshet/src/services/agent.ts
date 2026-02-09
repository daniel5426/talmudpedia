import { httpClient } from "./http";

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
  graph_definition?: AgentGraphDefinition;
  created_at: string;
  updated_at: string;
  published_at?: string;
}

export interface AgentGraphDefinition {
  spec_version?: string;
  nodes: any[];
  edges: any[];
}

export type ModelStatus = 'active' | 'deprecated' | 'disabled';
export type ModelProviderType = 'openai' | 'anthropic' | 'google' | 'cohere' | 'groq' | 'mistral' | 'together' | 'local' | 'gemini' | 'huggingface' | 'custom';
export type ModelCapabilityType = 'chat' | 'completion' | 'embedding' | 'image' | 'vision' | 'audio' | 'rerank' | 'speech_to_text' | 'text_to_speech';

export interface LogicalModel {
  id: string;
  name: string;
  slug: string;
  description?: string;
  capability_type: ModelCapabilityType;
  metadata: Record<string, unknown>;
  default_resolution_policy: Record<string, unknown>;
  version: number;
  status: ModelStatus;
  is_active?: boolean;
  is_default?: boolean;
  tenant_id: string;
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
}

export interface CreateModelRequest {
  name: string;
  slug: string;
  description?: string;
  capability_type: ModelCapabilityType;
  metadata?: Record<string, unknown>;
  default_resolution_policy?: Record<string, unknown>;
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
}

export interface UpdateProviderRequest {
  provider_model_id?: string;
  priority?: number;
  is_enabled?: boolean;
  config?: Record<string, unknown>;
  credentials_ref?: string | null;
}

export interface ModelsListResponse {
  models: LogicalModel[];
  total: number;
}

// Tool Types
export type ToolImplementationType = "internal" | "http" | "rag_retrieval" | "function" | "custom" | "artifact" | "mcp";
export type ToolStatus = "draft" | "published" | "deprecated" | "disabled";
export type ToolTypeBucket = "built_in" | "mcp" | "artifact" | "custom";

export interface ToolDefinition {
  id: string;
  name: string;
  slug: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  implementation_type: ToolImplementationType;
  implementation_config?: Record<string, unknown>;
  execution_config?: Record<string, unknown>;
  version: string;
  status: ToolStatus;
  tool_type?: ToolTypeBucket;
  tenant_id: string;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  artifact_id?: string;
  artifact_version?: string;
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

export interface AgentRunStatus {
  id: string
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "paused"
  result?: any
  error?: string
  checkpoint?: any
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
  span_id?: string
  name?: string
  data?: Record<string, any>
  metadata?: Record<string, any>
  received_at?: number
}

export interface AgentOperatorSpec {
  type: string;
  category: string;
  display_name: string;
  description: string;
  reads: string[];
  writes: string[];
  config_schema: Record<string, any>;
  ui: Record<string, any>;
}

// ============================================================================
// Services
// ============================================================================

export const agentService = {
  // Catalog / Metadata
  async listOperators(): Promise<AgentOperatorSpec[]> {
    return httpClient.get<AgentOperatorSpec[]>("/agents/operators");
  },

  async listAgents(params?: { status?: string, skip?: number, limit?: number }) {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    const queryString = query.toString();
    const path = `/agents${queryString ? `?${queryString}` : ""}`;
    return httpClient.get<{ agents: Agent[], total: number }>(path);
  },

  async getAgent(id: string) {
    return httpClient.get<Agent>(`/agents/${id}`);
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

  async getRunStatus(runId: string, includeTree = false) {
    const path = includeTree
      ? `/agents/runs/${runId}?include_tree=true`
      : `/agents/runs/${runId}`;
    return httpClient.get<AgentRunStatus>(path);
  },

  async getRunTree(runId: string) {
    return httpClient.get<AgentRunTreeResponse>(`/agents/runs/${runId}/tree`);
  },

  async executeAgent(id: string, input: Record<string, any>) {
    return httpClient.post(`/agents/${id}/execute`, { input_params: input });
  },

  async streamAgent(
    id: string,
    input: { text?: string; messages?: any[]; runId?: string; context?: Record<string, any> },
    mode: 'debug' | 'production' = 'production'
  ) {
    // CRITICAL: Bypass Next.js dev proxy for SSE streaming.
    // The Next.js rewrite proxy buffers responses, causing all tokens to appear at once.
    // We call the backend directly for streaming endpoints only.
    const directBackendUrl = process.env.NEXT_PUBLIC_BACKEND_STREAM_URL || 'http://127.0.0.1:8000';
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
        context: input.context || {},
        run_id: input.runId 
      }),
    });
  }
};
