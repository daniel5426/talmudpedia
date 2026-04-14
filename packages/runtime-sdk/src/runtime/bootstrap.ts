import type { RuntimeBootstrap } from "../core/types";

export type RuntimeBootstrapRequest = {
  apiBaseUrl?: string;
  appSlug?: string;
  revisionId?: string;
  bootstrapUrl?: string;
  previewToken?: string;
  fetchImpl?: typeof fetch;
};

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function isAbsoluteUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

function resolveBuilderPreviewBootstrapUrl(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const runtimeWindow = window as Window & {
    __TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH?: unknown;
  };
  const previewBasePath = String(runtimeWindow.__TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH || "").trim();
  if (previewBasePath) {
    const normalized = previewBasePath.endsWith("/") ? previewBasePath.slice(0, -1) : previewBasePath;
    return `${normalized}/_talmudpedia/runtime/bootstrap`;
  }
  const pathname = String(window.location.pathname || "").trim();
  const match = pathname.match(/^(\/public\/apps-builder\/draft-dev\/sessions\/[^/]+\/preview)\/?$/);
  if (!match) {
    return null;
  }
  return `${match[1]}/_talmudpedia/runtime/bootstrap`;
}

function resolveBootstrapPath(request: RuntimeBootstrapRequest): string {
  const explicitBootstrapUrl =
    String(request.bootstrapUrl || "").trim() || resolveBuilderPreviewBootstrapUrl() || "";
  if (explicitBootstrapUrl) {
    return explicitBootstrapUrl;
  }
  if (request.revisionId) {
    return `/public/apps/preview/revisions/${encodeURIComponent(request.revisionId)}/runtime/bootstrap`;
  }
  if (request.appSlug) {
    return `/public/external/apps/${encodeURIComponent(request.appSlug)}/runtime/bootstrap`;
  }
  throw new Error("Runtime bootstrap requires bootstrapUrl, appSlug, or revisionId.");
}

export async function fetchRuntimeBootstrap(request: RuntimeBootstrapRequest): Promise<RuntimeBootstrap> {
  const fetchImpl = request.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    throw new Error("Runtime SDK requires fetch implementation.");
  }

  const base = trimTrailingSlash(request.apiBaseUrl || "/api/py");
  const path = resolveBootstrapPath(request);
  const url = isAbsoluteUrl(path) ? path : `${base}${path}`;
  const headers: Record<string, string> = {};
  if (request.previewToken) {
    headers.Authorization = `Bearer ${request.previewToken}`;
  }

  const response = await fetchImpl(url, { method: "GET", headers });
  if (!response.ok) {
    let message = "Failed to fetch runtime bootstrap";
    try {
      const data = (await response.json()) as { detail?: string; message?: string };
      message = String(data.detail || data.message || message);
    } catch {
      message = response.statusText || message;
    }
    throw new Error(message);
  }

  return (await response.json()) as RuntimeBootstrap;
}
