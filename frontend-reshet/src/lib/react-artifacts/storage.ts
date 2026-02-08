import type { ReactArtifact } from "./types";

const STORAGE_PREFIX = "react-artifact:v1";

export const getStorageKey = (tenantSlugOrId?: string | null, chatId?: string | null) => {
  const tenant = tenantSlugOrId || "unknown-tenant";
  const chat = chatId || "draft-chat";
  return `${STORAGE_PREFIX}:${tenant}:${chat}`;
};

export const loadArtifact = (storageKey: string): ReactArtifact | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ReactArtifact;
    if (!parsed?.code || !parsed?.sourceMessageId) return null;
    return parsed;
  } catch (error) {
    console.warn("Failed to load react artifact", error);
    return null;
  }
};

export const saveArtifact = (storageKey: string, artifact: ReactArtifact) => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(artifact));
  } catch (error) {
    console.warn("Failed to save react artifact", error);
  }
};
