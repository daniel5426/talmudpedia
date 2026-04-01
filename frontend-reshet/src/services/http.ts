import { useAuthStore } from "@/lib/store/useAuthStore";

export class HttpRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(message);
    this.name = "HttpRequestError";
  }
}

export function getHttpErrorDetail(error: unknown): any | null {
  if (error instanceof HttpRequestError) {
    return error.detail;
  }
  if (!(error instanceof Error)) {
    return null;
  }
  try {
    return JSON.parse(error.message);
  } catch {
    return null;
  }
}

export function formatHttpErrorMessage(error: unknown, fallback = "Request failed"): string {
  const detail = getHttpErrorDetail(error);
  if (detail && typeof detail === "object") {
    const typedDetail = detail as { message?: unknown; errors?: unknown[] };
    if (Array.isArray(typedDetail.errors) && typedDetail.errors.length > 0) {
      const messages = typedDetail.errors
        .map((item) =>
          item && typeof item === "object" && typeof (item as { message?: unknown }).message === "string"
            ? String((item as { message: string }).message)
            : null
        )
        .filter((value): value is string => Boolean(value));
      if (messages.length > 0) {
        return messages.join(" ");
      }
    }
    if (typeof typedDetail.message === "string" && typedDetail.message.trim()) {
      return typedDetail.message;
    }
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

class HttpClient {
  constructor(public readonly baseUrl: string) {}

  private shouldSuppressErrorLogging(message: unknown): boolean {
    let normalized = "";
    if (typeof message === "string") {
      normalized = message;
    } else {
      try {
        normalized = JSON.stringify(message || "");
      } catch {
        normalized = String(message || "");
      }
    }
    return normalized.includes("PUBLISH_ACTIVE_SESSION_LOCKED");
  }

  buildHeaders(headers?: HeadersInit, body?: BodyInit | null): HeadersInit {
    const authState = useAuthStore.getState();
    const token = authState.token;
    const tenantId = authState.user?.tenant_id;
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
    if (tenantId && !nextHeaders["X-Tenant-ID"]) {
      nextHeaders["X-Tenant-ID"] = tenantId;
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
        let parsedErrorPayload: unknown = null;
        try {
          const data = await response.json();
          parsedErrorPayload = data?.detail ?? data;
          if (typeof parsedErrorPayload === "string") {
            message = parsedErrorPayload;
          } else if (parsedErrorPayload && typeof parsedErrorPayload === "object") {
            message =
              (parsedErrorPayload as { message?: unknown; detail?: unknown }).message ||
              (parsedErrorPayload as { detail?: unknown }).detail ||
              data?.message ||
              message;
          } else {
            message = data?.message || message;
          }
        } catch {
          message = response.statusText || message;
        }
        const errorMsg = typeof message === 'object' ? JSON.stringify(message) : String(message);
        if (!this.shouldSuppressErrorLogging(errorMsg)) {
          if (parsedErrorPayload !== null) {
            console.error(`[HttpClient] Error Data for ${url}:`, parsedErrorPayload);
          } else {
            console.error(`[HttpClient] Error Response for ${url}:`, errorMsg);
          }
        }
        throw new HttpRequestError(
          errorMsg,
          response.status,
          parsedErrorPayload ?? { message: errorMsg },
        );
      }

      if (response.status === 204) {
        return undefined as T;
      }

      const result = await response.json();
      console.log(`[HttpClient] Result for ${url}:`, result);
      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error || "");
      if (!this.shouldSuppressErrorLogging(errorMessage)) {
        console.error(`[HttpClient] Fetch Error for ${url}:`, error);
      }
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
