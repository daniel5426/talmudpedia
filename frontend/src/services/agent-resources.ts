import api from "./api";

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

export type ModelStatus = 'active' | 'inactive' | 'deprecated' | 'disabled';
export type ModelProviderType = 'openai' | 'anthropic' | 'google' | 'cohere' | 'groq' | 'mistral' | 'together' | 'local' | 'gemini' | 'huggingface';
export type ModelCapabilityType = 'chat' | 'completion' | 'embedding' | 'image' | 'vision' | 'audio' | 'rerank' | 'speech_to_text';

export interface LogicalModel {
  id: string;
  name: string;
  slug: string;
  description?: string;
  provider: ModelProviderType;
  providers?: any[]; 
  external_model_id: string;
  capabilities: ModelCapabilityType[];
  capability_type?: ModelCapabilityType;
  is_active: boolean;
  status: ModelStatus;
}

export interface CreateModelRequest {
  name: string;
  slug?: string;
  description?: string;
  provider?: ModelProviderType;
  external_model_id?: string;
  capability_type?: ModelCapabilityType;
  capabilities?: ModelCapabilityType[];
}

export interface CreateProviderRequest {
  name: string;
  type: ModelProviderType;
  provider?: ModelProviderType;
  provider_model_id?: string;
  priority?: number;
  config?: Record<string, any>;
}

export interface AgentListResponse {
  agents: Agent[];
  total: number;
}

export const agentService = {
  async listAgents(params?: { status?: string, skip?: number, limit?: number }) {
    const response = await api.get<AgentListResponse>('/agents', { params });
    return response.data;
  },

  async getAgent(id: string) {
    const response = await api.get<Agent>(`/agents/${id}`);
    return response.data;
  },

  async createAgent(data: Partial<Agent>) {
    const response = await api.post<Agent>('/agents', data);
    return response.data;
  },

  async updateAgent(id: string, data: Partial<Agent>) {
    const response = await api.patch<Agent>(`/agents/${id}`, data);
    return response.data;
  },

  async publishAgent(id: string) {
    const response = await api.post<Agent>(`/agents/${id}/publish`);
    return response.data;
  },

  async executeAgent(id: string, input: Record<string, any>) {
    const response = await api.post(`/agents/${id}/execute`, { input_params: input });
    return response.data;
  }
};

export const modelsService = {
  async listModels() {
    const response = await api.get<LogicalModel[]>('/models');
    return response.data;
  },
  async createModel(data: CreateModelRequest) {
    const response = await api.post<LogicalModel>('/models', data);
    return response.data;
  },
  async deleteModel(id: string) {
    const response = await api.delete(`/models/${id}`);
    return response.data;
  },
  async addProvider(modelId: string, data: CreateProviderRequest) {
    const response = await api.post(`/models/${modelId}/providers`, data);
    return response.data;
  },
  async removeProvider(modelId: string, providerId: string) {
    const response = await api.delete(`/models/${modelId}/providers/${providerId}`);
    return response.data;
  }
};
