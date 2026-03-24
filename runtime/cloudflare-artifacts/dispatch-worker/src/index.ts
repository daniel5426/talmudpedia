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
  allowed_hosts?: string[];
  outbound_grant?: string;
  outbound_base_url?: string;
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
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
      outbound: {
        artifact_outbound_grant: payload.outbound_grant || "",
        artifact_allowed_hosts: payload.allowed_hosts || [],
      },
    });

    const upstream = await worker.fetch("https://artifact.internal/execute", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await upstream.json();
    return Response.json({ data });
  },
};
