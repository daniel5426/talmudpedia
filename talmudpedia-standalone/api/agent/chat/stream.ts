import { embedClient, env } from "../../_lib/embed.js";
import { listDemoClients } from "../../_lib/demo-clients.js";
import { toEmbedErrorPayload } from "../../_lib/errors.js";
import { json } from "../../_lib/http.js";
import { ensureSession, setSelectedClient } from "../../_lib/session.js";

type StreamRequestBody = {
  input?: string;
  threadId?: string;
  attachmentIds?: string[];
  clientId?: string;
};

type StandaloneRuntimeEvent = {
  version: "run-stream.v2";
  seq: number;
  ts: string;
  event: string;
  run_id: string;
  stage: string;
  payload: Record<string, unknown>;
  diagnostics: Array<Record<string, unknown>>;
};

export const maxDuration = 60;

function encodeSse(payload: unknown): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(payload)}\n\n`);
}

function buildFailureEvent(message: string): StandaloneRuntimeEvent {
  return {
    version: "run-stream.v2",
    seq: Number.MAX_SAFE_INTEGER,
    ts: new Date().toISOString(),
    event: "run.failed",
    run_id: "standalone-bff-error",
    stage: "run",
    payload: { error: message },
    diagnostics: [{ message }],
  };
}

export async function POST(request: Request): Promise<Response> {
  const responseHeaders = new Headers();
  const session = ensureSession(request, responseHeaders, env.SESSION_COOKIE_SECRET);
  const body = (await request.json().catch(() => null)) as StreamRequestBody | null;
  const input = String(body?.input || "").trim();
  const threadId = String(body?.threadId || "").trim() || undefined;
  const attachmentIds = Array.isArray(body?.attachmentIds)
    ? body.attachmentIds.map((value) => String(value || "").trim()).filter(Boolean)
    : [];
  const requestedClientId = String(body?.clientId || session.selectedClientId || "").trim();

  if (!input && attachmentIds.length === 0) {
    return json({ error: "input or attachmentIds is required" }, { headers: responseHeaders, status: 400 });
  }

  if (!requestedClientId) {
    return json({ error: "clientId is required" }, { headers: responseHeaders, status: 400 });
  }

  const matchedClient = listDemoClients().find((client) => client.id === requestedClientId);
  if (!matchedClient) {
    return json(
      { error: "clientId must match one of the demo clients." },
      { headers: responseHeaders, status: 400 },
    );
  }

  setSelectedClient(request, responseHeaders, matchedClient.id);

  const stream = new TransformStream<Uint8Array, Uint8Array>();
  const writer = stream.writable.getWriter();

  let headerThreadId: string | null = null;
  let firstEventResolved = false;
  let resolveFirstEvent!: () => void;
  const firstEvent = new Promise<void>((resolve) => {
    resolveFirstEvent = resolve;
  });

  void embedClient
    .streamAgent(
      env.TALMUDPEDIA_AGENT_ID,
      {
        input: input || undefined,
        messages: [
          {
            role: "system",
            content:
              `Selected demo client context: client_id=${matchedClient.id}; ` +
              `client_name=${matchedClient.name}; sector=${matchedClient.sector}; ` +
              `base_currency=${matchedClient.baseCurrency}. ` +
              "Treat this as authoritative client scope for the current turn unless the user explicitly asks to switch clients.",
          },
        ],
        attachment_ids: attachmentIds,
        thread_id: threadId,
        external_user_id: session.userId,
        metadata: {
          client_id: matchedClient.id,
          client_name: matchedClient.name,
          sector: matchedClient.sector,
          base_currency: matchedClient.baseCurrency,
        },
      },
      async (event) => {
        if (!headerThreadId && event.event === "run.accepted") {
          const acceptedThreadId = event.payload.thread_id;
          if (typeof acceptedThreadId === "string" && acceptedThreadId.trim()) {
            headerThreadId = acceptedThreadId;
          }
        }
        if (!firstEventResolved) {
          firstEventResolved = true;
          resolveFirstEvent();
        }
        await writer.write(encodeSse(event));
      },
    )
    .catch(async (error) => {
      const payload = toEmbedErrorPayload(error);
      if (!firstEventResolved) {
        firstEventResolved = true;
        resolveFirstEvent();
      }
      await writer.write(encodeSse(buildFailureEvent(payload.error)));
    })
    .finally(async () => {
      await writer.close();
    });

  await Promise.race([
    firstEvent,
    new Promise<void>((resolve) => {
      setTimeout(resolve, 150);
    }),
  ]);

  responseHeaders.set("Content-Type", "text/event-stream; charset=utf-8");
  responseHeaders.set("Cache-Control", "no-cache, no-transform");
  responseHeaders.set("X-Accel-Buffering", "no");

  if (headerThreadId) {
    responseHeaders.set("X-Thread-ID", headerThreadId);
  }

  return new Response(stream.readable, {
    headers: responseHeaders,
  });
}
