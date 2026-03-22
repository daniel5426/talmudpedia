import { embedClient, env } from "../../_lib/embed.js";
import { toEmbedErrorPayload } from "../../_lib/errors.js";
import { json } from "../../_lib/http.js";
import { ensureSession } from "../../_lib/session.js";

export async function POST(request: Request): Promise<Response> {
  const headers = new Headers();
  const session = ensureSession(request, headers, env.SESSION_COOKIE_SECRET);

  try {
    const formData = await request.formData();
    const threadId = String(formData.get("threadId") || "").trim() || undefined;
    const files = formData
      .getAll("files")
      .filter((entry): entry is File => entry instanceof File);

    if (files.length === 0) {
      return json({ error: "At least one file is required." }, { headers, status: 400 });
    }

    return json(
      await embedClient.uploadAgentAttachments(env.TALMUDPEDIA_AGENT_ID, {
        externalUserId: session.user.id,
        threadId,
        files,
      }),
      { headers },
    );
  } catch (error) {
    const payload = toEmbedErrorPayload(error);
    return json(payload, { headers, status: payload.status });
  }
}
