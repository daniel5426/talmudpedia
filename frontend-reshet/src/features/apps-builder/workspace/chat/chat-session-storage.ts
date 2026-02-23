const STORAGE_PREFIX = "apps-builder:last-chat-session";

function storageKey(appId: string): string {
  return `${STORAGE_PREFIX}:${String(appId || "").trim()}`;
}

export function readStoredChatSessionId(appId: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(storageKey(appId));
    const normalized = String(value || "").trim();
    return normalized || null;
  } catch {
    return null;
  }
}

export function writeStoredChatSessionId(appId: string, sessionId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    const key = storageKey(appId);
    const normalized = String(sessionId || "").trim();
    if (!normalized) {
      window.localStorage.removeItem(key);
      return;
    }
    window.localStorage.setItem(key, normalized);
  } catch {
    // ignore storage exceptions
  }
}
