"use client";

import type { DraftDevSessionStatus } from "@/services/published-apps";
import type { PreviewTransportStatus } from "@/features/apps-builder/preview/previewTransport";

export type PreviewLoadingStepStatus = "complete" | "current" | "pending" | "error";

export type PreviewLoadingState = {
  title: string;
  detail: string;
  steps: Array<{
    label: string;
    status: PreviewLoadingStepStatus;
  }>;
};

type BuilderPreviewLoadingStateOptions = {
  lifecyclePhase: "idle" | "ensuring" | "syncing" | "running" | "recovering" | "error";
  draftDevStatus: DraftDevSessionStatus | null;
  transportStatus: PreviewTransportStatus | null;
  loadingMessage?: string | null;
  errorMessage?: string | null;
};

function createSteps(
  currentStep: number,
  errorStep: number | null = null,
): PreviewLoadingState["steps"] {
  const labels = [
    "Create live workspace",
    "Start preview runtime",
    "Connect live preview",
  ];
  return labels.map((label, index) => {
    const step = index + 1;
    if (errorStep === step) {
      return { label, status: "error" as const };
    }
    if (step < currentStep) {
      return { label, status: "complete" as const };
    }
    if (step === currentStep) {
      return { label, status: "current" as const };
    }
    return { label, status: "pending" as const };
  });
}

export function buildBuilderPreviewLoadingState(
  options: BuilderPreviewLoadingStateOptions,
): PreviewLoadingState | null {
  const detail = String(options.loadingMessage || "").trim() || "Loading preview...";
  const errorDetail = String(options.errorMessage || "").trim() || "Draft preview session failed.";

  if (options.transportStatus === "failed" || options.lifecyclePhase === "error") {
    return {
      title: "Preview failed",
      detail: errorDetail,
      steps: createSteps(3, 3),
    };
  }

  if (options.transportStatus === "reconnecting" || options.lifecyclePhase === "recovering") {
    return {
      title: "Recovering live preview",
      detail,
      steps: createSteps(3),
    };
  }

  if (options.transportStatus === "booting") {
    return {
      title: "Connecting live preview",
      detail,
      steps: createSteps(3),
    };
  }

  if (options.lifecyclePhase === "syncing") {
    return {
      title: "Syncing initial files",
      detail,
      steps: createSteps(2),
    };
  }

  if (options.lifecyclePhase === "ensuring") {
    if (options.draftDevStatus === "building") {
      return {
        title: "Starting preview runtime",
        detail,
        steps: createSteps(2),
      };
    }
    return {
      title: "Creating live workspace",
      detail,
      steps: createSteps(1),
    };
  }

  if (options.draftDevStatus === "starting") {
    return {
      title: "Creating live workspace",
      detail,
      steps: createSteps(1),
    };
  }

  if (options.draftDevStatus === "building" || options.draftDevStatus === "stopping") {
    return {
      title: "Starting preview runtime",
      detail,
      steps: createSteps(2),
    };
  }

  if (options.transportStatus === "ready" || options.lifecyclePhase === "running") {
    return null;
  }

  return {
    title: "Preparing draft preview",
    detail,
    steps: createSteps(1),
  };
}
