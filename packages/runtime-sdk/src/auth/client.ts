import type { RuntimeTokenStore } from "./storage";

type AuthUser = {
  id: string;
  email: string;
  full_name?: string;
  avatar?: string;
};

type PublicAuthResponse = {
  token: string;
  token_type: "bearer";
  user: AuthUser;
};

type PublishedAppThreadSummary = {
  id: string;
  title: string | null;
  status: string;
  surface: string;
  last_run_id?: string | null;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
};

type PublishedAppThreadDetail = PublishedAppThreadSummary & {
  turns: Array<{
    id: string;
    run_id: string;
    turn_index: number;
    status: string;
    user_input_text?: string | null;
    assistant_output_text?: string | null;
    usage_tokens: number;
    created_at: string;
    completed_at?: string | null;
    metadata?: Record<string, unknown> | null;
  }>;
};

type PublishedAppThreadListResponse = {
  items: PublishedAppThreadSummary[];
  total: number;
  page: number;
  pages: number;
};

type AuthClientOptions = {
  apiBaseUrl?: string;
  appSlug: string;
  fetchImpl?: typeof fetch;
  tokenStore?: RuntimeTokenStore;
};

type ExchangeRequest = {
  token: string;
};

type PasswordSignupRequest = {
  email: string;
  password: string;
  full_name?: string;
};

type PasswordLoginRequest = {
  email: string;
  password: string;
};

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

async function parseError(response: Response, fallback: string): Promise<never> {
  let message = fallback;
  try {
    const data = (await response.json()) as { detail?: string; message?: string };
    message = String(data.detail || data.message || message);
  } catch {
    message = response.statusText || message;
  }
  throw new Error(message);
}

export function createPublishedAppAuthClient(options: AuthClientOptions) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    throw new Error("Runtime SDK requires fetch implementation.");
  }

  const base = trimTrailingSlash(options.apiBaseUrl || "/api/py");
  const slug = encodeURIComponent(options.appSlug);

  const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
    const response = await fetchImpl(`${base}${path}`, init);
    if (!response.ok) {
      await parseError(response, "Published auth request failed");
    }
    return (await response.json()) as T;
  };

  const persistToken = (payload: PublicAuthResponse): PublicAuthResponse => {
    options.tokenStore?.set(payload.token);
    return payload;
  };

  const requireBearer = (token?: string): string => {
    const bearer = token || options.tokenStore?.get();
    if (!bearer) {
      throw new Error("No auth token is available.");
    }
    return bearer;
  };

  return {
    async signup(payload: PasswordSignupRequest): Promise<PublicAuthResponse> {
      return persistToken(
        await request<PublicAuthResponse>(`/public/external/apps/${slug}/auth/signup`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
      );
    },

    async login(payload: PasswordLoginRequest): Promise<PublicAuthResponse> {
      return persistToken(
        await request<PublicAuthResponse>(`/public/external/apps/${slug}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
      );
    },

    async exchange(payload: ExchangeRequest): Promise<PublicAuthResponse> {
      return persistToken(
        await request<PublicAuthResponse>(`/public/external/apps/${slug}/auth/exchange`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
      );
    },

    async me(token?: string): Promise<AuthUser> {
      return request<AuthUser>(`/public/external/apps/${slug}/auth/me`, {
        headers: { Authorization: `Bearer ${requireBearer(token)}` },
      });
    },

    async listThreads(params?: { skip?: number; limit?: number; token?: string }): Promise<PublishedAppThreadListResponse> {
      const query = new URLSearchParams();
      if (typeof params?.skip === "number") query.set("skip", String(params.skip));
      if (typeof params?.limit === "number") query.set("limit", String(params.limit));
      const suffix = query.toString() ? `?${query.toString()}` : "";
      return request<PublishedAppThreadListResponse>(`/public/external/apps/${slug}/threads${suffix}`, {
        headers: { Authorization: `Bearer ${requireBearer(params?.token)}` },
      });
    },

    async getThread(threadId: string, token?: string): Promise<PublishedAppThreadDetail> {
      return request<PublishedAppThreadDetail>(`/public/external/apps/${slug}/threads/${encodeURIComponent(threadId)}`, {
        headers: { Authorization: `Bearer ${requireBearer(token)}` },
      });
    },

    async logout(token?: string): Promise<{ status: string }> {
      const payload = await request<{ status: string }>(`/public/external/apps/${slug}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${requireBearer(token)}` },
      });
      options.tokenStore?.clear();
      return payload;
    },
  };
}

export type {
  AuthClientOptions,
  AuthUser,
  PublicAuthResponse,
  PublishedAppThreadSummary,
  PublishedAppThreadDetail,
  PublishedAppThreadListResponse,
  ExchangeRequest,
  PasswordSignupRequest,
  PasswordLoginRequest,
};
