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
};

type RuntimeConfig = {
  app_id?: string;
  app_slug?: string;
  agent_id?: string;
  api_base_url?: string;
  bootstrap_path?: string;
};

const TOKEN_PREFIX = "published-app-auth-token";
const PREVIEW_AUTH_MESSAGE_TYPE = "talmudpedia.preview-auth.v1";
const config = (runtimeConfig || {}) as RuntimeConfig;

let bootstrapPromise: Promise<RuntimeBootstrap> | null = null;
let previewAuthToken: string | null = null;
let isPreviewAuthChannelBound = false;

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
  return {
    mode: mode === "builder-preview" || mode === "published-runtime" ? mode : undefined,
    basePath: basePath || undefined,
    bootstrapUrl: bootstrapUrl || undefined,
    token: token || null,
  };
}

function bindPreviewAuthChannel(): void {
  if (typeof window === "undefined" || isPreviewAuthChannelBound) return;
  isPreviewAuthChannelBound = true;
  window.addEventListener("message", (event: MessageEvent<unknown>) => {
    const data = event.data;
    if (!data || typeof data !== "object") return;
    const payload = data as Record<string, unknown>;
    if (payload.type !== PREVIEW_AUTH_MESSAGE_TYPE) return;
    const token = String(payload.token || "").trim();
    previewAuthToken = token || null;
  });
}

function normalizeApiBaseUrl(value?: string): string {
  const raw = String(value || "").trim() || "/api/py";
  return raw.endsWith("/") ? raw.slice(0, -1) : raw;
}

function buildBootstrapFromBasePath(ctx: QueryRuntimeContext, basePath: string): RuntimeBootstrap {
  const normalizedBase = basePath.endsWith("/") ? basePath.slice(0, -1) : basePath;
  return {
    version: "runtime-bootstrap.v1",
    app_id: String(config.app_id || ""),
    slug: String(config.app_slug || ""),
    mode: ctx.mode || "published-runtime",
    api_base_path: normalizeApiBaseUrl(config.api_base_url),
    api_base_url: normalizeApiBaseUrl(config.api_base_url),
    chat_stream_path: `${normalizedBase}/chat/stream`,
    chat_stream_url: `${normalizedBase}/chat/stream`,
    auth: {
      enabled: true,
      providers: ["password"],
      exchange_enabled: false,
    },
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
  const previewHeaders = previewAuthToken ? { Authorization: `Bearer ${previewAuthToken}` } : undefined;
  if (ctx.bootstrapUrl) {
    const response = await fetch(ctx.bootstrapUrl, { headers: previewHeaders });
    if (!response.ok) {
      throw new Error("Failed to fetch runtime bootstrap.");
    }
    return (await response.json()) as RuntimeBootstrap;
  }

  const bootstrapPath = String(config.bootstrap_path || "").trim();
  if (bootstrapPath) {
    const apiBaseUrl = normalizeApiBaseUrl(config.api_base_url);
    const url = `${apiBaseUrl}${bootstrapPath.startsWith("/") ? bootstrapPath : `/${bootstrapPath}`}`;
    const response = await fetch(url, { headers: previewHeaders });
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
    previewToken: previewAuthToken || undefined,
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

function resolveTokenProvider(basePath?: string) {
  const query = readQueryContext();
  const explicitToken = query.token;
  const resolvedBasePath = basePath || query.basePath || "";
  const isPreviewMode =
    query.mode === "builder-preview" ||
    resolvedBasePath.includes("/public/apps/preview/revisions/");

  return async () => {
    bindPreviewAuthChannel();
    if (explicitToken) return explicitToken;
    if (isPreviewMode) return previewAuthToken;
    if (typeof window === "undefined") return null;
    const appSlug = String(config.app_slug || "").trim();
    if (!appSlug) return null;
    return window.localStorage.getItem(`${TOKEN_PREFIX}:${appSlug}`);
  };
}

export const createRuntimeClient = (basePath?: string) => {
  bindPreviewAuthChannel();
  return {
    async stream(
      input: RuntimeInput,
      onEvent: (event: RuntimeEvent) => void,
    ): Promise<{ chatId: string | null }> {
      const bootstrap = await resolveBootstrap(basePath);
      const runtimeClient = createSdkRuntimeClient({
        apiBaseUrl: normalizeApiBaseUrl(config.api_base_url),
        bootstrap,
        tokenProvider: resolveTokenProvider(basePath),
      });

      return runtimeClient.stream(input, (event) => {
        onEvent(toLegacyEvent(event));
      });
    },
  };
};
