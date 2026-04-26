"use client";

import { normalizeAppsBuilderPreviewRoute } from "@/services/apps-builder-preview-routes";

export type PreviewTransportStatus = "idle" | "booting" | "ready" | "reconnecting" | "failed";

export function logBuilderPreviewDebug(scope: string, event: string, fields: Record<string, unknown> = {}): void {
  if (typeof console === "undefined" || typeof console.info !== "function") {
    return;
  }
  console.info(`[apps-builder][${scope}]`, {
    event,
    ...fields,
  });
}

export function normalizeBuilderPreviewRoute(route: string): string | null {
  return normalizeAppsBuilderPreviewRoute(route);
}

export function buildBuilderPreviewDocumentUrl(options: {
  baseUrl: string;
  route: string;
  reloadToken?: number;
  buildId?: string | null;
}): string {
  const normalizedRoute = normalizeBuilderPreviewRoute(options.route) || "/";
  const reloadToken = Number(options.reloadToken || 0);
  const buildId = String(options.buildId || "").trim();
  try {
    const parsed = new URL(options.baseUrl);
    parsed.searchParams.set("preview_route", normalizedRoute);
    if (reloadToken > 0) {
      parsed.searchParams.set("__reload", String(reloadToken));
    } else {
      parsed.searchParams.delete("__reload");
    }
    if (buildId) {
      parsed.searchParams.set("__build", buildId);
    } else {
      parsed.searchParams.delete("__build");
    }
    return parsed.toString();
  } catch {
    const separator = options.baseUrl.includes("?") ? "&" : "?";
    const reloadSuffix = reloadToken > 0 ? `&__reload=${reloadToken}` : "";
    const buildSuffix = buildId ? `&__build=${encodeURIComponent(buildId)}` : "";
    return `${options.baseUrl}${separator}preview_route=${encodeURIComponent(normalizedRoute)}${reloadSuffix}${buildSuffix}`;
  }
}
