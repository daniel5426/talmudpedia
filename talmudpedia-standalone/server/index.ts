import cookieParser from "cookie-parser";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { EmbeddedAgentClient, EmbeddedAgentSDKError } from "@agents24/embed-sdk";

import { loadEnv } from "./env.js";
import { clearSession, ensureSession } from "./session.js";

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

function normalizeBaseUrl(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

app.get("/api/session", (req, res) => {
  res.json(getSession(req, res));
});

app.delete("/api/session", (_req, res) => {
  clearSession(res);
  res.status(204).end();
});

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

app.post("/api/agent/chat/stream", async (req, res) => {
  const session = getSession(req, res);
  const input = String(req.body?.input || "").trim();
  const threadId = String(req.body?.threadId || "").trim() || undefined;

  if (!input) {
    res.status(400).json({ error: "input is required" });
    return;
  }

  try {
    const upstreamResponse = await fetch(
      `${normalizeBaseUrl(env.TALMUDPEDIA_BASE_URL)}/public/embed/agents/${env.TALMUDPEDIA_AGENT_ID}/chat/stream`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.TALMUDPEDIA_EMBED_API_KEY}`,
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          input,
          thread_id: threadId,
          external_user_id: session.userId,
        }),
      },
    );

    if (!upstreamResponse.ok || !upstreamResponse.body) {
      const text = await upstreamResponse.text();
      res.status(upstreamResponse.status).json({
        error: text || "Failed to connect to the embedded-agent stream endpoint.",
      });
      return;
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");
    const upstreamThreadId = upstreamResponse.headers.get("X-Thread-ID");
    if (upstreamThreadId) {
      res.setHeader("X-Thread-ID", upstreamThreadId);
    }
    res.flushHeaders?.();

    const reader = upstreamResponse.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) {
        res.write(Buffer.from(value));
      }
    }

    res.end();
  } catch (error) {
    const payload = toErrorPayload(error);
    res.status(payload.status);
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");
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
    res.end();
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
