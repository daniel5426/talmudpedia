import { normalizeRuntimeEvent } from "./events";
import { parseSseStream } from "./sse";
import type {
  NormalizedRuntimeEvent,
  RuntimeBootstrap,
  RuntimeClientOptions,
  RuntimeInput,
  RuntimeStreamResult,
} from "./types";

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function resolveChatStreamUrl(bootstrap: RuntimeBootstrap, apiBaseUrl?: string): string {
  if (bootstrap.chat_stream_url) {
    return bootstrap.chat_stream_url;
  }

  if (!apiBaseUrl) {
    throw new Error("Runtime SDK requires chat_stream_url or apiBaseUrl + chat_stream_path.");
  }

  const normalizedBase = trimTrailingSlash(apiBaseUrl);
  const path = bootstrap.chat_stream_path.startsWith("/")
    ? bootstrap.chat_stream_path
    : `/${bootstrap.chat_stream_path}`;
  return `${normalizedBase}${path}`;
}

async function resolveToken(options: RuntimeClientOptions): Promise<string | null> {
  const provider = options.tokenProvider;
  if (!provider) return null;
  const value = await provider();
  if (!value) return null;
  const token = String(value).trim();
  return token || null;
}

export function createRuntimeClient(options: RuntimeClientOptions) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    throw new Error("Runtime SDK requires fetch implementation.");
  }

  const bootstrap = options.bootstrap;
  if (!bootstrap) {
    throw new Error("Runtime SDK requires bootstrap configuration.");
  }

  const streamUrl = resolveChatStreamUrl(bootstrap, options.apiBaseUrl || bootstrap.api_base_url);

  return {
    async stream(
      input: RuntimeInput,
      onEvent: (event: NormalizedRuntimeEvent) => void,
    ): Promise<RuntimeStreamResult> {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      const token = await resolveToken(options);
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetchImpl(streamUrl, {
        method: "POST",
        headers,
        body: JSON.stringify(input || {}),
      });

      if (!response.ok) {
        let message = "Failed to stream runtime response";
        try {
          const data = (await response.json()) as { detail?: string; message?: string };
          message = String(data.detail || data.message || message);
        } catch {
          message = response.statusText || message;
        }
        throw new Error(message);
      }

      const reader = response.body;
      if (!reader) {
        throw new Error("Streaming reader unavailable");
      }

      await parseSseStream(reader, (rawEvent) => {
        onEvent(normalizeRuntimeEvent(rawEvent));
      });

      return { chatId: response.headers.get("X-Chat-ID") };
    },
  };
}
