import express from "express";
import { EmbeddedAgentClient, type EmbeddedAgentRuntimeEvent } from "@agents24/embed-sdk";

const app = express();
app.use(express.json());

const client = new EmbeddedAgentClient({
  baseUrl: process.env.TALMUDPEDIA_BASE_URL || "",
  apiKey: process.env.TALMUDPEDIA_EMBED_API_KEY || "",
});

const agentId = process.env.TALMUDPEDIA_AGENT_ID || "";
const threadsByUser = new Map<string, string>();

app.post("/api/agent/chat", async (req, res, next) => {
  try {
    const userId = String(req.body.userId || "").trim();
    const input = String(req.body.input || "").trim();
    const existingThreadId = threadsByUser.get(userId);
    const events: EmbeddedAgentRuntimeEvent[] = [];

    const result = await client.streamAgent(
      agentId,
      {
        input,
        thread_id: existingThreadId,
        external_user_id: userId,
      },
      (event) => {
        events.push(event);
      },
    );

    if (result.threadId) {
      threadsByUser.set(userId, result.threadId);
    }

    res.json({
      threadId: result.threadId,
      events,
    });
  } catch (error) {
    next(error);
  }
});

app.get("/api/agent/threads", async (req, res, next) => {
  try {
    const userId = String(req.query.userId || "").trim();
    const threads = await client.listAgentThreads(agentId, {
      externalUserId: userId,
    });
    res.json(threads);
  } catch (error) {
    next(error);
  }
});

app.get("/api/agent/threads/:threadId", async (req, res, next) => {
  try {
    const userId = String(req.query.userId || "").trim();
    const thread = await client.getAgentThread(agentId, req.params.threadId, {
      externalUserId: userId,
    });
    res.json(thread);
  } catch (error) {
    next(error);
  }
});

app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  const message = error instanceof Error ? error.message : "Unexpected server error";
  res.status(500).json({ error: message });
});

const port = Number(process.env.PORT || 3001);
app.listen(port, () => {
  console.log(`Embed SDK example server listening on http://localhost:${port}`);
});
