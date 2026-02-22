export type RuntimeInputMessage = {
  role: string;
  content: string;
};

export type RuntimeInput = {
  input?: string;
  messages?: RuntimeInputMessage[];
  chat_id?: string;
  context?: Record<string, unknown>;
};

export type RuntimeAuthCapabilities = {
  enabled: boolean;
  providers: string[];
  exchange_enabled: boolean;
};

export type RuntimeBootstrap = {
  version: "runtime-bootstrap.v1";
  app_id: string;
  slug: string;
  revision_id?: string;
  mode: "published-runtime" | "builder-preview";
  api_base_path: string;
  api_base_url?: string;
  chat_stream_path: string;
  chat_stream_url?: string;
  auth: RuntimeAuthCapabilities;
  preview_token?: string | null;
};

export type RawRuntimeEvent = Record<string, unknown>;

export type NormalizedRuntimeEvent = {
  type: string;
  event?: string;
  data?: Record<string, unknown>;
  payload?: Record<string, unknown>;
  content?: string;
  raw: RawRuntimeEvent;
};

export type RuntimeTokenProvider = (() => string | null | undefined | Promise<string | null | undefined>) | undefined;

export type RuntimeClientOptions = {
  apiBaseUrl?: string;
  bootstrap?: RuntimeBootstrap;
  tokenProvider?: RuntimeTokenProvider;
  fetchImpl?: typeof fetch;
};

export type RuntimeStreamResult = {
  chatId: string | null;
};
