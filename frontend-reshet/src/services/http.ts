import { useAuthStore } from "@/lib/store/useAuthStore";

class HttpClient {
  constructor(public readonly baseUrl: string) {}

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
    
    console.log(`[HttpClient] Request: ${init.method || 'GET'} ${url}`, {
      headers,
      body: init.body ? (typeof init.body === 'string' ? JSON.parse(init.body) : 'FormData/Binary') : null
    });

    try {
      const response = await fetch(url, { ...init, headers });
      
      console.log(`[HttpClient] Response: ${response.status} ${response.statusText} for ${url}`);

      if (!response.ok) {
        if (response.status === 401) {
          useAuthStore.getState().logout();
        }
        let message: any = "Request failed";
        try {
          const data = await response.json();
          console.error(`[HttpClient] Error Data for ${url}:`, data);
          message = data.detail || data.message || message;
        } catch {
          message = response.statusText || message;
        }
        const errorMsg = typeof message === 'object' ? JSON.stringify(message) : String(message);
        throw new Error(errorMsg);
      }

      if (response.status === 204) {
        return undefined as T;
      }

      const result = await response.json();
      console.log(`[HttpClient] Result for ${url}:`, result);
      return result;
    } catch (error) {
      console.error(`[HttpClient] Fetch Error for ${url}:`, error);
      throw error;
    }
  }

  get<T>(path: string, init?: RequestInit) {
    return this.request<T>(path, { ...init, method: "GET" });
  }

  post<T>(path: string, body?: any, init?: RequestInit) {
    const preparedBody =
      body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined;
    return this.request<T>(path, { ...init, method: "POST", body: preparedBody });
  }

  put<T>(path: string, body?: any, init?: RequestInit) {
    const preparedBody =
      body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined;
    return this.request<T>(path, { ...init, method: "PUT", body: preparedBody });
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
