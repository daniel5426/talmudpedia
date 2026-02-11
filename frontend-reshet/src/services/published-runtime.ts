const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "/api/py";

export type PublishedRuntimeAuthProvider = "password" | "google";

export interface PublishedRuntimeConfig {
  id: string;
  tenant_id: string;
  agent_id: string;
  name: string;
  slug: string;
  status: "draft" | "published" | "paused" | "archived";
  auth_enabled: boolean;
  auth_providers: PublishedRuntimeAuthProvider[];
  published_url?: string | null;
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
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method: options.method || "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
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

  async getConfig(appSlug: string): Promise<PublishedRuntimeConfig> {
    return runtimeRequest<PublishedRuntimeConfig>(`/public/apps/${encodeURIComponent(appSlug)}/config`);
  },

  async signup(appSlug: string, payload: { email: string; password: string; full_name?: string }): Promise<PublicAuthResponse> {
    return runtimeRequest<PublicAuthResponse>(`/public/apps/${encodeURIComponent(appSlug)}/auth/signup`, {
      method: "POST",
      body: payload,
    });
  },

  async login(appSlug: string, payload: { email: string; password: string }): Promise<PublicAuthResponse> {
    return runtimeRequest<PublicAuthResponse>(`/public/apps/${encodeURIComponent(appSlug)}/auth/login`, {
      method: "POST",
      body: payload,
    });
  },

  getGoogleStartUrl(appSlug: string, returnTo: string): string {
    return `${BASE_URL}/public/apps/${encodeURIComponent(appSlug)}/auth/google/start?return_to=${encodeURIComponent(returnTo)}`;
  },

  async getMe(appSlug: string, token: string): Promise<PublishedRuntimeUser> {
    return runtimeRequest<PublishedRuntimeUser>(`/public/apps/${encodeURIComponent(appSlug)}/auth/me`, {
      token,
    });
  },

  async logout(appSlug: string, token: string): Promise<{ status: string }> {
    return runtimeRequest<{ status: string }>(`/public/apps/${encodeURIComponent(appSlug)}/auth/logout`, {
      method: "POST",
      token,
    });
  },

  async listChats(appSlug: string, token: string): Promise<{ items: PublicChatItem[] }> {
    return runtimeRequest<{ items: PublicChatItem[] }>(`/public/apps/${encodeURIComponent(appSlug)}/chats`, {
      token,
    });
  },

  async getChat(appSlug: string, chatId: string, token: string): Promise<PublicChatHistory> {
    return runtimeRequest<PublicChatHistory>(`/public/apps/${encodeURIComponent(appSlug)}/chats/${encodeURIComponent(chatId)}`, {
      token,
    });
  },

  async streamChat(
    appSlug: string,
    payload: { input?: string; messages?: Array<Record<string, unknown>>; chat_id?: string; context?: Record<string, unknown> },
    token?: string,
  ): Promise<Response> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    const response = await fetch(`${BASE_URL}/public/apps/${encodeURIComponent(appSlug)}/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
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
