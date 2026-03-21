import { embedClient, env } from "../../_lib/embed.js";
import { toEmbedErrorPayload } from "../../_lib/errors.js";
import { getPathParam, json } from "../../_lib/http.js";
import { ensureSession } from "../../_lib/session.js";

function readThreadId(request: Request): string {
  return getPathParam(request, "/api/agent/threads/");
}

export async function GET(request: Request): Promise<Response> {
  const headers = new Headers();
  const session = ensureSession(request, headers, env.SESSION_COOKIE_SECRET);

  try {
    return json(
      await embedClient.getAgentThread(env.TALMUDPEDIA_AGENT_ID, readThreadId(request), {
        externalUserId: session.userId,
      }),
      { headers },
    );
  } catch (error) {
    const payload = toEmbedErrorPayload(error);
    return json(payload, { headers, status: payload.status });
  }
}

export async function DELETE(request: Request): Promise<Response> {
  const headers = new Headers();
  const session = ensureSession(request, headers, env.SESSION_COOKIE_SECRET);

  try {
    return json(
      await embedClient.deleteAgentThread(env.TALMUDPEDIA_AGENT_ID, readThreadId(request), {
        externalUserId: session.userId,
      }),
      { headers },
    );
  } catch (error) {
    const payload = toEmbedErrorPayload(error);
    return json(payload, { headers, status: payload.status });
  }
}
