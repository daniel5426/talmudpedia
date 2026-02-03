import { httpClient } from "./http";
import { ToolDefinition, ToolsListResponse, ToolImplementationType, ToolStatus, CreateToolRequest, UpdateToolRequest } from "./agent";

export const toolsService = {
  async listTools(
    implementationType?: ToolImplementationType,
    status?: ToolStatus,
    toolType?: string,
    skip = 0,
    limit = 50
  ): Promise<ToolsListResponse> {
    const query = new URLSearchParams();
    if (implementationType) query.set("implementation_type", implementationType);
    if (status) query.set("status", status);
    if (toolType) query.set("tool_type", toolType);
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
