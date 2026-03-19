import type { EmbeddedAgentSDKErrorKind } from "./errors";

export type EmbeddedAgentStreamRequest = {
  input?: string;
  messages?: Array<Record<string, unknown>>;
  attachment_ids?: string[];
  thread_id?: string;
  external_user_id: string;
  external_session_id?: string;
  metadata?: Record<string, unknown>;
  client?: Record<string, unknown>;
};

export type EmbeddedAgentAttachment = {
  id: string;
  thread_id: string | null;
  kind: string;
  filename: string;
  mime_type: string;
  byte_size: number;
  status: string;
  processing_error: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type EmbeddedAgentThreadSummary = {
  id: string;
  agent_id: string | null;
  external_user_id: string | null;
  external_session_id: string | null;
  title: string | null;
  status: string;
  surface: string;
  last_run_id: string | null;
  last_activity_at: string | null;
  created_at: string;
  updated_at: string;
};

export type EmbeddedAgentThreadTurn = {
  id: string;
  run_id: string;
  turn_index: number;
  user_input_text: string | null;
  assistant_output_text: string | null;
  status: string;
  usage_tokens: number;
  metadata: Record<string, unknown>;
  attachments: EmbeddedAgentAttachment[];
  created_at: string;
  completed_at: string | null;
  run_events: EmbeddedAgentRuntimeEvent[];
};

export type EmbeddedAgentThreadDetail = EmbeddedAgentThreadSummary & {
  turns: EmbeddedAgentThreadTurn[];
};

export type EmbeddedAgentThreadsResponse = {
  items: EmbeddedAgentThreadSummary[];
  total: number;
};

export type EmbeddedAgentRuntimeDiagnostic = {
  message?: string;
} & Record<string, unknown>;

export type EmbeddedAgentUiPayload = {
  format: "openui";
  version: 1;
  content?: string | null;
  content_delta?: string | null;
  ast?: Record<string, unknown> | null;
  component_library_id?: string | null;
  surface?: "chat_inline" | "app_canvas" | string | null;
  is_final?: boolean;
};

type EmbeddedAgentRuntimeEventBase = {
  version: "run-stream.v2";
  seq: number;
  ts: string;
  event: string;
  run_id: string;
  stage: string;
  payload: Record<string, unknown>;
  diagnostics: EmbeddedAgentRuntimeDiagnostic[];
};

export type EmbeddedAgentUiRuntimeEvent = Omit<
  EmbeddedAgentRuntimeEventBase,
  "event" | "stage" | "payload"
> & {
  event: "assistant.ui";
  stage: "assistant";
  payload: EmbeddedAgentUiPayload;
};

export type EmbeddedAgentRuntimeEvent =
  | EmbeddedAgentUiRuntimeEvent
  | EmbeddedAgentRuntimeEventBase;

export type StreamAgentResult = {
  threadId: string | null;
};

export type EmbeddedAgentThreadListOptions = {
  externalUserId: string;
  externalSessionId?: string;
  skip?: number;
  limit?: number;
};

export type EmbeddedAgentThreadDetailOptions = {
  externalUserId: string;
  externalSessionId?: string;
};

export type EmbeddedAgentThreadDeleteOptions = {
  externalUserId: string;
  externalSessionId?: string;
};

export type EmbeddedAgentThreadDeleteResult = {
  deleted: boolean;
};

export type EmbeddedAgentAttachmentUploadOptions = {
  externalUserId: string;
  externalSessionId?: string;
  threadId?: string;
  files: File[];
};

export type EmbeddedAgentAttachmentUploadResult = {
  items: EmbeddedAgentAttachment[];
};

export type EmbeddedAgentClientOptions = {
  baseUrl: string;
  apiKey: string;
  fetchImpl?: typeof fetch;
};

export type EmbeddedAgentSDKSerializedError = {
  message: string;
  kind: EmbeddedAgentSDKErrorKind;
  status?: number;
  details?: unknown;
};
