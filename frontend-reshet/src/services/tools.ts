import { httpClient } from "./http";
import {
  ToolDefinition,
  ToolsListResponse,
  ToolImplementationType,
  ToolStatus,
  CreateToolRequest,
  UpdateToolRequest,
} from "./agent";
import type { ControlPlaneListView } from "./types";

function toUpperEnum(value?: string): string | undefined {
  return value ? value.toUpperCase() : undefined;
}

function toLowerEnum<T extends string | undefined>(value: T): T {
  return (value ? (value.toLowerCase() as T) : value);
}

function normalizeTool(tool: ToolDefinition): ToolDefinition {
  return {
    ...tool,
    status: toLowerEnum(tool.status) as ToolStatus,
    implementation_type: toLowerEnum(tool.implementation_type) as ToolImplementationType,
  };
}

function normalizeToolPayload<T extends CreateToolRequest | UpdateToolRequest>(payload: T): T {
  const next = { ...payload } as T;
  if ("status" in next && next.status) {
    next.status = toUpperEnum(next.status) as T["status"];
  }
  if ("implementation_type" in next && next.implementation_type) {
    next.implementation_type = toUpperEnum(next.implementation_type) as T["implementation_type"];
  }
  return next;
}

export const toolsService = {
  async listTools(
    implementationType?: ToolImplementationType,
    status?: ToolStatus,
    toolType?: string,
    skip = 0,
    limit = 20,
    view: ControlPlaneListView = "summary",
  ): Promise<ToolsListResponse> {
    const query = new URLSearchParams();
    if (implementationType) query.set("implementation_type", toUpperEnum(implementationType)!);
    if (status) query.set("status", toUpperEnum(status)!);
    if (toolType) query.set("tool_type", toolType);
    query.set("skip", String(skip));
    query.set("limit", String(limit));
    query.set("view", view);
    const queryString = query.toString();

    const response = await httpClient.get<ToolsListResponse>(`/tools?${queryString}`);
    return {
      ...response,
      items: response.items.map(normalizeTool),
    };
  },

  async getTool(id: string): Promise<ToolDefinition> {
    const tool = await httpClient.get<ToolDefinition>(`/tools/${id}`);
    return normalizeTool(tool);
  },

  async createTool(data: CreateToolRequest): Promise<ToolDefinition> {
    const tool = await httpClient.post<ToolDefinition>('/tools', normalizeToolPayload(data));
    return normalizeTool(tool);
  },

  async updateTool(id: string, data: UpdateToolRequest): Promise<ToolDefinition> {
    const tool = await httpClient.put<ToolDefinition>(`/tools/${id}`, normalizeToolPayload(data));
    return normalizeTool(tool);
  },

  async publishTool(id: string): Promise<ToolDefinition> {
    const tool = await httpClient.post<ToolDefinition>(`/tools/${id}/publish`, {});
    return normalizeTool(tool);
  },

  async createVersion(id: string, newVersion: string): Promise<ToolDefinition> {
    const tool = await httpClient.post<ToolDefinition>(`/tools/${id}/version?new_version=${encodeURIComponent(newVersion)}`, {});
    return normalizeTool(tool);
  },

  async deleteTool(id: string): Promise<void> {
    await httpClient.delete(`/tools/${id}`);
  },

  async listBuiltinTemplates(skip = 0, limit = 100): Promise<ToolsListResponse> {
    const query = new URLSearchParams();
    query.set("skip", String(skip));
    query.set("limit", String(limit));
    const response = await httpClient.get<{ tools: ToolDefinition[]; total: number }>(`/tools/builtins/templates?${query.toString()}`);
    return {
      items: response.tools.map(normalizeTool),
      total: response.total,
      has_more: skip + response.tools.length < response.total,
      skip,
      limit,
      view: "summary",
    };
  },
};
