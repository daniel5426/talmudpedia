import { useAuthStore } from "@/lib/store/useAuthStore";

class HttpClient {
  constructor(private baseUrl: string) {}

  buildHeaders(headers?: HeadersInit, body?: BodyInit | null): HeadersInit {
    const token = useAuthStore.getState().token;
    const nextHeaders: Record<string, string> = {};

    if (headers) {
      Object.entries(headers).forEach(([key, value]) => {
        if (value !== undefined) nextHeaders[key] = String(value);
      });
    }

    const isFormData = body instanceof FormData;
    if (body && !isFormData && !nextHeaders["Content-Type"]) {
      nextHeaders["Content-Type"] = "application/json";
    }

    if (token) {
      nextHeaders["Authorization"] = `Bearer ${token}`;
    }

    return nextHeaders;
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = this.buildHeaders(init.headers, init.body ?? null);
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, { ...init, headers });

    if (!response.ok) {
      if (response.status === 401) {
        useAuthStore.getState().logout();
      }
      let message = "Request failed";
      try {
        const data = await response.json();
        message = data.detail || data.message || message;
      } catch {
        message = response.statusText || message;
      }
      throw new Error(message);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  get<T>(path: string, init?: RequestInit) {
    return this.request<T>(path, { ...init, method: "GET" });
  }

  post<T>(path: string, body?: any, init?: RequestInit) {
    const preparedBody =
      body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined;
    return this.request<T>(path, { ...init, method: "POST", body: preparedBody });
  }

  patch<T>(path: string, body?: any, init?: RequestInit) {
    const preparedBody =
      body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined;
    return this.request<T>(path, { ...init, method: "PATCH", body: preparedBody });
  }

  delete<T>(path: string, init?: RequestInit) {
    return this.request<T>(path, { ...init, method: "DELETE" });
  }

  async requestRaw(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = this.buildHeaders(init.headers, init.body ?? null);
    const url = `${this.baseUrl}${path}`;
    return fetch(url, { ...init, headers });
  }
}

export const httpClient = new HttpClient(process.env.NEXT_PUBLIC_BACKEND_URL || "/api/py");
