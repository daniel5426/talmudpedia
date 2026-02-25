import { useEffect, type MutableRefObject } from "react";

import { publishedAppsService } from "@/services";

import { parseTerminalRunStatus } from "./stream-parsers";

type UseAppsBuilderChatSendingReconcileOptions = {
  appId: string;
  isSending: boolean;
  isSendingRef: MutableRefObject<boolean>;
  activeRunIdRef: MutableRefObject<string | null>;
  lastKnownRunIdRef: MutableRefObject<string | null>;
  activeChatSessionIdRef: MutableRefObject<string | null>;
  forceClearSendingState: () => void;
};

export function useAppsBuilderChatSendingReconcile({
  appId,
  isSending,
  isSendingRef,
  activeRunIdRef,
  lastKnownRunIdRef,
  activeChatSessionIdRef,
  forceClearSendingState,
}: UseAppsBuilderChatSendingReconcileOptions) {
  useEffect(() => {
    if (!isSending) {
      return;
    }
    let disposed = false;
    const intervalMs = 2000;
    const isNotFoundError = (err: unknown): boolean => {
      const message = err instanceof Error ? err.message : String(err || "");
      return message.toLowerCase().includes("not found");
    };
    const reconcileSendingState = async () => {
      if (disposed || !isSendingRef.current) {
        return;
      }
      const runId = activeRunIdRef.current || lastKnownRunIdRef.current;
      if (runId) {
        try {
          const run = await publishedAppsService.getCodingAgentRun(appId, runId);
          if (parseTerminalRunStatus(run.status)) {
            forceClearSendingState();
          }
          return;
        } catch (err) {
          if (isNotFoundError(err)) {
            forceClearSendingState();
            return;
          }
        }
      }
      const sessionId = activeChatSessionIdRef.current;
      if (!sessionId) {
        return;
      }
      try {
        const active = await publishedAppsService.findCodingAgentChatSessionActiveRun(appId, sessionId);
        if (!active || parseTerminalRunStatus(active.status)) {
          forceClearSendingState();
        }
      } catch (err) {
        if (isNotFoundError(err)) {
          forceClearSendingState();
        }
      }
    };
    void reconcileSendingState();
    const timer = setInterval(() => {
      void reconcileSendingState();
    }, intervalMs);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [
    activeChatSessionIdRef,
    activeRunIdRef,
    appId,
    forceClearSendingState,
    isSending,
    isSendingRef,
    lastKnownRunIdRef,
  ]);
}
