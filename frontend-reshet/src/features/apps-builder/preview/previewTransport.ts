"use client";

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
  const raw = String(route || "").trim();
  if (!raw) return null;
  const [pathname] = raw.split(/[?#]/, 1);
  const normalized = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const collapsed = normalized.replace(/\/{2,}/g, "/");
  if (!collapsed) return "/";
  if (collapsed !== "/" && collapsed.endsWith("/")) {
    return collapsed.slice(0, -1) || "/";
  }
  return collapsed;
}

export function appendPreviewRuntimeToken(url: string, token?: string | null): string {
  const trimmedToken = String(token || "").trim();
  if (!trimmedToken) {
    return url;
  }
  try {
    const parsed = new URL(url);
    parsed.searchParams.set("runtime_token", trimmedToken);
    return parsed.toString();
  } catch {
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}runtime_token=${encodeURIComponent(trimmedToken)}`;
  }
}

export function buildBuilderPreviewDocumentUrl(options: {
  baseUrl: string;
  route: string;
  runtimeToken?: string | null;
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
    return appendPreviewRuntimeToken(parsed.toString(), options.runtimeToken);
  } catch {
    const separator = options.baseUrl.includes("?") ? "&" : "?";
    const reloadSuffix = reloadToken > 0 ? `&__reload=${reloadToken}` : "";
    const buildSuffix = buildId ? `&__build=${encodeURIComponent(buildId)}` : "";
    return appendPreviewRuntimeToken(
      `${options.baseUrl}${separator}preview_route=${encodeURIComponent(normalizedRoute)}${reloadSuffix}${buildSuffix}`,
      options.runtimeToken,
    );
  }
}
