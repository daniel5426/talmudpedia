export type RuntimeInput = {
  input?: string;
  messages?: Array<{ role: string; content: string }>;
  thread_id?: string;
  context?: Record<string, unknown>;
};

export type RuntimeEvent = {
  type: string;
  event?: string;
  payload?: Record<string, unknown>;
  content?: string;
};

type RuntimeContext = {
  mode?: "builder-preview" | "published-runtime";
  appSlug?: string;
  basePath?: string;
  token?: string | null;
  previewToken?: string | null;
};

const getRuntimeContextFromQuery = (): RuntimeContext => {
  if (typeof window === "undefined") return {};
  const query = new URLSearchParams(window.location.search);
  const mode = query.get("runtime_mode");
  const appSlug = query.get("runtime_app_slug");
  const basePath = query.get("runtime_base_path");
  const token = query.get("runtime_token");
  const previewToken = query.get("runtime_preview_token") || query.get("preview_token");
  return {
    mode: mode === "builder-preview" || mode === "published-runtime" ? mode : undefined,
    appSlug: appSlug || undefined,
    basePath: basePath || undefined,
    token: token || null,
    previewToken: previewToken || null,
  };
};

const getRuntimeContext = (): RuntimeContext => {
  if (typeof window === "undefined") return {};
  const queryContext = getRuntimeContextFromQuery();
  const candidate = (window as Window & { __APP_RUNTIME_CONTEXT?: RuntimeContext }).__APP_RUNTIME_CONTEXT;
  return { ...queryContext, ...(candidate || {}) };
};

const resolveBasePath = (): string | null => {
  const ctx = getRuntimeContext();
  if (ctx.basePath) return ctx.basePath;
  if (ctx.appSlug) return `/api/py/public/apps/${encodeURIComponent(ctx.appSlug)}`;
  return null;
};

const resolveToken = (): string | null => {
  const ctx = getRuntimeContext();
  if (ctx.token) return ctx.token;
  // Published runtime auth uses same-origin HttpOnly cookies via the host runtime gateway.
  return null;
};

const resolvePreviewToken = (): string | null => {
  const ctx = getRuntimeContext();
  if (ctx.previewToken) return ctx.previewToken;
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("preview_token");
};

const buildStreamUrl = (basePath: string): string => {
  const base = `${basePath}/chat/stream`;
  const previewToken = resolvePreviewToken();
  if (!previewToken || !basePath.includes("/preview/revisions/")) {
    return base;
  }
  const connector = base.includes("?") ? "&" : "?";
  return `${base}${connector}preview_token=${encodeURIComponent(previewToken)}`;
};

export const createRuntimeClient = () => {
  return {
    async stream(input: RuntimeInput, onEvent: (event: RuntimeEvent) => void): Promise<{ threadId: string | null }> {
      const basePath = resolveBasePath();
      if (!basePath) {
        throw new Error("Runtime context is missing app slug/base path.");
      }

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      const token = resolveToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(buildStreamUrl(basePath), {
        method: "POST",
        headers,
        body: JSON.stringify(input),
      });
      if (!response.ok) {
        throw new Error(`Runtime stream failed: ${response.status}`);
      }

      const threadId = response.headers.get("X-Thread-ID");
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
          const line = raw.split("\n").find((item) => item.startsWith("data: "));
          if (line) {
            try {
              onEvent(JSON.parse(line.slice(6)) as RuntimeEvent);
            } catch {
              // Ignore malformed events.
            }
          }
          splitIndex = buffer.indexOf("\n\n");
        }
      }

      return { threadId };
    },
  };
};
