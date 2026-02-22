import {
  createRuntimeClient as createSdkRuntimeClient,
  fetchRuntimeBootstrap,
  type NormalizedRuntimeEvent,
  type RuntimeBootstrap,
  type RuntimeInput,
} from "@talmudpedia/runtime-sdk";

import runtimeConfig from "./runtime-config.json";

export type { RuntimeInput };

export type RuntimeEvent = {
  type: string;
  event?: string;
  data?: Record<string, unknown>;
  payload?: Record<string, unknown>;
  content?: string;
};

type QueryRuntimeContext = {
  mode?: "builder-preview" | "published-runtime";
  basePath?: string;
  bootstrapUrl?: string;
  token?: string | null;
  previewToken?: string | null;
};

type RuntimeConfig = {
  app_id?: string;
  app_slug?: string;
  agent_id?: string;
  api_base_url?: string;
  bootstrap_path?: string;
};

const TOKEN_PREFIX = "published-app-auth-token";
const config = (runtimeConfig || {}) as RuntimeConfig;

let bootstrapPromise: Promise<RuntimeBootstrap> | null = null;

function toLegacyEvent(event: NormalizedRuntimeEvent): RuntimeEvent {
  return {
    type: event.type,
    event: event.event,
    data: event.data,
    payload: event.payload,
    content: event.content,
  };
}

function readQueryContext(): QueryRuntimeContext {
  if (typeof window === "undefined") return {};
  const params = new URLSearchParams(window.location.search);
  const mode = params.get("runtime_mode");
  const basePath = params.get("runtime_base_path");
  const bootstrapUrl = params.get("runtime_bootstrap_url");
  const token = params.get("runtime_token");
  const previewToken = params.get("runtime_preview_token") || params.get("preview_token");
  return {
    mode: mode === "builder-preview" || mode === "published-runtime" ? mode : undefined,
    basePath: basePath || undefined,
    bootstrapUrl: bootstrapUrl || undefined,
    token: token || null,
    previewToken: previewToken || null,
  };
}

function normalizeApiBaseUrl(value?: string): string {
  const raw = String(value || "").trim() || "/api/py";
  return raw.endsWith("/") ? raw.slice(0, -1) : raw;
}

function buildBootstrapFromBasePath(ctx: QueryRuntimeContext, basePath: string): RuntimeBootstrap {
  const normalizedBase = basePath.endsWith("/") ? basePath.slice(0, -1) : basePath;
  let streamUrl = `${normalizedBase}/chat/stream`;
  if (ctx.previewToken && normalizedBase.includes("/preview/revisions/")) {
    const connector = streamUrl.includes("?") ? "&" : "?";
    streamUrl = `${streamUrl}${connector}preview_token=${encodeURIComponent(ctx.previewToken)}`;
  }

  return {
    version: "runtime-bootstrap.v1",
    app_id: String(config.app_id || ""),
    slug: String(config.app_slug || ""),
    mode: ctx.mode || "published-runtime",
    api_base_path: normalizeApiBaseUrl(config.api_base_url),
    api_base_url: normalizeApiBaseUrl(config.api_base_url),
    chat_stream_path: `${normalizedBase}/chat/stream`,
    chat_stream_url: streamUrl,
    auth: {
      enabled: true,
      providers: ["password"],
      exchange_enabled: false,
    },
    preview_token: ctx.previewToken || null,
  };
}

function readInlineBootstrap(): RuntimeBootstrap | null {
  if (typeof window === "undefined") return null;
  const payload = (window as Window & { __APP_RUNTIME_CONTEXT?: unknown }).__APP_RUNTIME_CONTEXT;
  if (!payload || typeof payload !== "object") return null;
  const context = payload as Partial<RuntimeBootstrap>;
  if (!context.chat_stream_path && !context.chat_stream_url) return null;
  if (!context.version || !context.mode) return null;
  return context as RuntimeBootstrap;
}

async function fetchBootstrapFromConfig(ctx: QueryRuntimeContext): Promise<RuntimeBootstrap> {
  if (ctx.bootstrapUrl) {
    const response = await fetch(ctx.bootstrapUrl, {
      headers: ctx.previewToken ? { Authorization: `Bearer ${ctx.previewToken}` } : undefined,
    });
    if (!response.ok) {
      throw new Error("Failed to fetch runtime bootstrap.");
    }
    return (await response.json()) as RuntimeBootstrap;
  }

  const bootstrapPath = String(config.bootstrap_path || "").trim();
  if (bootstrapPath) {
    const apiBaseUrl = normalizeApiBaseUrl(config.api_base_url);
    const url = `${apiBaseUrl}${bootstrapPath.startsWith("/") ? bootstrapPath : `/${bootstrapPath}`}`;
    const response = await fetch(url, {
      headers: ctx.previewToken ? { Authorization: `Bearer ${ctx.previewToken}` } : undefined,
    });
    if (!response.ok) {
      throw new Error("Failed to fetch runtime bootstrap.");
    }
    return (await response.json()) as RuntimeBootstrap;
  }

  const appSlug = String(config.app_slug || "").trim();
  if (!appSlug) {
    throw new Error("Runtime bootstrap is missing app slug config.");
  }

  return fetchRuntimeBootstrap({
    apiBaseUrl: normalizeApiBaseUrl(config.api_base_url),
    appSlug,
    previewToken: ctx.previewToken || undefined,
  });
}

async function resolveBootstrap(basePath?: string): Promise<RuntimeBootstrap> {
  const query = readQueryContext();
  if (basePath) {
    return buildBootstrapFromBasePath(query, basePath);
  }

  if (query.basePath) {
    return buildBootstrapFromBasePath(query, query.basePath);
  }

  const inline = readInlineBootstrap();
  if (inline) {
    return inline;
  }

  if (!bootstrapPromise) {
    bootstrapPromise = fetchBootstrapFromConfig(query);
  }
  return bootstrapPromise;
}

function resolveTokenProvider() {
  const query = readQueryContext();
  const explicitToken = query.token;
  const explicitPreviewToken = query.previewToken;

  return async () => {
    if (explicitToken) return explicitToken;
    if (explicitPreviewToken) return null;
    if (typeof window === "undefined") return null;
    const appSlug = String(config.app_slug || "").trim();
    if (!appSlug) return null;
    return window.localStorage.getItem(`${TOKEN_PREFIX}:${appSlug}`);
  };
}

export const createRuntimeClient = (basePath?: string) => {
  return {
    async stream(
      input: RuntimeInput,
      onEvent: (event: RuntimeEvent) => void,
    ): Promise<{ chatId: string | null }> {
      const bootstrap = await resolveBootstrap(basePath);
      const runtimeClient = createSdkRuntimeClient({
        apiBaseUrl: normalizeApiBaseUrl(config.api_base_url),
        bootstrap,
        tokenProvider: resolveTokenProvider(),
      });

      return runtimeClient.stream(input, (event) => {
        onEvent(toLegacyEvent(event));
      });
    },
  };
};
