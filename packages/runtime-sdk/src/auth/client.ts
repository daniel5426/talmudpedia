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

  return {
    async signup(payload: PasswordSignupRequest): Promise<PublicAuthResponse> {
      return persistToken(
        await request<PublicAuthResponse>(`/public/apps/${slug}/auth/signup`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
      );
    },

    async login(payload: PasswordLoginRequest): Promise<PublicAuthResponse> {
      return persistToken(
        await request<PublicAuthResponse>(`/public/apps/${slug}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
      );
    },

    async exchange(payload: ExchangeRequest): Promise<PublicAuthResponse> {
      return persistToken(
        await request<PublicAuthResponse>(`/public/apps/${slug}/auth/exchange`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
      );
    },

    async me(token?: string): Promise<AuthUser> {
      const bearer = token || options.tokenStore?.get();
      if (!bearer) {
        throw new Error("No auth token is available.");
      }
      return request<AuthUser>(`/public/apps/${slug}/auth/me`, {
        headers: { Authorization: `Bearer ${bearer}` },
      });
    },

    async logout(token?: string): Promise<{ status: string }> {
      const bearer = token || options.tokenStore?.get();
      if (!bearer) {
        throw new Error("No auth token is available.");
      }
      const payload = await request<{ status: string }>(`/public/apps/${slug}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${bearer}` },
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
  ExchangeRequest,
  PasswordSignupRequest,
  PasswordLoginRequest,
};
