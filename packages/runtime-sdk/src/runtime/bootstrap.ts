import type { RuntimeBootstrap } from "../core/types";

export type RuntimeBootstrapRequest = {
  apiBaseUrl?: string;
  appSlug?: string;
  revisionId?: string;
  previewToken?: string;
  fetchImpl?: typeof fetch;
};

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function resolveBootstrapPath(request: RuntimeBootstrapRequest): string {
  if (request.revisionId) {
    return `/public/apps/preview/revisions/${encodeURIComponent(request.revisionId)}/runtime/bootstrap`;
  }
  if (request.appSlug) {
    return `/public/apps/${encodeURIComponent(request.appSlug)}/runtime/bootstrap`;
  }
  throw new Error("Runtime bootstrap requires appSlug or revisionId.");
}

export async function fetchRuntimeBootstrap(request: RuntimeBootstrapRequest): Promise<RuntimeBootstrap> {
  const fetchImpl = request.fetchImpl || globalThis.fetch;
  if (!fetchImpl) {
    throw new Error("Runtime SDK requires fetch implementation.");
  }

  const base = trimTrailingSlash(request.apiBaseUrl || "/api/py");
  const path = resolveBootstrapPath(request);
  const url = `${base}${path}`;
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
