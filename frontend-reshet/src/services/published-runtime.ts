const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "/api/py";

export type PublishedRuntimeAuthProvider = "password" | "google";

export interface PublishedRuntimeConfig {
  id: string;
  organization_id: string;
  agent_id: string;
  name: string;
  description?: string | null;
  logo_url?: string | null;
  public_id: string;
  status: "draft" | "published" | "paused" | "archived";
  visibility?: "public" | "private";
  auth_enabled: boolean;
  auth_providers: PublishedRuntimeAuthProvider[];
  auth_template_key?: string;
  published_url?: string | null;
  has_custom_ui?: boolean;
  published_revision_id?: string | null;
  ui_runtime_mode?: "legacy_template" | "custom_bundle";
}

export interface PublishedRuntimeDescriptor {
  app_id: string;
  public_id: string;
  revision_id: string;
  runtime_mode: string;
  published_url?: string | null;
  asset_base_url?: string | null;
  api_base_path: string;
}

export interface PreviewRuntimeDescriptor {
  app_id: string;
  public_id: string;
  revision_id: string;
  runtime_mode: string;
  preview_url: string;
  asset_base_url: string;
  api_base_path: string;
}

export interface PublishedRuntimeUser {
  id: string;
  email: string;
  full_name?: string;
  avatar?: string;
}

export interface PublicAuthResponse {
  token: string;
  token_type: "bearer";
  user: PublishedRuntimeUser;
}

export interface PublicChatItem {
  id: string;
  title?: string;
  created_at: string;
  updated_at: string;
}

export interface PublicChatHistory {
  id: string;
  title?: string;
  messages: Array<{
    role: string;
    content: string;
    created_at?: string;
  }>;
  created_at: string;
  updated_at: string;
}

interface RuntimeRequestOptions {
  method?: string;
  body?: unknown;
  token?: string;
}

async function runtimeRequest<T>(path: string, options: RuntimeRequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.token) headers.Authorization = `Bearer ${options.token}`;

  const response = await fetch(`${BASE_URL}${path}`, {
    method: options.method || "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    credentials: "omit",
    cache: "no-store",
  });

  if (!response.ok) {
    let message = "Request failed";
    try {
      const data = await response.json();
      message = data.detail || data.message || message;
    } catch {
      message = response.statusText || message;
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const publishedRuntimeService = {
  async resolveByHost(host: string) {
    return runtimeRequest<{ app: PublishedRuntimeConfig }>(`/public/apps/resolve?host=${encodeURIComponent(host)}`);
  },

  async getConfig(appPublicId: string): Promise<PublishedRuntimeConfig> {
    return runtimeRequest<PublishedRuntimeConfig>(`/public/apps/${encodeURIComponent(appPublicId)}/config`);
  },

  async getRuntime(appPublicId: string): Promise<PublishedRuntimeDescriptor> {
    return runtimeRequest<PublishedRuntimeDescriptor>(`/public/apps/${encodeURIComponent(appPublicId)}/runtime`);
  },

  async getPreviewRuntime(revisionId: string): Promise<PreviewRuntimeDescriptor> {
    return runtimeRequest<PreviewRuntimeDescriptor>(
      `/public/apps/preview/revisions/${encodeURIComponent(revisionId)}/runtime`
    );
  },

  async signup(appPublicId: string, payload: { email: string; password: string; full_name?: string }): Promise<PublicAuthResponse> {
    return runtimeRequest<PublicAuthResponse>(`/public/external/apps/${encodeURIComponent(appPublicId)}/auth/signup`, {
      method: "POST",
      body: payload,
    });
  },

  async login(appPublicId: string, payload: { email: string; password: string }): Promise<PublicAuthResponse> {
    return runtimeRequest<PublicAuthResponse>(`/public/external/apps/${encodeURIComponent(appPublicId)}/auth/login`, {
      method: "POST",
      body: payload,
    });
  },

  async exchange(appPublicId: string, payload: { token: string }): Promise<PublicAuthResponse> {
    return runtimeRequest<PublicAuthResponse>(`/public/external/apps/${encodeURIComponent(appPublicId)}/auth/exchange`, {
      method: "POST",
      body: payload,
    });
  },

  async getMe(appPublicId: string, token: string): Promise<PublishedRuntimeUser> {
    return runtimeRequest<PublishedRuntimeUser>(`/public/external/apps/${encodeURIComponent(appPublicId)}/auth/me`, {
      token,
    });
  },

  async logout(appPublicId: string, token: string): Promise<{ status: string }> {
    return runtimeRequest<{ status: string }>(`/public/external/apps/${encodeURIComponent(appPublicId)}/auth/logout`, {
      method: "POST",
      token,
    });
  },

  async listChats(appPublicId: string, token: string): Promise<{ items: PublicChatItem[] }> {
    return runtimeRequest<{ items: PublicChatItem[] }>(`/public/external/apps/${encodeURIComponent(appPublicId)}/threads`, {
      token,
    });
  },

  async getChat(appPublicId: string, chatId: string, token: string): Promise<PublicChatHistory> {
    return runtimeRequest<PublicChatHistory>(
      `/public/external/apps/${encodeURIComponent(appPublicId)}/threads/${encodeURIComponent(chatId)}`,
      { token }
    );
  },

  async streamChat(
    appPublicId: string,
    payload: { input?: string; messages?: Array<Record<string, unknown>>; thread_id?: string; context?: Record<string, unknown> },
    token?: string,
  ): Promise<Response> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(`${BASE_URL}/public/external/apps/${encodeURIComponent(appPublicId)}/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      credentials: "omit",
      cache: "no-store",
    });
    if (!response.ok) {
      let message = "Failed to stream chat";
      try {
        const data = await response.json();
        message = data.detail || data.message || message;
      } catch {
        message = response.statusText || message;
      }
      throw new Error(message);
    }
    return response;
  },
};
