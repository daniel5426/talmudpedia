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

export type TerminalRunStatus = "completed" | "failed" | "cancelled" | "paused";

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

export const resolvePositiveTimeoutMs = (rawValue: string | undefined, fallbackMs: number): number => {
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) return fallbackMs;
  const rounded = Math.floor(parsed);
  if (rounded <= 0) return fallbackMs;
  return rounded;
};
