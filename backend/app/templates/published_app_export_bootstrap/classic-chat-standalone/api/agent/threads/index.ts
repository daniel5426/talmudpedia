import { embedClient, env } from "../../_lib/embed.js";
import { toEmbedErrorPayload } from "../../_lib/errors.js";
import { json } from "../../_lib/http.js";
import { ensureSession } from "../../_lib/session.js";

export async function GET(request: Request): Promise<Response> {
  const headers = new Headers();
  const session = ensureSession(request, headers, env.SESSION_COOKIE_SECRET);

  try {
    return json(
      await embedClient.listAgentThreads(env.TALMUDPEDIA_AGENT_ID, {
        externalUserId: session.user.id,
      }),
      { headers },
    );
  } catch (error) {
    const payload = toEmbedErrorPayload(error);
    return json(payload, { headers, status: payload.status });
  }
}
