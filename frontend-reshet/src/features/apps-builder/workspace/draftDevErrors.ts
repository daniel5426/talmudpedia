"use client";

const DRAFT_SANDBOX_NOT_RUNNING_MARKER = "draft dev sandbox is not running";

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
