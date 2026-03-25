export interface Env {
  DISPATCHER_PRODUCTION: DispatchNamespace;
  DISPATCHER_STAGING: DispatchNamespace;
  BACKEND_SHARED_SECRET: string;
}

type DispatchRequest = {
  worker_name: string;
  namespace: string;
  run_id: string;
  tenant_id: string;
  revision_id: string;
  limits?: { cpu_ms?: number; subrequests?: number };
  inputs?: unknown;
  config?: Record<string, unknown>;
  context?: Record<string, unknown>;
  entry_module_path?: string;
  source_files?: Array<{ path: string; content: string }>;
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const auth = request.headers.get("authorization") || "";
      if (env.BACKEND_SHARED_SECRET && auth !== `Bearer ${env.BACKEND_SHARED_SECRET}`) {
        return Response.json({ error: "unauthorized" }, { status: 401 });
      }

      const payload = (await request.json()) as DispatchRequest;
      const dispatcher = payload.namespace === "staging" ? env.DISPATCHER_STAGING : env.DISPATCHER_PRODUCTION;
      const worker = dispatcher.get(payload.worker_name, {}, {
        limits: {
          cpuMs: payload.limits?.cpu_ms,
          subRequests: payload.limits?.subrequests,
        },
      });

      const upstream = await worker.fetch("https://artifact.internal/execute", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const upstreamText = await upstream.text();
      let data: unknown = null;
      try {
        data = upstreamText ? JSON.parse(upstreamText) : null;
      } catch {
        return Response.json(
          {
            detail: {
              code: "DISPATCH_UPSTREAM_INVALID_JSON",
              message: "Dispatched worker returned a non-JSON response.",
              upstream_status: upstream.status,
              upstream_text: upstreamText.slice(0, 4000),
            },
          },
          { status: 500 },
        );
      }
      if (!upstream.ok) {
        const detail =
          data && typeof data === "object" && "detail" in data
            ? (data as { detail?: unknown }).detail
            : undefined;
        return Response.json(
          {
            detail: {
              code: "DISPATCH_UPSTREAM_ERROR",
              message: "Dispatched worker returned an error response.",
              upstream_status: upstream.status,
              upstream_detail: detail,
              upstream_text: upstreamText.slice(0, 4000),
            },
          },
          { status: 500 },
        );
      }
      return Response.json({ data });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return Response.json({ detail: { code: "DISPATCH_WORKER_FAILED", message } }, { status: 500 });
    }
  },
};
