export type RuntimeInput = {
  input?: string;
  messages?: Array<{ role: string; content: string }>;
  chat_id?: string;
  context?: Record<string, unknown>;
};

export type RuntimeEvent = {
  type: string;
  event?: string;
  data?: Record<string, unknown>;
  content?: string;
};

type RuntimeContext = {
  mode?: "builder-preview" | "published-runtime";
  appSlug?: string;
  basePath?: string;
  token?: string | null;
};

const TOKEN_PREFIX = "published-app-auth-token";

const getRuntimeContext = (): RuntimeContext => {
  if (typeof window === "undefined") return {};
  const candidate = (window as Window & { __APP_RUNTIME_CONTEXT?: RuntimeContext }).__APP_RUNTIME_CONTEXT;
  return candidate || {};
};

const resolveBasePath = (basePath?: string): string | null => {
  const ctx = getRuntimeContext();
  if (basePath) return basePath;
  if (ctx.basePath) return ctx.basePath;
  if (ctx.appSlug) return `/api/py/public/apps/${encodeURIComponent(ctx.appSlug)}`;
  return null;
};

const resolveToken = (): string | null => {
  const ctx = getRuntimeContext();
  if (ctx.token) return ctx.token;
  if (typeof window === "undefined" || !ctx.appSlug) return null;
  return window.localStorage.getItem(`${TOKEN_PREFIX}:${ctx.appSlug}`);
};

export const createRuntimeClient = (basePath?: string) => {
  return {
    async stream(input: RuntimeInput, onEvent: (event: RuntimeEvent) => void): Promise<{ chatId: string | null }> {
      const ctx = getRuntimeContext();
      if (ctx.mode === "builder-preview") {
        onEvent({
          type: "error",
          content: "Live runtime is unavailable in builder preview. Publish the app to test real agent responses.",
        });
        return { chatId: null };
      }

      const resolvedBasePath = resolveBasePath(basePath);
      if (!resolvedBasePath) {
        throw new Error("Runtime context is missing app slug/base path.");
      }

      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const token = resolveToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(`${resolvedBasePath}/chat/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify(input),
      });
      if (!response.ok) {
        let message = "Failed to stream runtime response";
        try {
          const data = await response.json();
          message = data.detail || data.message || message;
        } catch {
          message = response.statusText || message;
        }
        throw new Error(message);
      }

      const chatId = response.headers.get("X-Chat-ID");
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Streaming reader unavailable");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let splitIndex = buffer.indexOf("\n\n");
        while (splitIndex >= 0) {
          const raw = buffer.slice(0, splitIndex).trim();
          buffer = buffer.slice(splitIndex + 2);
          const dataLine = raw.split("\n").find((line) => line.startsWith("data: "));
          if (dataLine) {
            try {
              onEvent(JSON.parse(dataLine.slice(6)));
            } catch {
              // ignore invalid events
            }
          }
          splitIndex = buffer.indexOf("\n\n");
        }
      }

      return { chatId };
    },
  };
};
