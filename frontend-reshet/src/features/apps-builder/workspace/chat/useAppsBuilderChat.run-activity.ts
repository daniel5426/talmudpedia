import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { publishedAppsService } from "@/services";

import { parseTerminalRunStatus } from "./stream-parsers";

export type SessionRunActivity = {
  runId: string;
  status: string;
};

type SessionRunActivityMap = Record<string, SessionRunActivity>;

type UseAppsBuilderChatRunActivityOptions = {
  appId: string;
  pollIntervalMs?: number;
};

function normalizeSessionId(value: string | null | undefined): string {
  return String(value || "").trim();
}

export function useAppsBuilderChatRunActivity({
  appId,
  pollIntervalMs = 3000,
}: UseAppsBuilderChatRunActivityOptions) {
  const [sessionRunActivityMap, setSessionRunActivityMap] = useState<SessionRunActivityMap>({});
  const sessionRunActivityRef = useRef<SessionRunActivityMap>({});

  const updateSessionRunActivity = useCallback(
    (sessionId: string, next: SessionRunActivity | null) => {
      const normalizedSessionId = normalizeSessionId(sessionId);
      if (!normalizedSessionId) return;
      setSessionRunActivityMap((prev) => {
        const current = prev[normalizedSessionId];
        if (!next) {
          if (!current) return prev;
          const copy = { ...prev };
          delete copy[normalizedSessionId];
          return copy;
        }
        if (current && current.runId === next.runId && current.status === next.status) {
          return prev;
        }
        return { ...prev, [normalizedSessionId]: next };
      });
    },
    [],
  );

  useEffect(() => {
    sessionRunActivityRef.current = sessionRunActivityMap;
  }, [sessionRunActivityMap]);

  const markSessionRunActive = useCallback(
    (sessionId: string, runId: string, status = "running") => {
      const normalizedSessionId = normalizeSessionId(sessionId);
      const normalizedRunId = String(runId || "").trim();
      if (!normalizedSessionId || !normalizedRunId) return;
      updateSessionRunActivity(normalizedSessionId, { runId: normalizedRunId, status: String(status || "running") });
    },
    [updateSessionRunActivity],
  );

  const clearSessionRunActivity = useCallback(
    (sessionId: string, runId?: string | null) => {
      const normalizedSessionId = normalizeSessionId(sessionId);
      if (!normalizedSessionId) return;
      const normalizedRunId = String(runId || "").trim();
      const current = sessionRunActivityRef.current[normalizedSessionId];
      if (normalizedRunId && current && current.runId !== normalizedRunId) {
        return;
      }
      updateSessionRunActivity(normalizedSessionId, null);
    },
    [updateSessionRunActivity],
  );

  const probeSessionRunActivity = useCallback(
    async (sessionId: string) => {
      const normalizedSessionId = normalizeSessionId(sessionId);
      if (!normalizedSessionId) return;
      try {
        const active = await publishedAppsService.findCodingAgentChatSessionActiveRun(appId, normalizedSessionId);
        if (!active) {
          clearSessionRunActivity(normalizedSessionId);
          return;
        }
        const terminal = parseTerminalRunStatus(active.status);
        if (terminal) {
          clearSessionRunActivity(normalizedSessionId);
          return;
        }
        markSessionRunActive(normalizedSessionId, active.run_id, active.status);
      } catch {
        // Ignore transient lookup errors to avoid UI churn.
      }
    },
    [appId, clearSessionRunActivity, markSessionRunActive],
  );

  const probeSessionRunActivityBatch = useCallback(
    async (sessionIds: string[]) => {
      const normalized = Array.from(
        new Set(
          (sessionIds || [])
            .map((item) => normalizeSessionId(item))
            .filter(Boolean),
        ),
      );
      await Promise.all(normalized.map(async (sessionId) => {
        await probeSessionRunActivity(sessionId);
      }));
    },
    [probeSessionRunActivity],
  );

  const runningSessionIds = useMemo(() => Object.keys(sessionRunActivityMap), [sessionRunActivityMap]);
  const runningSessionIdsKey = useMemo(
    () => [...runningSessionIds].sort().join("|"),
    [runningSessionIds],
  );

  useEffect(() => {
    if (!runningSessionIds.length) return;
    let disposed = false;
    const timer = setInterval(() => {
      if (disposed) return;
      const sessionIds = Object.keys(sessionRunActivityRef.current);
      if (!sessionIds.length) return;
      void probeSessionRunActivityBatch(sessionIds);
    }, Math.max(1000, pollIntervalMs));
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [pollIntervalMs, probeSessionRunActivityBatch, runningSessionIds.length, runningSessionIdsKey]);

  return {
    sessionRunActivityMap,
    runningSessionIds,
    markSessionRunActive,
    clearSessionRunActivity,
    probeSessionRunActivity,
    probeSessionRunActivityBatch,
  };
}
