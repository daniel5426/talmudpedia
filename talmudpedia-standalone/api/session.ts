import { loadSessionEnv } from "./_lib/env.js";
import { json, noContent } from "./_lib/http.js";
import { clearSession, ensureSession } from "./_lib/session.js";

const sessionEnv = loadSessionEnv();

export async function GET(request: Request): Promise<Response> {
  const headers = new Headers();
  const session = ensureSession(request, headers, sessionEnv.SESSION_COOKIE_SECRET);
  return json(session, { headers });
}

export async function DELETE(request: Request): Promise<Response> {
  const headers = new Headers();
  clearSession(request, headers);
  return noContent({ headers });
}
