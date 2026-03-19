import { httpClient } from "./http";

// ============================================================================
// Types
// ============================================================================

export interface PromptRecord {
  id: string;
  tenant_id: string | null;
  name: string;
  description: string | null;
  content: string;
  scope: "tenant" | "global";
  status: "active" | "archived";
  ownership: "manual" | "system";
  managed_by: string | null;
  allowed_surfaces: string[];
  tags: string[];
  version: number;
  created_at: string;
  updated_at: string;
}

export interface PromptListResponse {
  prompts: PromptRecord[];
  total: number;
}

export interface PromptVersionRecord {
  id: string;
  prompt_id: string;
  version: number;
  name: string;
  description: string | null;
  content: string;
  allowed_surfaces: string[];
  tags: string[];
  created_by: string | null;
  created_at: string;
}

export interface PromptUsageRecord {
  resource_type: "agent" | "tool" | "artifact";
  resource_id: string;
  resource_name: string;
  surface: string;
  location_pointer: string;
  tenant_id: string | null;
  node_id: string | null;
}

export interface PromptMentionRecord {
  id: string;
  name: string;
  description: string | null;
  scope: string;
  tenant_id: string | null;
  updated_at: string;
}

export interface CreatePromptRequest {
  name: string;
  description?: string | null;
  content?: string;
  scope?: "tenant" | "global";
  allowed_surfaces?: string[];
  tags?: string[];
}

export interface UpdatePromptRequest {
  name?: string;
  description?: string | null;
  content?: string;
  allowed_surfaces?: string[];
  tags?: string[];
}

export interface PromptResolvePreviewResponse {
  text: string;
  bindings: Array<{
    prompt_id: string;
    version: number;
    surface: string | null;
    name: string;
  }>;
  errors: string[];
}

// ============================================================================
// Service
// ============================================================================

export const promptsService = {
  async listPrompts(params?: {
    q?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<PromptListResponse> {
    const query = new URLSearchParams();
    if (params?.q) query.set("q", params.q);
    if (params?.status) query.set("status", params.status);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return httpClient.get<PromptListResponse>(`/prompts${qs ? `?${qs}` : ""}`);
  },

  async getPrompt(id: string): Promise<PromptRecord> {
    return httpClient.get<PromptRecord>(`/prompts/${id}`);
  },

  async createPrompt(data: CreatePromptRequest): Promise<PromptRecord> {
    return httpClient.post<PromptRecord>("/prompts", data);
  },

  async updatePrompt(id: string, data: UpdatePromptRequest): Promise<PromptRecord> {
    return httpClient.patch<PromptRecord>(`/prompts/${id}`, data);
  },

  async deletePrompt(id: string): Promise<{ deleted: boolean }> {
    return httpClient.delete<{ deleted: boolean }>(`/prompts/${id}`);
  },

  async archivePrompt(id: string): Promise<PromptRecord> {
    return httpClient.post<PromptRecord>(`/prompts/${id}/archive`, {});
  },

  async restorePrompt(id: string): Promise<PromptRecord> {
    return httpClient.post<PromptRecord>(`/prompts/${id}/restore`, {});
  },

  async listVersions(id: string): Promise<PromptVersionRecord[]> {
    return httpClient.get<PromptVersionRecord[]>(`/prompts/${id}/versions`);
  },

  async rollback(id: string, version: number): Promise<PromptRecord> {
    return httpClient.post<PromptRecord>(`/prompts/${id}/rollback`, { version });
  },

  async getUsage(id: string): Promise<PromptUsageRecord[]> {
    return httpClient.get<PromptUsageRecord[]>(`/prompts/${id}/usage`);
  },

  async searchMentions(params?: {
    q?: string;
    surface?: string;
    limit?: number;
  }): Promise<PromptMentionRecord[]> {
    const query = new URLSearchParams();
    if (params?.q) query.set("q", params.q);
    if (params?.surface) query.set("surface", params.surface);
    if (params?.limit) query.set("limit", String(params.limit));
    const qs = query.toString();
    return httpClient.get<PromptMentionRecord[]>(`/prompts/mentions/search${qs ? `?${qs}` : ""}`);
  },

  async resolvePreview(text: string, surface?: string): Promise<PromptResolvePreviewResponse> {
    return httpClient.post<PromptResolvePreviewResponse>("/prompts/resolve-preview", {
      text,
      surface: surface ?? null,
    });
  },
};
