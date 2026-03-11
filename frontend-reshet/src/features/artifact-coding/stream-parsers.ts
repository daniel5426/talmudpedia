import type { ArtifactCodingStreamEvent } from "@/services/artifacts";

export type ArtifactCodingPendingQuestion = {
  requestId: string;
  questions: Array<{
    header?: string;
    question: string;
    multiple?: boolean;
    options: Array<{ label: string; description?: string }>;
  }>;
};

export const TERMINAL_RUN_EVENTS = new Set<string>([
  "run.completed",
  "run.failed",
  "run.cancelled",
  "run.paused",
]);

export const parseSse = (raw: string): ArtifactCodingStreamEvent | null => {
  const dataLines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("data:"));
  if (dataLines.length === 0) return null;
  const payload = dataLines.map((line) => line.slice(5).trimStart()).join("\n");
  if (!payload || payload === "[DONE]") return null;
  try {
    return JSON.parse(payload) as ArtifactCodingStreamEvent;
  } catch {
    return null;
  }
};

export const parseTerminalRunStatus = (status: unknown): "completed" | "failed" | "cancelled" | "paused" | null => {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "completed" || normalized === "failed" || normalized === "cancelled" || normalized === "paused") {
    return normalized;
  }
  return null;
};

export const parsePendingQuestionPayload = (payload: unknown): ArtifactCodingPendingQuestion | null => {
  if (!payload || typeof payload !== "object") return null;
  const source = payload as Record<string, unknown>;
  const requestId = String(source.request_id || source.requestId || "").trim();
  const rawQuestions = Array.isArray(source.questions) ? source.questions : [];
  if (!requestId || rawQuestions.length === 0) {
    return null;
  }
  const questions = rawQuestions
    .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    .map((item) => ({
      header: String(item.header || "").trim() || undefined,
      question: String(item.question || "").trim(),
      multiple: Boolean(item.multiple),
      options: (Array.isArray(item.options) ? item.options : [])
        .filter((option): option is Record<string, unknown> => !!option && typeof option === "object")
        .map((option) => ({
          label: String(option.label || "").trim(),
          description: String(option.description || "").trim() || undefined,
        }))
        .filter((option) => !!option.label),
    }))
    .filter((item) => !!item.question);
  if (!questions.length) return null;
  return { requestId, questions };
};
