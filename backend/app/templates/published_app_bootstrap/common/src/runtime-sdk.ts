import {
  createRuntimeClient as createSdkRuntimeClient,
  fetchRuntimeBootstrap,
  type NormalizedRuntimeEvent,
  type RuntimeBootstrap,
  type RuntimeInput as SdkRuntimeInput,
} from "@talmudpedia/runtime-sdk";

import runtimeConfig from "./runtime-config.json";

export type RuntimeInput = SdkRuntimeInput & {
  attachment_ids?: string[];
};

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
  slug?: string;
  public_id?: string;
  app_public_id?: string;
  agent_id?: string;
  api_base_url?: string;
  bootstrap_path?: string;
};

const config = (runtimeConfig || {}) as RuntimeConfig;
const PREVIEW_AUTH_MESSAGE_TYPE = "talmudpedia.preview-auth.v1";

let bootstrapPromise: Promise<RuntimeBootstrap> | null = null;
let previewAuthToken: string | null = null;
let isPreviewAuthChannelBound = false;

type RuntimeBootstrapWire = Partial<RuntimeBootstrap> & {
  public_id?: string;
  app_public_id?: string;
};

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

function normalizeApiBaseUrl(value?: string): string {
  const raw = String(value || "").trim() || "/api/py";
  return raw.endsWith("/") ? raw.slice(0, -1) : raw;
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

function readConfiguredAppSlug(): string {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const querySlug =
      params.get("app_slug") ||
      params.get("public_id") ||
      params.get("app_public_id") ||
      "";
    if (querySlug.trim()) {
      return querySlug.trim();
    }
  }
  return String(config.slug || config.public_id || config.app_public_id || "").trim();
}

function normalizeBootstrap(payload: RuntimeBootstrapWire): RuntimeBootstrap {
  const streamPath =
    typeof payload.chat_stream_path === "string" && payload.chat_stream_path.trim()
      ? payload.chat_stream_path.trim()
      : typeof payload.chat_stream_url === "string" && payload.chat_stream_url.trim()
        ? new URL(
            payload.chat_stream_url,
            typeof window !== "undefined" ? window.location.origin : "http://localhost",
          ).pathname
        : "";

  return {
    version: "runtime-bootstrap.v1",
    stream_contract_version: "run-stream.v2",
    request_contract_version: "thread.v1",
    app_id: String(payload.app_id || ""),
    slug: String(payload.slug || payload.public_id || payload.app_public_id || "").trim(),
    revision_id:
      typeof payload.revision_id === "string" && payload.revision_id.trim()
        ? payload.revision_id
        : undefined,
    mode: payload.mode === "builder-preview" ? "builder-preview" : "published-runtime",
    api_base_path: String(payload.api_base_path || "/"),
    api_base_url:
      typeof payload.api_base_url === "string" && payload.api_base_url.trim()
        ? payload.api_base_url
        : undefined,
    chat_stream_path: streamPath,
    chat_stream_url:
      typeof payload.chat_stream_url === "string" && payload.chat_stream_url.trim()
        ? payload.chat_stream_url
        : undefined,
    auth: {
      enabled: Boolean(payload.auth?.enabled),
      providers: Array.isArray(payload.auth?.providers)
        ? payload.auth.providers.filter((value): value is string => typeof value === "string")
        : [],
      exchange_enabled: Boolean(payload.auth?.exchange_enabled),
    },
  };
}

