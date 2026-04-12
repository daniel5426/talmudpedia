export type RuntimeInputMessage = {
  role: string;
  content: string;
};

export type RuntimeInput = {
  input?: string;
  messages?: RuntimeInputMessage[];
  thread_id?: string;
  context?: Record<string, unknown>;
};

export type RuntimeAuthCapabilities = {
  enabled: boolean;
  providers: string[];
  exchange_enabled: boolean;
};

export type RuntimeBootstrap = {
  version: "runtime-bootstrap.v1";
  stream_contract_version: "run-stream.v2";
  request_contract_version: "thread.v1";
  app_id: string;
  slug: string;
  revision_id?: string;
  mode: "published-runtime" | "builder-preview";
  api_base_path: string;
  api_base_url?: string;
  chat_stream_path: string;
  chat_stream_url?: string;
  auth: RuntimeAuthCapabilities;
};

export type RawRuntimeEvent = Record<string, unknown>;

export type RuntimeResponseBlock =
  | {
      id: string;
      kind: "assistant_text";
      runId?: string | null;
      seq: number;
      status: string;
      text: string;
      ts?: string | null;
    }
  | {
      id: string;
      kind: "tool_call";
      runId?: string | null;
      seq: number;
      status: string;
      ts?: string | null;
      tool: Record<string, unknown>;
    }
  | {
      id: string;
      kind: "reasoning_note" | "approval_request" | "error" | "artifact" | "user_message";
      runId?: string | null;
      seq: number;
      status: string;
      ts?: string | null;
      [key: string]: unknown;
    };

export type NormalizedRuntimeEvent = {
  type: string;
  event?: string;
  data?: Record<string, unknown>;
  payload?: Record<string, unknown>;
  content?: string;
  responseBlocks?: RuntimeResponseBlock[];
  assistantOutputText?: string;
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
  threadId: string | null;
};
