import { env } from "../_lib/embed.js";
import { json } from "../_lib/http.js";
import { ensureSession, setSelectedClient } from "../_lib/session.js";

export async function PATCH(request: Request): Promise<Response> {
  const headers = new Headers();
  const session = ensureSession(request, headers, env.SESSION_COOKIE_SECRET);
  const body = (await request.json().catch(() => null)) as { clientId?: string } | null;
  const requestedClientId = String(body?.clientId || "").trim();
  const matchedClient = session.availableClients.find((client) => client.id === requestedClientId);

  if (!matchedClient) {
    return json(
      { error: "clientId must match one of the demo clients." },
      { headers, status: 400 },
    );
  }

  setSelectedClient(request, headers, matchedClient.id);
  return json(
    {
      ...session,
      selectedClientId: matchedClient.id,
    },
    { headers },
  );
}
