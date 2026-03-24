export interface Env {
  BACKEND_SECRET_BROKER_URL: string;
  BACKEND_SHARED_SECRET: string;
  artifact_outbound_grant?: string;
  artifact_allowed_hosts?: string[];
}

function isAllowed(url: URL, allowedHosts: string[]): boolean {
  return allowedHosts.includes(url.host);
}

const CREDENTIAL_HEADER = "x-artifact-credential-id";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const credentialId = request.headers.get(CREDENTIAL_HEADER) || "";
    const grant = String(env.artifact_outbound_grant || "");
    if (!credentialId || !grant) {
      return Response.json({ detail: { message: "credential_id and grant are required" } }, { status: 400 });
    }
    const target = new URL(request.url);
    const allowedHosts = Array.isArray(env.artifact_allowed_hosts) ? env.artifact_allowed_hosts : [];
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
        grant,
        credential_id: credentialId,
        url: target.toString(),
      }),
    });
    if (!brokerResponse.ok) {
      return new Response(brokerResponse.body, {
        status: brokerResponse.status,
        headers: brokerResponse.headers,
      });
    }
    const brokerData = (await brokerResponse.json()) as { inject_headers?: Record<string, string> };
    const headers = new Headers(request.headers);
    headers.delete(CREDENTIAL_HEADER);
    for (const [key, value] of Object.entries(brokerData.inject_headers || {})) {
      headers.set(key, value);
    }
    const upstream = await fetch(new Request(request, { headers }));
    return new Response(upstream.body, {
      status: upstream.status,
      headers: upstream.headers,
    });
  },
};
