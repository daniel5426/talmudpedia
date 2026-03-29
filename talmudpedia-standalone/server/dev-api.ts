import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import * as uploadRoute from "../api/agent/attachments/upload.js";
import * as chatStreamRoute from "../api/agent/chat/stream.js";
import * as threadRoute from "../api/agent/threads/[threadId].js";
import * as threadsRoute from "../api/agent/threads/index.js";
import * as sessionClientRoute from "../api/session/client.js";
import * as sessionRoute from "../api/session.js";

type RouteHandler = (request: Request) => Promise<Response>;
type RouteModule = Record<string, unknown>;

const PORT = Number(process.env.STANDALONE_API_PORT || 3001);

const routes: Array<{
  match: (pathname: string) => boolean;
  module: RouteModule;
}> = [
  { match: (pathname) => pathname === "/api/session", module: sessionRoute },
  { match: (pathname) => pathname === "/api/session/client", module: sessionClientRoute },
  { match: (pathname) => pathname === "/api/agent/threads", module: threadsRoute },
  {
    match: (pathname) =>
      pathname.startsWith("/api/agent/threads/") && pathname.length > "/api/agent/threads/".length,
    module: threadRoute,
  },
  { match: (pathname) => pathname === "/api/agent/attachments/upload", module: uploadRoute },
  { match: (pathname) => pathname === "/api/agent/chat/stream", module: chatStreamRoute },
];

function toRequest(req: IncomingMessage): Request {
  const origin = `http://${req.headers.host || `127.0.0.1:${PORT}`}`;
  const url = new URL(req.url || "/", origin);
  const headers = new Headers();

  for (const [key, value] of Object.entries(req.headers)) {
    if (Array.isArray(value)) {
      for (const entry of value) {
        headers.append(key, entry);
      }
      continue;
    }
    if (typeof value === "string") {
      headers.set(key, value);
    }
  }

  const method = (req.method || "GET").toUpperCase();
  const init: RequestInit & { duplex?: "half" } = {
    method,
    headers,
  };

  if (method !== "GET" && method !== "HEAD") {
    init.body = req as unknown as BodyInit;
    init.duplex = "half";
  }

  return new Request(url, init);
}

function applyHeaders(res: ServerResponse, response: Response): void {
  res.statusCode = response.status;
  res.statusMessage = response.statusText;

  for (const [key, value] of response.headers.entries()) {
    if (key.toLowerCase() === "set-cookie") {
      continue;
    }
    res.setHeader(key, value);
  }

  if (typeof response.headers.getSetCookie === "function") {
    const cookies = response.headers.getSetCookie();
    if (cookies.length > 0) {
      res.setHeader("set-cookie", cookies);
    }
  } else {
    const cookie = response.headers.get("set-cookie");
    if (cookie) {
      res.setHeader("set-cookie", cookie);
    }
  }
}

async function writeResponse(res: ServerResponse, response: Response): Promise<void> {
  applyHeaders(res, response);

  if (!response.body) {
    res.end();
    return;
  }

  const reader = response.body.getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    res.write(Buffer.from(value));
  }

  res.end();
}

async function handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
  try {
    const request = toRequest(req);
    const pathname = new URL(request.url).pathname;
    const route = routes.find((candidate) => candidate.match(pathname));

    if (!route) {
      res.statusCode = 404;
      res.setHeader("content-type", "application/json; charset=utf-8");
      res.end(JSON.stringify({ error: "Not found" }));
      return;
    }

    const method = (req.method || "GET").toUpperCase();
    const handler = route.module[method];
    if (typeof handler !== "function") {
      res.statusCode = 405;
      res.setHeader("content-type", "application/json; charset=utf-8");
      res.end(JSON.stringify({ error: `Method ${method} not allowed` }));
      return;
    }

    await writeResponse(res, await (handler as RouteHandler)(request));
  } catch (error) {
    res.statusCode = 500;
    res.setHeader("content-type", "application/json; charset=utf-8");
    res.end(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Unexpected local API error",
      }),
    );
  }
}

createServer((req, res) => {
  void handle(req, res);
}).listen(PORT, "127.0.0.1", () => {
  console.log(`Talmudpedia standalone local API listening on http://127.0.0.1:${PORT}`);
});
