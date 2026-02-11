import { httpClient } from "./http";

export type PublishedAppStatus = "draft" | "published" | "paused" | "archived";
export type PublishedAppAuthProvider = "password" | "google";

export interface PublishedApp {
  id: string;
  tenant_id: string;
  agent_id: string;
  name: string;
  slug: string;
  status: PublishedAppStatus;
  auth_enabled: boolean;
  auth_providers: PublishedAppAuthProvider[];
  published_url?: string | null;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
  published_at?: string | null;
}

export interface CreatePublishedAppRequest {
  name: string;
  slug: string;
  agent_id: string;
  auth_enabled?: boolean;
  auth_providers?: PublishedAppAuthProvider[];
}

export interface UpdatePublishedAppRequest {
  name?: string;
  slug?: string;
  agent_id?: string;
  auth_enabled?: boolean;
  auth_providers?: PublishedAppAuthProvider[];
  status?: PublishedAppStatus;
}

export const publishedAppsService = {
  async list(): Promise<PublishedApp[]> {
    return httpClient.get<PublishedApp[]>("/admin/apps");
  },

  async get(appId: string): Promise<PublishedApp> {
    return httpClient.get<PublishedApp>(`/admin/apps/${appId}`);
  },

  async create(payload: CreatePublishedAppRequest): Promise<PublishedApp> {
    return httpClient.post<PublishedApp>("/admin/apps", payload);
  },

  async update(appId: string, payload: UpdatePublishedAppRequest): Promise<PublishedApp> {
    return httpClient.patch<PublishedApp>(`/admin/apps/${appId}`, payload);
  },

  async remove(appId: string): Promise<{ status: string; id: string }> {
    return httpClient.delete<{ status: string; id: string }>(`/admin/apps/${appId}`);
  },

  async publish(appId: string): Promise<PublishedApp> {
    return httpClient.post<PublishedApp>(`/admin/apps/${appId}/publish`, {});
  },

  async unpublish(appId: string): Promise<PublishedApp> {
    return httpClient.post<PublishedApp>(`/admin/apps/${appId}/unpublish`, {});
  },

  async runtimePreview(appId: string): Promise<{ app_id: string; slug: string; status: string; runtime_url: string }> {
    return httpClient.get<{ app_id: string; slug: string; status: string; runtime_url: string }>(`/admin/apps/${appId}/runtime-preview`);
  },
};
