"use client";

import type { FileUIPart } from "ai";

const STORAGE_KEY = "kesher.pendingChatMessage";
const PROCESSING_VALUE = "__processing__";

export type PendingChatMessage = {
  text: string;
  files: FileUIPart[];
};

export const savePendingChatMessage = (message: PendingChatMessage) => {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(message));
};

export const hasPendingChatMessage = () => {
  if (typeof window === "undefined") {
    return false;
  }
  return sessionStorage.getItem(STORAGE_KEY) !== null;
};

export const consumePendingChatMessage = (): PendingChatMessage | null => {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw || raw === PROCESSING_VALUE) {
    return null;
  }
  sessionStorage.setItem(STORAGE_KEY, PROCESSING_VALUE);
  try {
    return JSON.parse(raw) as PendingChatMessage;
  } catch {
    return null;
  }
};

export const clearPendingChatMessage = () => {
  if (typeof window === "undefined") {
    return;
  }
  sessionStorage.removeItem(STORAGE_KEY);
};

