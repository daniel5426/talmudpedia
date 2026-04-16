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

export class HttpRequestTimeoutError extends Error {
  constructor(
    message: string,
    public readonly timeoutMs: number,
  ) {
    super(message);
    this.name = "HttpRequestTimeoutError";
  }
}

type HttpRequestInit = RequestInit & {
  clearSessionOn401?: boolean;
  timeoutMs?: number;
};

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

    return nextHeaders;
  }

  async request<T>(path: string, init: HttpRequestInit = {}): Promise<T> {
    const headers = this.buildHeaders(init.headers, init.body ?? null);
    const url = `${this.baseUrl}${path}`;
    const { clearSessionOn401, timeoutMs, signal, ...requestInit } = init;
    const controller = timeoutMs ? new AbortController() : null;
    let didTimeout = false;
    const timeoutId =
      controller && timeoutMs
        ? globalThis.setTimeout(() => {
            didTimeout = true;
            controller.abort(`Request timed out after ${timeoutMs}ms`);
          }, timeoutMs)
        : null;

    if (signal && controller) {
      if (signal.aborted) {
        controller.abort(signal.reason);
      } else {
        signal.addEventListener("abort", () => controller.abort(signal.reason), { once: true });
      }
    }

    try {
      const response = await fetch(url, {
        ...requestInit,
        headers,
        credentials: "include",
        signal: controller?.signal ?? signal,
      });

      if (!response.ok) {
        if (response.status === 401 && clearSessionOn401) {
          useAuthStore.getState().clearSession();
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
        throw new HttpRequestError(
          errorMsg,
          response.status,
          parsedErrorPayload ?? { message: errorMsg },
        );
      }

      if (response.status === 204) {
        return undefined as T;
      }
      return response.json();
    } catch (error) {
      if (didTimeout) {
        throw new HttpRequestTimeoutError(
          `Request timed out for ${url} after ${timeoutMs}ms`,
          timeoutMs ?? 0,
        );
      }
      const errorMessage = error instanceof Error ? error.message : String(error || "");
      if (!this.shouldSuppressErrorLogging(errorMessage)) {
        console.error(`[HttpClient] Request failed for ${url}:`, error);
      }
      throw error;
    } finally {
      if (timeoutId !== null) {
        globalThis.clearTimeout(timeoutId);
      }
    }
  }

  get<T>(path: string, init?: HttpRequestInit) {
    return this.request<T>(path, { ...init, method: "GET" });
  }

  post<T>(path: string, body?: any, init?: HttpRequestInit) {
    const preparedBody =
      body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined;
    return this.request<T>(path, { ...init, method: "POST", body: preparedBody });
  }

  put<T>(path: string, body?: any, init?: HttpRequestInit) {
    const preparedBody =
      body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined;
    return this.request<T>(path, { ...init, method: "PUT", body: preparedBody });
  }

  patch<T>(path: string, body?: any, init?: HttpRequestInit) {
    const preparedBody =
      body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined;
    return this.request<T>(path, { ...init, method: "PATCH", body: preparedBody });
  }

  delete<T>(path: string, init?: HttpRequestInit) {
    return this.request<T>(path, { ...init, method: "DELETE" });
  }

  async requestRaw(path: string, init: HttpRequestInit = {}): Promise<Response> {
    const headers = this.buildHeaders(init.headers, init.body ?? null);
    const url = `${this.baseUrl}${path}`;
    return fetch(url, { ...init, headers, credentials: "include" });
  }
}

export const httpClient = new HttpClient(process.env.NEXT_PUBLIC_BACKEND_URL || "/api/py");
