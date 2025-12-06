import type { FileUIPart } from "ai";

/**
 * Error constants for chat operations
 */
export const ChatErrorTypes = {
  ABORT: "AbortError",
  CHAT_ID_CHANGED: "Chat ID changed",
  USER_STOPPED: "User stopped",
  NEW_REQUEST: "New request starting",
} as const;

/**
 * Checks if an error should be silently ignored (user-initiated cancellations)
 */
export function isIgnorableError(error: any): boolean {
  return (
    error.name === ChatErrorTypes.ABORT ||
    error.message === ChatErrorTypes.CHAT_ID_CHANGED ||
    error.message === ChatErrorTypes.USER_STOPPED ||
    error.message === ChatErrorTypes.NEW_REQUEST
  );
}

/**
 * Processes files for upload by converting them to base64
 */
export async function processFilesForUpload(
  files: FileUIPart[]
): Promise<Array<{ name: string; type: string; content: string }>> {
  return Promise.all(
    files.map(async (file) => {
      const response = await fetch(file.url);
      const blob = await response.blob();

      return new Promise<{
        name: string;
        type: string;
        content: string;
      }>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(",")[1];
          resolve({
            name: file.filename || "attachment",
            type: file.mediaType || "application/octet-stream",
            content: base64,
          });
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });
    })
  );
}

/**
 * Helper class to manage abort controller lifecycle
 */
export class AbortControllerManager {
  private controller: AbortController | null = null;

  get signal() {
    return this.controller?.signal;
  }

  /**
   * Aborts the current request if one exists
   */
  abort(reason?: string): void {
    if (this.controller && !this.controller.signal.aborted) {
      this.controller.abort(reason);
      this.controller = null;
    }
  }

  /**
   * Creates a new abort controller, aborting any existing one
   */
  create(reason?: string): AbortController {
    this.abort(reason);
    this.controller = new AbortController();
    return this.controller;
  }

  /**
   * Checks if current controller is aborted
   */
  isAborted(): boolean {
    return this.controller?.signal.aborted ?? true;
  }

  /**
   * Clears the controller without aborting
   */
  clear(): void {
    this.controller = null;
  }
}
