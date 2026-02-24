import type { CodingAgentStreamEvent, RevisionConflictResponse } from "@/services";

export type CodingAgentModelUnavailableDetail = {
  code: "CODING_AGENT_MODEL_UNAVAILABLE";
  field: "model_id";
  message: string;
};

export type CodingAgentEngineUnavailableDetail = {
  code: "CODING_AGENT_ENGINE_UNAVAILABLE" | "CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME";
  field: "engine";
  message: string;
};

export type CodingAgentRunActiveDetail = {
  code: "CODING_AGENT_RUN_ACTIVE";
  message: string;
  active_run_id: string;
  chat_session_id?: string;
  next_replay_seq?: number;
};

export type TerminalRunStatus = "completed" | "failed" | "cancelled" | "paused";

export type CodingAgentQuestionOption = {
  label: string;
  description?: string;
};

export type CodingAgentQuestionItem = {
  header?: string;
  question: string;
  multiple?: boolean;
  options: CodingAgentQuestionOption[];
};

export type CodingAgentPendingQuestion = {
  requestId: string;
  questions: CodingAgentQuestionItem[];
  toolCallId?: string;
  toolMessageId?: string;
};

export const TERMINAL_RUN_EVENTS = new Set<string>([
  "run.completed",
  "run.failed",
  "run.cancelled",
  "run.paused",
]);

export const parseSse = (raw: string): CodingAgentStreamEvent | null => {
  const dataLines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("data:"));
  if (dataLines.length === 0) return null;
  const payload = dataLines.map((line) => line.slice(5).trimStart()).join("\n");
  if (!payload || payload === "[DONE]") return null;
  try {
    return JSON.parse(payload) as CodingAgentStreamEvent;
  } catch {
    return null;
  }
};

export const parseRevisionConflict = (detail: unknown): RevisionConflictResponse | null => {
  let parsed: unknown = detail;
  if (typeof parsed === "string") {
    const text = parsed.trim();
    if (!text) return null;
    try {
      parsed = JSON.parse(text);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== "object") {
    return null;
  }
  const candidate = parsed as Partial<RevisionConflictResponse>;
  if (candidate.code !== "REVISION_CONFLICT") {
    return null;
  }
  if (!candidate.latest_revision_id || !candidate.latest_updated_at) {
    return null;
  }
  return {
    code: "REVISION_CONFLICT",
    latest_revision_id: String(candidate.latest_revision_id),
    latest_updated_at: String(candidate.latest_updated_at),
    message: String(candidate.message || "Draft revision is stale"),
  };
};

export const parseModelUnavailableDetail = (detail: unknown): CodingAgentModelUnavailableDetail | null => {
  let parsed: unknown = detail;
  if (typeof parsed === "string") {
    const text = parsed.trim();
    if (!text) return null;
    try {
      parsed = JSON.parse(text);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== "object") {
    return null;
  }
  const candidate = parsed as Partial<CodingAgentModelUnavailableDetail>;
  if (candidate.code !== "CODING_AGENT_MODEL_UNAVAILABLE") {
    return null;
  }
  if (candidate.field !== "model_id") {
    return null;
  }
  return {
    code: "CODING_AGENT_MODEL_UNAVAILABLE",
    field: "model_id",
    message: String(candidate.message || "Selected model is unavailable. Pick another model and retry."),
  };
};

export const parseEngineUnavailableDetail = (detail: unknown): CodingAgentEngineUnavailableDetail | null => {
  let parsed: unknown = detail;
  if (typeof parsed === "string") {
    const text = parsed.trim();
    if (!text) return null;
    try {
      parsed = JSON.parse(text);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== "object") {
    return null;
  }
  const candidate = parsed as Partial<CodingAgentEngineUnavailableDetail>;
  if (candidate.field !== "engine") {
    return null;
  }
  if (candidate.code !== "CODING_AGENT_ENGINE_UNAVAILABLE" && candidate.code !== "CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME") {
    return null;
  }
  return {
    code: candidate.code,
    field: "engine",
    message: String(candidate.message || "Selected engine is unavailable for this runtime."),
  };
};

export const parseRunActiveDetail = (detail: unknown): CodingAgentRunActiveDetail | null => {
  let parsed: unknown = detail;
  if (typeof parsed === "string") {
    const text = parsed.trim();
    if (!text) return null;
    try {
      parsed = JSON.parse(text);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== "object") {
    return null;
  }
  const candidate = parsed as Partial<CodingAgentRunActiveDetail>;
  if (candidate.code !== "CODING_AGENT_RUN_ACTIVE") {
    return null;
  }
  const runId = String(candidate.active_run_id || "").trim();
  if (!runId) {
    return null;
  }
  const nextReplaySeqRaw = Number(candidate.next_replay_seq);
  const nextReplaySeq =
    Number.isFinite(nextReplaySeqRaw) && nextReplaySeqRaw > 0
      ? Math.floor(nextReplaySeqRaw)
      : undefined;
  return {
    code: "CODING_AGENT_RUN_ACTIVE",
    message: String(candidate.message || "A coding-agent run is already active for this preview session."),
    active_run_id: runId,
    chat_session_id: candidate.chat_session_id ? String(candidate.chat_session_id) : undefined,
    next_replay_seq: nextReplaySeq,
  };
};

export const parseTerminalRunStatus = (status: unknown): TerminalRunStatus | null => {
  const normalized = String(status || "").trim().toLowerCase();
  if (
    normalized !== "completed" &&
    normalized !== "failed" &&
    normalized !== "cancelled" &&
    normalized !== "paused"
  ) {
    return null;
  }
  return normalized;
};

export const parsePendingQuestionPayload = (payload: unknown): CodingAgentPendingQuestion | null => {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const source = payload as Record<string, unknown>;
  const requestId = String(source.request_id || source.requestId || "").trim();
  if (!requestId) {
    return null;
  }
  const rawQuestions = Array.isArray(source.questions) ? source.questions : [];
  const questions: CodingAgentQuestionItem[] = rawQuestions
    .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    .map((item) => ({
      header: String(item.header || "").trim() || undefined,
      question: String(item.question || "").trim(),
      multiple: Boolean(item.multiple),
      options: (Array.isArray(item.options) ? item.options : [])
        .filter((opt): opt is Record<string, unknown> => !!opt && typeof opt === "object")
        .map((opt) => ({
          label: String(opt.label || "").trim(),
          description: String(opt.description || "").trim() || undefined,
        }))
        .filter((opt) => !!opt.label),
    }))
    .filter((item) => !!item.question);
  if (questions.length === 0) {
    return null;
  }
  const tool = source.tool && typeof source.tool === "object" ? (source.tool as Record<string, unknown>) : {};
  return {
    requestId,
    questions,
    toolCallId: String(tool.call_id || tool.callId || "").trim() || undefined,
    toolMessageId: String(tool.message_id || tool.messageId || "").trim() || undefined,
  };
};

export const resolvePositiveTimeoutMs = (rawValue: string | undefined, fallbackMs: number): number => {
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) return fallbackMs;
  const rounded = Math.floor(parsed);
  if (rounded <= 0) return fallbackMs;
  return rounded;
};
