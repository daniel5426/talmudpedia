import { EmbeddedAgentSDKError } from "./errors";

const SERVER_ONLY_MESSAGE =
  "EmbeddedAgentClient is server-only. Keep your Talmudpedia API key on your backend and call the SDK from Node.";

export function assertServerRuntime(): void {
  if (typeof window !== "undefined" && typeof document !== "undefined") {
    throw new EmbeddedAgentSDKError(SERVER_ONLY_MESSAGE, { kind: "protocol" });
  }
}

export function normalizeBaseUrl(baseUrl: string): string {
  const normalized = String(baseUrl || "").trim().replace(/\/+$/, "");
  if (!normalized) {
    throw new EmbeddedAgentSDKError("EmbeddedAgentClient requires a non-empty baseUrl.", {
      kind: "protocol",
    });
  }
  try {
    return new URL(normalized).toString().replace(/\/+$/, "");
  } catch (cause) {
    throw new EmbeddedAgentSDKError("EmbeddedAgentClient received an invalid baseUrl.", {
      kind: "protocol",
      cause,
      details: { baseUrl },
    });
  }
}

export function resolveFetchImpl(fetchImpl?: typeof fetch): typeof fetch {
  if (fetchImpl) {
    return fetchImpl;
  }
  if (typeof fetch === "function") {
    return fetch;
  }
  throw new EmbeddedAgentSDKError(
    "No fetch implementation is available. Use Node 18.17+ or pass fetchImpl explicitly.",
    { kind: "protocol" },
  );
}

export function buildStreamHeaders(apiKey: string): HeadersInit {
  return {
    Authorization: `Bearer ${apiKey}`,
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  };
}

export function buildJsonHeaders(apiKey: string): HeadersInit {
  return {
    Authorization: `Bearer ${apiKey}`,
    Accept: "application/json",
  };
}

function extractMessageFromDetails(details: unknown): string | undefined {
  if (!details || typeof details !== "object" || Array.isArray(details)) {
    return undefined;
  }
  const detail = (details as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.trim() ? detail.trim() : undefined;
}

async function parseErrorDetails(response: Response): Promise<unknown> {
  if (typeof response.text === "function") {
    try {
      const raw = await response.text();
      if (!raw) {
        return null;
      }
      try {
        return JSON.parse(raw) as unknown;
      } catch {
        return raw;
      }
    } catch {
      return null;
    }
  }
  if (typeof response.json === "function") {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }
  return null;
}

export async function assertOk(response: Response): Promise<void> {
  if (response.ok) {
    return;
  }
  const details = await parseErrorDetails(response);
  const message =
    extractMessageFromDetails(details) ||
    (typeof details === "string" && details.trim()) ||
    response.statusText ||
    "Request failed";
  throw new EmbeddedAgentSDKError(message, {
    kind: "http",
    status: response.status,
    details,
  });
}

export function wrapNetworkError(message: string, cause: unknown): EmbeddedAgentSDKError {
  if (cause instanceof EmbeddedAgentSDKError) {
    return cause;
  }
  return new EmbeddedAgentSDKError(message, {
    kind: "network",
    cause,
    details: cause instanceof Error ? { name: cause.name } : undefined,
  });
}
