import cookieParser from "cookie-parser";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { EmbeddedAgentClient, EmbeddedAgentSDKError } from "@agents24/embed-sdk";

import { loadEnv } from "./env.js";
import { createPricoDemoRouter } from "./prico-demo/router.js";
import { clearSession, ensureSession, setSelectedClient } from "./session.js";

const env = loadEnv();
const app = express();
const client = new EmbeddedAgentClient({
  baseUrl: env.TALMUDPEDIA_BASE_URL,
  apiKey: env.TALMUDPEDIA_EMBED_API_KEY,
});
const isProduction = process.env.NODE_ENV === "production";
const currentDir = path.dirname(fileURLToPath(import.meta.url));
const staticDir = path.resolve(currentDir, "../dist");

app.use(cookieParser());
app.use(express.json());

function getSession(req: express.Request, res: express.Response) {
  return ensureSession(req, res, env.SESSION_COOKIE_SECRET);
}

function toErrorPayload(error: unknown) {
  if (error instanceof EmbeddedAgentSDKError) {
    return {
      error: error.message,
      kind: error.kind,
      status: error.status ?? 502,
      details: error.details ?? null,
    };
  }
  return {
    error: error instanceof Error ? error.message : "Unexpected server error",
    kind: "internal",
    status: 500,
    details: null,
  };
}

function writeSseFrame(res: express.Response, payload: unknown): void {
  res.write(`data: ${JSON.stringify(payload)}\n\n`);
}

async function parseMultipartForm(req: express.Request): Promise<FormData> {
  const headers = new Headers();
  for (const [key, value] of Object.entries(req.headers)) {
    if (Array.isArray(value)) {
      headers.set(key, value.join(", "));
      continue;
    }
    if (typeof value === "string") {
      headers.set(key, value);
    }
  }
  const origin = `${req.protocol}://${req.get("host") || "localhost"}`;
  const request = new Request(`${origin}${req.originalUrl}`, {
    method: req.method,
    headers,
    body: req,
    duplex: "half",
  } as RequestInit & { duplex: "half" });
  return request.formData();
}

app.get("/api/session", (req, res) => {
  res.json(getSession(req, res));
});

app.patch("/api/session/client", (req, res) => {
  const requestedClientId = String(req.body?.clientId || "").trim();
  const session = getSession(req, res);
  const matchedClient = session.availableClients.find((client) => client.id === requestedClientId);
  if (!matchedClient) {
    res.status(400).json({ error: "clientId must match one of the demo clients." });
    return;
  }

  setSelectedClient(res, matchedClient.id);
  res.json({
    ...session,
    selectedClientId: matchedClient.id,
  });
});

app.delete("/api/session", (_req, res) => {
  clearSession(res);
  res.status(204).end();
});

app.use("/api/prico-tools", createPricoDemoRouter());

app.get("/api/agent/threads", async (req, res) => {
  try {
    const session = getSession(req, res);
    const payload = await client.listAgentThreads(env.TALMUDPEDIA_AGENT_ID, {
      externalUserId: session.userId,
    });
    res.json(payload);
  } catch (error) {
    const payload = toErrorPayload(error);
    res.status(payload.status).json(payload);
  }
});

app.get("/api/agent/threads/:threadId", async (req, res) => {
  try {
    const session = getSession(req, res);
    const payload = await client.getAgentThread(
      env.TALMUDPEDIA_AGENT_ID,
      req.params.threadId,
      { externalUserId: session.userId },
    );
    res.json(payload);
  } catch (error) {
    const payload = toErrorPayload(error);
    res.status(payload.status).json(payload);
  }
});

app.delete("/api/agent/threads/:threadId", async (req, res) => {
  try {
    const session = getSession(req, res);
    const payload = await client.deleteAgentThread(
      env.TALMUDPEDIA_AGENT_ID,
      req.params.threadId,
      { externalUserId: session.userId },
    );
    res.json(payload);
  } catch (error) {
    const payload = toErrorPayload(error);
    res.status(payload.status).json(payload);
  }
});

app.post("/api/agent/attachments/upload", async (req, res) => {
  try {
    const session = getSession(req, res);
    const formData = await parseMultipartForm(req);
    const threadId = String(formData.get("threadId") || "").trim() || undefined;
    const files = formData
      .getAll("files")
      .filter((entry): entry is File => entry instanceof File);

    if (files.length === 0) {
      res.status(400).json({ error: "At least one file is required." });
      return;
    }

    const payload = await client.uploadAgentAttachments(env.TALMUDPEDIA_AGENT_ID, {
      externalUserId: session.userId,
      threadId,
      files,
    });
    res.json(payload);
  } catch (error) {
    const payload = toErrorPayload(error);
    res.status(payload.status).json(payload);
  }
});

app.post("/api/agent/chat/stream", async (req, res) => {
  const session = getSession(req, res);
  const input = String(req.body?.input || "").trim();
  const threadId = String(req.body?.threadId || "").trim() || undefined;
  const attachmentIds = Array.isArray(req.body?.attachmentIds)
    ? req.body.attachmentIds
        .map((value: unknown) => String(value || "").trim())
        .filter(Boolean)
    : [];
  const requestedClientId = String(req.body?.clientId || session.selectedClientId || "").trim();

  if (!input && attachmentIds.length === 0) {
    res.status(400).json({ error: "input or attachmentIds is required" });
    return;
  }
  if (!requestedClientId) {
    res.status(400).json({ error: "clientId is required" });
    return;
  }

  const matchedClient = session.availableClients.find((client) => client.id === requestedClientId);
  if (!matchedClient) {
    res.status(400).json({ error: "clientId must match one of the demo clients." });
    return;
  }

  setSelectedClient(res, matchedClient.id);

  try {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");

    let didFlushHeaders = false;
    await client.streamAgent(
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
        if (!didFlushHeaders) {
          const acceptedThreadId = event.event === "run.accepted" ? event.payload.thread_id : null;
          if (typeof acceptedThreadId === "string" && acceptedThreadId.trim()) {
            res.setHeader("X-Thread-ID", acceptedThreadId);
          }
          res.flushHeaders?.();
          didFlushHeaders = true;
        }
        writeSseFrame(res, event);
      },
    );

    if (!didFlushHeaders) {
      res.flushHeaders?.();
      didFlushHeaders = true;
    }

    res.end();
  } catch (error) {
    const payload = toErrorPayload(error);
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");
    res.flushHeaders?.();
    writeSseFrame(res, {
      version: "run-stream.v2",
      seq: Number.MAX_SAFE_INTEGER,
      ts: new Date().toISOString(),
      event: "run.failed",
      run_id: "standalone-bff-error",
      stage: "run",
      payload: { error: payload.error },
      diagnostics: [{ message: payload.error }],
    });
    if (!res.writableEnded) {
      res.end();
    }
  }
});

if (isProduction) {
  app.use(express.static(staticDir));
  app.get(/^(?!\/api\/).*/, (_req, res) => {
    res.sendFile(path.join(staticDir, "index.html"));
  });
}

app.listen(env.PORT, () => {
  console.log(`Talmudpedia standalone server listening on http://localhost:${env.PORT}`);
});
