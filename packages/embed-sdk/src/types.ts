import type { EmbeddedAgentSDKErrorKind } from "./errors";

export type EmbeddedAgentResponseBlock =
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
      kind: "ui_blocks";
      runId?: string | null;
      seq: number;
      status: string;
      ts?: string | null;
      toolCallId?: string | null;
      contractVersion?: string | null;
      bundle?: Record<string, unknown>;
      error?: string | null;
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
  response_blocks: EmbeddedAgentResponseBlock[];
  attachments: EmbeddedAgentAttachment[];
  created_at: string;
  completed_at: string | null;
  run_events: EmbeddedAgentRuntimeEvent[];
};

export type EmbeddedAgentThreadDetail = EmbeddedAgentThreadSummary & {
  turns: EmbeddedAgentThreadTurn[];
  paging: {
    has_more: boolean;
    next_before_turn_index: number | null;
  };
};

export type EmbeddedAgentThreadsResponse = {
  items: EmbeddedAgentThreadSummary[];
  total: number;
};

export type EmbeddedAgentRuntimeDiagnostic = {
  message?: string;
} & Record<string, unknown>;

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

export type EmbeddedAgentRuntimeEvent = EmbeddedAgentRuntimeEventBase;

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
  beforeTurnIndex?: number;
  limit?: number;
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
