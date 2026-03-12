"use client";

const DRAFT_SANDBOX_NOT_RUNNING_MARKER = "draft dev sandbox is not running";
const DRAFT_CONTROLLER_TIMEOUT_MARKERS = ["readtimeout", "timed out", "timeout"];
const CODING_AGENT_RUN_ACTIVE_MARKER = "coding_agent_run_active";
const DRAFT_WARMUP_ERROR_MARKERS = [
  "preview service did not become ready",
  "preview state not ready",
  "preview root not ready",
  "preview build pending",
];

function parseErrorDetailPayload(error: unknown): unknown {
  if (!error) return null;
  if (typeof error === "string") {
    const raw = error.trim();
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  }
  if (error instanceof Error) {
    return parseErrorDetailPayload(error.message);
  }
  return error;
}

export function isCodingAgentRunActiveError(error: unknown): boolean {
  const detail = parseErrorDetailPayload(error);
  if (!detail) return false;
  if (typeof detail === "string") {
    const normalized = detail.toLowerCase();
    return normalized.includes(CODING_AGENT_RUN_ACTIVE_MARKER);
  }
  if (typeof detail !== "object") return false;
  const code = String((detail as Record<string, unknown>).code || "").trim().toUpperCase();
  return code === "CODING_AGENT_RUN_ACTIVE";
}

export function isDraftSandboxNotRunningError(error: unknown): boolean {
  if (!error) return false;
  if (typeof error === "string") {
    return error.toLowerCase().includes(DRAFT_SANDBOX_NOT_RUNNING_MARKER);
  }
  if (error instanceof Error) {
    return error.message.toLowerCase().includes(DRAFT_SANDBOX_NOT_RUNNING_MARKER);
  }
  return false;
}

export function isDraftDevTransientBootstrapError(error: unknown): boolean {
  if (isDraftSandboxNotRunningError(error)) return true;
  const message =
    typeof error === "string" ? error.toLowerCase() : error instanceof Error ? error.message.toLowerCase() : "";
  return DRAFT_CONTROLLER_TIMEOUT_MARKERS.some((marker) => message.includes(marker));
}

export function isDraftDevWarmupError(error: unknown): boolean {
  const message =
    typeof error === "string" ? error.toLowerCase() : error instanceof Error ? error.message.toLowerCase() : "";
  return DRAFT_WARMUP_ERROR_MARKERS.some((marker) => message.includes(marker));
}
