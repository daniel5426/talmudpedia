export interface Env {
  BACKEND_SECRET_BROKER_URL: string;
  BACKEND_SHARED_SECRET: string;
}

type ProxyRequest = {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
  tenant_id?: string;
  run_id?: string;
  revision_id?: string;
  secret_capabilities?: string[];
  allowed_hosts?: string[];
};

function isAllowed(url: URL, allowedHosts: string[]): boolean {
  return allowedHosts.includes(url.host);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const payload = (await request.json()) as ProxyRequest;
    const target = new URL(payload.url);
    const allowedHosts = payload.allowed_hosts || [];
    if (!isAllowed(target, allowedHosts)) {
      return Response.json(
        {
          status: "blocked",
          events: [
            {
              event_type: "outbound_request_blocked",
              payload: { data: { url: target.toString(), host: target.host } },
            },
          ],
        },
        { status: 403 },
      );
    }

    const brokerResponse = await fetch(env.BACKEND_SECRET_BROKER_URL, {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.BACKEND_SHARED_SECRET}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        tenant_id: payload.tenant_id,
        run_id: payload.run_id,
        revision_id: payload.revision_id,
        secret_capabilities: payload.secret_capabilities || [],
        url: target.toString(),
      }),
    });
    const brokerData = (await brokerResponse.json()) as { inject_headers?: Record<string, string> };
    const headers = new Headers(payload.headers || {});
    for (const [key, value] of Object.entries(brokerData.inject_headers || {})) {
      headers.set(key, value);
    }
    const upstream = await fetch(target.toString(), {
      method: payload.method || "GET",
      headers,
      body: payload.body || undefined,
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: upstream.headers,
    });
  },
};
