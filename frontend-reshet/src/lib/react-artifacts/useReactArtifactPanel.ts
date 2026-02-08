import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactArtifact } from "./types";
import { buildReactArtifactFromMessage } from "./buildArtifact";
import { getStorageKey, loadArtifact, saveArtifact } from "./storage";

export type ArtifactMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  approvalRequest?: boolean;
};

type UseReactArtifactPanelOptions = {
  messages: ArtifactMessage[];
  tenantKey?: string | null;
  chatId?: string | null;
};

export const useReactArtifactPanel = ({
  messages,
  tenantKey,
  chatId,
}: UseReactArtifactPanelOptions) => {
  const [artifact, setArtifact] = useState<ReactArtifact | null>(null);
  const savedCodeRef = useRef<string | null>(null);
  const lastMessageIdRef = useRef<string | null>(null);

  const storageKey = useMemo(() => {
    if (!tenantKey && !chatId) return null;
    return getStorageKey(tenantKey ?? "unknown-tenant", chatId ?? "unknown-chat");
  }, [tenantKey, chatId]);

  useEffect(() => {
    if (!storageKey) {
      setArtifact(null);
      savedCodeRef.current = null;
      lastMessageIdRef.current = null;
      return;
    }
    const stored = loadArtifact(storageKey);
    if (stored) {
      setArtifact(stored);
      savedCodeRef.current = stored.code;
    } else {
      setArtifact(null);
      savedCodeRef.current = null;
    }
    lastMessageIdRef.current = null;
  }, [storageKey]);

  useEffect(() => {
    if (!messages?.length) return;
    const latestAssistant = [...messages]
      .reverse()
      .find((msg) => msg.role === "assistant" && msg.content && !msg.approvalRequest);

    if (!latestAssistant) return;
    if (latestAssistant.id === lastMessageIdRef.current) return;

    const built = buildReactArtifactFromMessage(
      latestAssistant.content,
      latestAssistant.id
    );

    if (!built) return;

    lastMessageIdRef.current = latestAssistant.id;
    setArtifact(built);
    savedCodeRef.current = built.code;

    if (storageKey) {
      saveArtifact(storageKey, built);
    }
  }, [messages, storageKey]);

  const openFromMessage = useCallback(
    (messageId: string, content: string) => {
      const built = buildReactArtifactFromMessage(content, messageId);
      if (!built) return null;
      lastMessageIdRef.current = messageId;
      setArtifact(built);
      savedCodeRef.current = built.code;
      if (storageKey) {
        saveArtifact(storageKey, built);
      }
      return built;
    },
    [storageKey]
  );

  const updateCode = useCallback((code: string) => {
    setArtifact((prev) =>
      prev
        ? {
            ...prev,
            code,
            updatedAt: new Date().toISOString(),
          }
        : prev
    );
  }, []);

  const persistCurrent = useCallback(() => {
    if (!storageKey || !artifact) return;
    saveArtifact(storageKey, artifact);
    savedCodeRef.current = artifact.code;
  }, [artifact, storageKey]);

  const resetToSaved = useCallback(() => {
    const saved = savedCodeRef.current;
    if (!saved) return;
    setArtifact((prev) =>
      prev
        ? {
            ...prev,
            code: saved,
            updatedAt: new Date().toISOString(),
          }
        : prev
    );
  }, []);

  const closePanel = useCallback(() => {
    if (artifact && storageKey) {
      saveArtifact(storageKey, artifact);
    }
    setArtifact(null);
  }, [artifact, storageKey]);

  return {
    artifact,
    setArtifact,
    openFromMessage,
    updateCode,
    persistCurrent,
    resetToSaved,
    closePanel,
  };
};
