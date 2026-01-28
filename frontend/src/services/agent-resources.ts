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
  created_at: string;
  updated_at: string;
  published_at?: string;
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
}

export interface CreateProviderRequest {
  provider: ModelProviderType;
  provider_model_id: string;
  config?: Record<string, unknown>;
  credentials_ref?: string;
  priority?: number;
}

export interface ModelsListResponse {
  models: LogicalModel[];
  total: number;
}

// Tool Types
export type ToolImplementationType = "internal" | "http" | "rag_retrieval" | "function" | "custom";
export type ToolStatus = "draft" | "published" | "deprecated" | "disabled";

export interface ToolDefinition {
  id: string;
  name: string;
  slug: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  implementation_type: ToolImplementationType;
  implementation_config: Record<string, unknown>;
  execution_config: Record<string, unknown>;
  version: string;
  status: ToolStatus;
  tenant_id: string;
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

export interface CreateToolRequest {
  name: string;
  slug: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  implementation_type: ToolImplementationType;
  implementation_config?: Record<string, unknown>;
  execution_config?: Record<string, unknown>;
}

export interface UpdateToolRequest {
  name?: string;
  description?: string;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  implementation_config?: Record<string, unknown>;
  execution_config?: Record<string, unknown>;
}

export interface ToolsListResponse {
  tools: ToolDefinition[];
  total: number;
}

// ============================================================================
// Services
// ============================================================================

// Operator Types
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

export const agentService = {
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

  async executeAgent(id: string, input: Record<string, any>) {
    return httpClient.post(`/agents/${id}/execute`, { input_params: input });
  },

  async streamAgent(id: string, input: Record<string, any>) {
    return httpClient.requestRaw(`/agents/${id}/stream`, {
      method: "POST",
      body: JSON.stringify({ input: input.text, messages: [], context: {} }),
    });
  }
};

export const modelsService = {
  async listModels(
    capabilityType?: ModelCapabilityType,
    status?: ModelStatus,
    skip = 0,
    limit = 50
  ): Promise<ModelsListResponse> {
    const query = new URLSearchParams();
    if (capabilityType) query.set("capability_type", capabilityType);
    if (status) query.set("status", status);
    query.set("skip", String(skip));
    query.set("limit", String(limit));
    const queryString = query.toString();
    
    return httpClient.get<ModelsListResponse>(`/models?${queryString}`);
  },

  async getModel(id: string): Promise<LogicalModel> {
    return httpClient.get<LogicalModel>(`/models/${id}`);
  },

  async createModel(data: CreateModelRequest): Promise<LogicalModel> {
    return httpClient.post<LogicalModel>('/models', data);
  },

  async updateModel(id: string, data: UpdateModelRequest): Promise<LogicalModel> {
    return httpClient.put<LogicalModel>(`/models/${id}`, data);
  },

  async deleteModel(id: string): Promise<void> {
    await httpClient.delete(`/models/${id}`);
  },

  async addProvider(modelId: string, data: CreateProviderRequest): Promise<ModelProviderSummary> {
    return httpClient.post<ModelProviderSummary>(`/models/${modelId}/providers`, data);
  },

  async removeProvider(modelId: string, providerId: string): Promise<void> {
    await httpClient.delete(`/models/${modelId}/providers/${providerId}`);
  },
};

export const toolsService = {
  async listTools(
    implementationType?: ToolImplementationType,
    status?: ToolStatus,
    skip = 0,
    limit = 50
  ): Promise<ToolsListResponse> {
    const query = new URLSearchParams();
    if (implementationType) query.set("implementation_type", implementationType);
    if (status) query.set("status", status);
    query.set("skip", String(skip));
    query.set("limit", String(limit));
    const queryString = query.toString();
    
    return httpClient.get<ToolsListResponse>(`/tools?${queryString}`);
  },

  async getTool(id: string): Promise<ToolDefinition> {
    return httpClient.get<ToolDefinition>(`/tools/${id}`);
  },

  async createTool(data: CreateToolRequest): Promise<ToolDefinition> {
    return httpClient.post<ToolDefinition>('/tools', data);
  },

  async updateTool(id: string, data: UpdateToolRequest): Promise<ToolDefinition> {
    return httpClient.put<ToolDefinition>(`/tools/${id}`, data);
  },

  async publishTool(id: string): Promise<ToolDefinition> {
    return httpClient.post<ToolDefinition>(`/tools/${id}/publish`, {});
  },

  async createVersion(id: string, newVersion: string): Promise<ToolDefinition> {
    return httpClient.post<ToolDefinition>(`/tools/${id}/version?new_version=${encodeURIComponent(newVersion)}`, {});
  },

  async deleteTool(id: string): Promise<void> {
    await httpClient.delete(`/tools/${id}`);
  },

  async testTool(id: string, input: Record<string, unknown>): Promise<unknown> {
    return httpClient.post(`/tools/${id}/test`, { input });
  },
};


