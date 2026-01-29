import { httpClient } from "./http";
import { LogicalModel, ModelsListResponse, ModelCapabilityType, ModelStatus, CreateModelRequest, UpdateModelRequest, ModelProviderSummary, CreateProviderRequest } from "./agent";

// We re-export types that were previously in agent-resources from agent.ts 
// so we don't need to change imports in many places.

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