function buildBootstrapFromBasePath(ctx: QueryRuntimeContext, basePath: string): RuntimeBootstrap {
  const normalizedBase = basePath.endsWith("/") ? basePath.slice(0, -1) : basePath;
  return {
    version: "runtime-bootstrap.v1",
    stream_contract_version: "run-stream.v2",
    request_contract_version: "thread.v1",
    app_id: String(config.app_id || ""),
    slug: readConfiguredAppSlug(),
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
  const context = payload as RuntimeBootstrapWire;
  if (!context.chat_stream_path && !context.chat_stream_url) return null;
  if (!context.version || !context.mode) return null;
  return normalizeBootstrap(context);
}

async function fetchBootstrapFromConfig(ctx: QueryRuntimeContext): Promise<RuntimeBootstrap> {
  const isBuilderPreview =
    Boolean(
      typeof window !== "undefined" &&
        (window as Window & { __TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH?: unknown })
          .__TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH,
    ) ||
    Boolean(ctx.basePath && ctx.basePath.includes("/public/apps-builder/draft-dev/sessions/")) ||
    (typeof window !== "undefined" &&
      window.location.pathname.includes("/public/apps-builder/draft-dev/sessions/"));
  const previewHeaders =
    !isBuilderPreview && previewAuthToken ? { Authorization: `Bearer ${previewAuthToken}` } : undefined;
  if (ctx.bootstrapUrl) {
    const response = await fetch(ctx.bootstrapUrl, { headers: previewHeaders });
    if (!response.ok) {
      throw new Error("Failed to fetch runtime bootstrap.");
    }
    return normalizeBootstrap((await response.json()) as RuntimeBootstrapWire);
  }

  const bootstrapPath = String(config.bootstrap_path || "").trim();
  if (bootstrapPath) {
    const apiBaseUrl = normalizeApiBaseUrl(config.api_base_url);
    const url = `${apiBaseUrl}${bootstrapPath.startsWith("/") ? bootstrapPath : `/${bootstrapPath}`}`;
    const response = await fetch(url, { headers: previewHeaders });
    if (!response.ok) {
      throw new Error("Failed to fetch runtime bootstrap.");
    }
    return normalizeBootstrap((await response.json()) as RuntimeBootstrapWire);
  }

  const appSlug = readConfiguredAppSlug();
  if (!appSlug) {
    throw new Error("Runtime bootstrap is missing app slug config.");
  }

  const bootstrap = await fetchRuntimeBootstrap({
    apiBaseUrl: normalizeApiBaseUrl(config.api_base_url),
    appSlug,
    previewToken: !isBuilderPreview ? (previewAuthToken || undefined) : undefined,
  });
  return normalizeBootstrap(bootstrap);
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

function inferBasePathFromBootstrap(bootstrap: RuntimeBootstrap): string {
  const streamPath =
    bootstrap.chat_stream_path ||
    (bootstrap.chat_stream_url
      ? new URL(
          bootstrap.chat_stream_url,
          typeof window !== "undefined" ? window.location.origin : "http://localhost",
        ).pathname
      : "");
  const normalized = String(streamPath || "").trim();
  if (!normalized.endsWith("/chat/stream")) {
    throw new Error("Runtime bootstrap is missing a valid chat stream path.");
  }
  const basePath = normalized.slice(0, -"/chat/stream".length);
  return basePath || "/";
}

export async function resolveRuntimeBasePath(basePath?: string): Promise<string> {
  const bootstrap = await resolveBootstrap(basePath);
  return inferBasePathFromBootstrap(bootstrap);
}

function resolveTokenProvider(basePath?: string) {
  const query = readQueryContext();
  const explicitToken = query.token;
  const resolvedBasePath = basePath || query.basePath || "";
  const isBuilderPreviewMode =
    query.mode === "builder-preview" ||
    resolvedBasePath.includes("/public/apps-builder/draft-dev/sessions/") ||
    (typeof window !== "undefined" && window.location.pathname.includes("/public/apps-builder/draft-dev/sessions/"));
  const isPublishedRevisionPreviewMode =
    resolvedBasePath.includes("/public/apps/preview/revisions/");

  return async () => {
    bindPreviewAuthChannel();
    if (isBuilderPreviewMode) return null;
    if (explicitToken) return explicitToken;
    if (isPublishedRevisionPreviewMode) return previewAuthToken;
    // Published runtime auth uses same-origin HttpOnly cookies via the host runtime gateway.
    return null;
  };
}

export const createRuntimeClient = (basePath?: string) => {
  bindPreviewAuthChannel();
  return {
    async stream(
      input: RuntimeInput,
      onEvent: (event: RuntimeEvent) => void,
    ): Promise<{ threadId: string | null }> {
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
