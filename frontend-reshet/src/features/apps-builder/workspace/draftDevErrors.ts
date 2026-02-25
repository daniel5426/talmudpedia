"use client";

const DRAFT_SANDBOX_NOT_RUNNING_MARKER = "draft dev sandbox is not running";
const DRAFT_CONTROLLER_TIMEOUT_MARKERS = ["readtimeout", "timed out", "timeout"];

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
