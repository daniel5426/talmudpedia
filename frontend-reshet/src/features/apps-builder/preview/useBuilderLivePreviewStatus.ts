"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { publishedAppsService, type DraftDevSessionResponse } from "@/services";
import { logBuilderPreviewDebug } from "@/features/apps-builder/preview/previewTransport";

type LivePreviewState = NonNullable<DraftDevSessionResponse["live_preview"]>;

type UseBuilderLivePreviewStatusOptions = {
  previewBaseUrl: string | null;
  sessionLivePreview: DraftDevSessionResponse["live_preview"] | null | undefined;
  enabled: boolean;
};

const ACTIVE_POLL_MS = 1500;

export function useBuilderLivePreviewStatus({
  previewBaseUrl,
  sessionLivePreview,
  enabled,
}: UseBuilderLivePreviewStatusOptions): LivePreviewState | null {
  const [state, setState] = useState<LivePreviewState | null>(
    (sessionLivePreview || null) as LivePreviewState | null,
  );
  const inFlightRef = useRef(false);

  useEffect(() => {
    setState((current) => {
      const next = (sessionLivePreview || null) as LivePreviewState | null;
      if (!next) {
        return current;
      }
      return {
        ...current,
        ...next,
      };
    });
  }, [sessionLivePreview]);

  const shouldPoll = useMemo(() => {
    const status = String(state?.status || sessionLivePreview?.status || "").trim().toLowerCase();
    return status === "booting"
      || status === "building"
      || status === "recovering"
      || status === "failed_no_build";
  }, [sessionLivePreview?.status, state?.status]);

  const sessionPreviewStatus = sessionLivePreview?.status || null;
  const currentStateStatus = state?.status || null;
  const currentBuildId = state?.current_build_id || null;
  const currentLastSuccessfulBuildId = state?.last_successful_build_id || null;

  useEffect(() => {
    if (!enabled || !previewBaseUrl || !shouldPoll) {
      return;
    }
    let cancelled = false;

    const poll = async () => {
      if (inFlightRef.current) {
        return;
      }
      inFlightRef.current = true;
      logBuilderPreviewDebug("live-preview", "status_poll_start", {
        previewBaseUrl,
        currentStatus: currentStateStatus || sessionPreviewStatus,
        currentBuildId,
        currentLastSuccessfulBuildId,
        previewAuthTokenPresent: false,
      });
      try {
        const next = await publishedAppsService.getDraftDevPreviewStatus(previewBaseUrl);
        if (cancelled) {
          return;
        }
        setState((current) => ({ ...(current || {}), ...next }));
        logBuilderPreviewDebug("live-preview", "status", {
          previewBaseUrl,
          status: next.status || null,
          currentBuildId: next.current_build_id || null,
          lastSuccessfulBuildId: next.last_successful_build_id || null,
          updatedAt: next.updated_at || null,
          debugBuildSequence: (next as Record<string, unknown>).debug_build_sequence ?? null,
          debugLastTriggerReason: (next as Record<string, unknown>).debug_last_trigger_reason ?? null,
          debugLastTriggerRevisionToken: (next as Record<string, unknown>).debug_last_trigger_revision_token ?? null,
          error: next.error || null,
        });
      } catch (error) {
        if (!cancelled) {
          logBuilderPreviewDebug("live-preview", "status_failed", {
            previewBaseUrl,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      } finally {
        inFlightRef.current = false;
      }
    };

    void poll();
    const interval = window.setInterval(() => {
      void poll();
    }, ACTIVE_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [
    enabled,
      previewBaseUrl,
    sessionPreviewStatus,
    shouldPoll,
    currentBuildId,
    currentLastSuccessfulBuildId,
    currentStateStatus,
  ]);

  return state;
}
