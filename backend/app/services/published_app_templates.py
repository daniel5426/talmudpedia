from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class PublishedAppTemplate:
    key: str
    name: str
    description: str
    thumbnail: str
    tags: List[str]
    entry_file: str
    style_tokens: Dict[str, str]


def _build_main_file() -> str:
    return """import React from \"react\";
import { createRoot } from \"react-dom/client\";
import { App } from \"./App\";
import \"./styles.css\";

const rootElement = document.getElementById(\"root\");
if (!rootElement) {
  throw new Error(\"Missing #root element\");
}
createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
"""


def _build_theme_file(tokens: Dict[str, str]) -> str:
    return f"""export const theme = {{
  fontDisplay: \"{tokens['fontDisplay']}\",
  fontBody: \"{tokens['fontBody']}\",
  bg: \"{tokens['bg']}\",
  panel: \"{tokens['panel']}\",
  border: \"{tokens['border']}\",
  accent: \"{tokens['accent']}\",
  accentSoft: \"{tokens['accentSoft']}\",
  text: \"{tokens['text']}\",
  muted: \"{tokens['muted']}\",
}};
"""


def _build_runtime_sdk_file() -> str:
    return """export type RuntimeInput = {
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
  mode?: \"builder-preview\" | \"published-runtime\";
  appSlug?: string;
  basePath?: string;
  token?: string | null;
};

const TOKEN_PREFIX = \"published-app-auth-token\";

const getRuntimeContext = (): RuntimeContext => {
  if (typeof window === \"undefined\") return {};
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
  if (typeof window === \"undefined\" || !ctx.appSlug) return null;
  return window.localStorage.getItem(`${TOKEN_PREFIX}:${ctx.appSlug}`);
};

export const createRuntimeClient = (basePath?: string) => {
  return {
    async stream(input: RuntimeInput, onEvent: (event: RuntimeEvent) => void): Promise<{ chatId: string | null }> {
      const ctx = getRuntimeContext();
      if (ctx.mode === \"builder-preview\") {
        onEvent({
          type: \"error\",
          content: \"Live runtime is unavailable in builder preview. Publish the app to test real agent responses.\",
        });
        return { chatId: null };
      }

      const resolvedBasePath = resolveBasePath(basePath);
      if (!resolvedBasePath) {
        throw new Error(\"Runtime context is missing app slug/base path.\");
      }

      const headers: Record<string, string> = { \"Content-Type\": \"application/json\" };
      const token = resolveToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(`${resolvedBasePath}/chat/stream`, {
        method: \"POST\",
        headers,
        body: JSON.stringify(input),
      });
      if (!response.ok) {
        let message = \"Failed to stream runtime response\";
        try {
          const data = await response.json();
          message = data.detail || data.message || message;
        } catch {
          message = response.statusText || message;
        }
        throw new Error(message);
      }

      const chatId = response.headers.get(\"X-Chat-ID\");
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error(\"Streaming reader unavailable\");
      }

      const decoder = new TextDecoder();
      let buffer = \"\";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let splitIndex = buffer.indexOf(\"\\n\\n\");
        while (splitIndex >= 0) {
          const raw = buffer.slice(0, splitIndex).trim();
          buffer = buffer.slice(splitIndex + 2);
          const dataLine = raw.split(\"\\n\").find((line) => line.startsWith(\"data: \"));
          if (dataLine) {
            try {
              onEvent(JSON.parse(dataLine.slice(6)));
            } catch {
              // ignore invalid events
            }
          }
          splitIndex = buffer.indexOf(\"\\n\\n\");
        }
      }

      return { chatId };
    },
  };
};
"""


def _build_default_chat_template_files(tokens: Dict[str, str]) -> Dict[str, str]:
    return {
        "src/main.tsx": _build_main_file(),
        "src/theme.ts": _build_theme_file(tokens),
        "src/runtime-sdk.ts": _build_runtime_sdk_file(),
        "src/App.tsx": """import { useMemo, useState } from \"react\";
import { createRuntimeClient, type RuntimeEvent } from \"./runtime-sdk\";
import { theme } from \"./theme\";

type Message = { role: \"user\" | \"assistant\"; content: string };

const extractTokenChunk = (event: RuntimeEvent): string => {
  if (event.event === \"token\" && typeof event.data?.content === \"string\") {
    return event.data.content;
  }
  if (event.type === \"token\" && typeof event.content === \"string\") {
    return event.content;
  }
  return \"\";
};

export function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState(\"\");
  const [isSending, setIsSending] = useState(false);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const runtime = useMemo(() => createRuntimeClient(), []);

  const title = useMemo(() => \"Your AI App\", []);

  const submit = async () => {
    const text = input.trim();
    if (!text || isSending) return;

    setRuntimeError(null);
    setIsSending(true);
    setInput(\"\");
    setMessages((prev) => [...prev, { role: \"user\", content: text }, { role: \"assistant\", content: \"\" }]);

    const applyEvent = (event: RuntimeEvent) => {
      const chunk = extractTokenChunk(event);
      if (event.type === \"error\") {
        setRuntimeError(event.content || \"Runtime streaming error\");
      }
      if (!chunk) return;
      setMessages((prev) => {
        const next = [...prev];
        const lastIndex = next.length - 1;
        if (lastIndex >= 0 && next[lastIndex].role === \"assistant\") {
          next[lastIndex] = {
            ...next[lastIndex],
            content: `${next[lastIndex].content}${chunk}`,
          };
        }
        return next;
      });
    };

    try {
      const result = await runtime.stream(
        { input: text, chat_id: chatId || undefined },
        applyEvent,
      );
      if (result.chatId) {
        setChatId(result.chatId);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : \"Failed to stream runtime response\";
      setRuntimeError(message);
      setMessages((prev) => {
        const next = [...prev];
        const lastIndex = next.length - 1;
        if (lastIndex >= 0 && next[lastIndex].role === \"assistant\") {
          next[lastIndex] = { role: \"assistant\", content: message };
          return next;
        }
        return [...next, { role: \"assistant\", content: message }];
      });
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div
      style={{
        fontFamily: theme.fontBody,
        background: theme.bg,
        color: theme.text,
        height: \"100vh\",
        display: \"flex\",
      }}
    >
      <aside
        style={{
          width: sidebarOpen ? 240 : 0,
          transition: \"width 180ms ease\",
          overflow: \"hidden\",
          borderRight: `1px solid ${theme.border}`,
          background: theme.panel,
          padding: sidebarOpen ? 16 : 0,
        }}
      >
        <h3 style={{ margin: 0, fontFamily: theme.fontDisplay }}>History</h3>
        <p style={{ color: theme.muted, fontSize: 12 }}>Connect persisted chats here.</p>
      </aside>

      <main style={{ flex: 1, display: \"flex\", flexDirection: \"column\" }}>
        <header
          style={{
            height: 56,
            borderBottom: `1px solid ${theme.border}`,
            display: \"flex\",
            alignItems: \"center\",
            justifyContent: \"space-between\",
            padding: \"0 16px\",
            background: theme.panel,
          }}
        >
          <button onClick={() => setSidebarOpen((v) => !v)}>Sidebar</button>
          <h1 style={{ margin: 0, fontSize: 16, fontFamily: theme.fontDisplay }}>{title}</h1>
          <button onClick={() => setSourceOpen((v) => !v)}>Source</button>
        </header>

        <section style={{ flex: 1, overflow: \"auto\", padding: 20 }}>
          {messages.length === 0 ? (
            <p style={{ color: theme.muted }}>Start a conversation.</p>
          ) : (
            messages.map((message, idx) => (
              <div key={`${message.role}-${idx}`} style={{ marginBottom: 12, textAlign: message.role === \"user\" ? \"right\" : \"left\" }}>
                <span
                  style={{
                    display: \"inline-block\",
                    background: message.role === \"user\" ? theme.accent : theme.panel,
                    color: message.role === \"user\" ? \"#fff\" : theme.text,
                    padding: \"10px 12px\",
                    borderRadius: 12,
                    maxWidth: \"75%\",
                    border: `1px solid ${theme.border}`,
                  }}
                >
                  {message.content}
                </span>
              </div>
            ))
          )}
        </section>

        {runtimeError && (
          <div
            style={{
              borderTop: `1px solid ${theme.border}`,
              background: theme.accentSoft,
              color: theme.text,
              padding: \"8px 12px\",
              fontSize: 12,
            }}
          >
            {runtimeError}
          </div>
        )}

        <footer style={{ borderTop: `1px solid ${theme.border}`, padding: 12, display: \"flex\", gap: 8 }}>
          <input
            style={{
              flex: 1,
              border: `1px solid ${theme.border}`,
              borderRadius: 10,
              padding: \"10px 12px\",
              background: theme.panel,
              color: theme.text,
            }}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder=\"Send a message\"
          />
          <button
            onClick={submit}
            disabled={isSending}
            style={{
              borderRadius: 10,
              border: \"none\",
              background: theme.accent,
              color: \"white\",
              padding: \"10px 14px\",
              opacity: isSending ? 0.7 : 1,
            }}
          >
            {isSending ? \"Sending...\" : \"Send\"}
          </button>
        </footer>
      </main>

      <aside
        style={{
          width: sourceOpen ? 320 : 0,
          transition: \"width 180ms ease\",
          overflow: \"hidden\",
          borderLeft: `1px solid ${theme.border}`,
          background: theme.panel,
          padding: sourceOpen ? 16 : 0,
        }}
      >
        <h3 style={{ margin: 0, fontFamily: theme.fontDisplay }}>Source Viewer</h3>
        <p style={{ color: theme.muted, fontSize: 12 }}>
          Keep this pane for retrieval results or citations.
        </p>
      </aside>
    </div>
  );
}
""",
        "src/styles.css": """:root {
  color-scheme: light;
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  font-family: var(--font-body, system-ui, sans-serif);
}
button {
  cursor: pointer;
}
""",
    }


def _build_layout_shell_template_files(tokens: Dict[str, str]) -> Dict[str, str]:
    return {
        "src/main.tsx": _build_main_file(),
        "src/theme.ts": _build_theme_file(tokens),
        "src/runtime-sdk.ts": _build_runtime_sdk_file(),
        "src/App.tsx": """import { useEffect, useMemo, useState } from \"react\";
import { LayoutShell } from \"./components/layout/LayoutShell\";
import type { ChatMessage, SourceItem } from \"./components/layout/types\";
import { createRuntimeClient, type RuntimeEvent } from \"./runtime-sdk\";
import { theme } from \"./theme\";

const defaultSources: SourceItem[] = [
  {
    id: \"src-1\",
    title: \"Policy Summary\",
    category: \"Reference\",
    preview: \"Short operational summary for assistant behavior and escalation paths.\",
    content:
      \"Use this panel for citations, retrieval snippets, or linked references. In production, wire this section to your runtime metadata and retrieval outputs.\",
  },
  {
    id: \"src-2\",
    title: \"Troubleshooting Notes\",
    category: \"Guide\",
    preview: \"Fallback patterns when responses fail or stream interruptions occur.\",
    content:
      \"When the model stream fails, render a clear fallback state and preserve user input. Add retry hints and keep the last successful partial response visible for continuity.\",
  },
  {
    id: \"src-3\",
    title: \"Deployment Checklist\",
    category: \"Operations\",
    preview: \"Pre-launch checks for authentication, observability, and release readiness.\",
    content:
      \"Before launch, validate auth gates, monitor stream latency, and test publish snapshots across desktop and mobile viewports. Keep rollback procedures documented.\",
  },
  {
    id: \"src-4\",
    title: \"Editorial Style Guide\",
    category: \"Design\",
    preview: \"Tone, layout rhythm, and visual standards for premium chat experiences.\",
    content:
      \"Prefer strong hierarchy, balanced whitespace, and clear panel ownership. Keep interaction transitions short and purposeful. Avoid noisy micro-interactions that reduce legibility.\",
  },
];

const extractTokenChunk = (event: RuntimeEvent): string => {
  if (event.event === \"token\" && typeof event.data?.content === \"string\") {
    return event.data.content;
  }
  if (event.type === \"token\" && typeof event.content === \"string\") {
    return event.content;
  }
  return \"\";
};

const extractSources = (event: RuntimeEvent): SourceItem[] => {
  if (event.event !== \"retrieval\" || !event.data) return [];
  const rawResults = (event.data as { results?: unknown[] }).results;
  if (!Array.isArray(rawResults)) return [];

  return rawResults
    .slice(0, 8)
    .map((result, index) => {
      const asRecord = (result && typeof result === \"object\") ? (result as Record<string, unknown>) : {};
      const metadata = (asRecord.metadata && typeof asRecord.metadata === \"object\") ? (asRecord.metadata as Record<string, unknown>) : {};
      const title = typeof metadata.ref === \"string\" ? metadata.ref : `Source ${index + 1}`;
      const preview = typeof metadata.text === \"string\" ? metadata.text : \"Retrieved supporting content\";
      const category = typeof metadata.source === \"string\" ? metadata.source : \"Retrieved\";
      const content = typeof asRecord.page_content === \"string\" ? asRecord.page_content : preview;
      return {
        id: `retrieved-${index + 1}`,
        title,
        category,
        preview,
        content,
      };
    })
    .filter((item) => item.content.trim().length > 0);
};

export function App() {
  const runtime = useMemo(() => createRuntimeClient(), []);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState(\"\");
  const [isSending, setIsSending] = useState(false);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const [sources, setSources] = useState<SourceItem[]>(defaultSources);

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty(\"--font-display\", theme.fontDisplay);
    root.style.setProperty(\"--font-body\", theme.fontBody);
    root.style.setProperty(\"--color-bg\", theme.bg);
    root.style.setProperty(\"--color-panel\", theme.panel);
    root.style.setProperty(\"--color-border\", theme.border);
    root.style.setProperty(\"--color-accent\", theme.accent);
    root.style.setProperty(\"--color-accent-soft\", theme.accentSoft);
    root.style.setProperty(\"--color-text\", theme.text);
    root.style.setProperty(\"--color-muted\", theme.muted);
  }, []);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || isSending) return;

    setRuntimeError(null);
    setIsSending(true);
    setInput(\"\");

    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: \"user\", content: text },
      { id: `assistant-${Date.now()}`, role: \"assistant\", content: \"\" },
    ]);

    const applyEvent = (event: RuntimeEvent) => {
      const chunk = extractTokenChunk(event);
      if (event.type === \"error\") {
        setRuntimeError(event.content || \"Runtime streaming error\");
      }

      const retrieved = extractSources(event);
      if (retrieved.length > 0) {
        setSources(retrieved);
      }

      if (!chunk) return;
      setMessages((prev) => {
        const next = [...prev];
        const lastIndex = next.length - 1;
        if (lastIndex >= 0 && next[lastIndex].role === \"assistant\") {
          next[lastIndex] = {
            ...next[lastIndex],
            content: `${next[lastIndex].content}${chunk}`,
          };
        }
        return next;
      });
    };

    try {
      const result = await runtime.stream({ input: text, chat_id: chatId || undefined }, applyEvent);
      if (result.chatId) {
        setChatId(result.chatId);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : \"Failed to stream runtime response\";
      setRuntimeError(message);
      setMessages((prev) => {
        const next = [...prev];
        const lastIndex = next.length - 1;
        if (lastIndex >= 0 && next[lastIndex].role === \"assistant\") {
          next[lastIndex] = { ...next[lastIndex], content: message };
          return next;
        }
        return [...next, { id: `assistant-error-${Date.now()}`, role: \"assistant\", content: message }];
      });
    } finally {
      setIsSending(false);
    }
  };

  return (
    <LayoutShell
      appTitle=\"Layout Shell Premium\"
      messages={messages}
      input={input}
      onInputChange={setInput}
      onSubmit={sendMessage}
      isSending={isSending}
      runtimeError={runtimeError}
      sources={sources}
    />
  );
}
""",
        "src/hooks/useIsMobile.ts": """import { useEffect, useState } from \"react\";

const MOBILE_BREAKPOINT = 900;

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window === \"undefined\") return false;
    return window.innerWidth <= MOBILE_BREAKPOINT;
  });

  useEffect(() => {
    if (typeof window === \"undefined\") return;

    const media = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`);
    const onChange = () => setIsMobile(media.matches);
    onChange();

    if (typeof media.addEventListener === \"function\") {
      media.addEventListener(\"change\", onChange);
      return () => media.removeEventListener(\"change\", onChange);
    }

    media.addListener(onChange);
    return () => media.removeListener(onChange);
  }, []);

  return isMobile;
}
""",
        "src/components/icons.tsx": """import type { SVGProps } from \"react\";

type IconProps = SVGProps<SVGSVGElement>;

const defaultAttrs = {
  width: 18,
  height: 18,
  viewBox: \"0 0 24 24\",
  fill: \"none\",
  stroke: \"currentColor\",
  strokeWidth: 1.75,
  strokeLinecap: \"round\" as const,
  strokeLinejoin: \"round\" as const,
};

export function MenuIcon(props: IconProps) {
  return (
    <svg {...defaultAttrs} {...props}>
      <path d=\"M4 7h16\" />
      <path d=\"M4 12h16\" />
      <path d=\"M4 17h16\" />
    </svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <svg {...defaultAttrs} {...props}>
      <path d=\"m6 6 12 12\" />
      <path d=\"m18 6-12 12\" />
    </svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <svg {...defaultAttrs} {...props}>
      <path d=\"m22 2-7 20-4-9-9-4Z\" />
      <path d=\"M22 2 11 13\" />
    </svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <svg {...defaultAttrs} {...props}>
      <circle cx=\"11\" cy=\"11\" r=\"7\" />
      <path d=\"m20 20-3.5-3.5\" />
    </svg>
  );
}

export function BookIcon(props: IconProps) {
  return (
    <svg {...defaultAttrs} {...props}>
      <path d=\"M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21V5.5Z\" />
      <path d=\"M8 7h7\" />
      <path d=\"M8 11h7\" />
    </svg>
  );
}

export function ChatIcon(props: IconProps) {
  return (
    <svg {...defaultAttrs} {...props}>
      <path d=\"M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 4V6Z\" />
    </svg>
  );
}

export function LayersIcon(props: IconProps) {
  return (
    <svg {...defaultAttrs} {...props}>
      <path d=\"m12 3 9 5-9 5-9-5 9-5Z\" />
      <path d=\"m3 13 9 5 9-5\" />
      <path d=\"m3 8 9 5 9-5\" />
    </svg>
  );
}

export function SparklesIcon(props: IconProps) {
  return (
    <svg {...defaultAttrs} {...props}>
      <path d=\"M12 3 9.8 8.8 4 11l5.8 2.2L12 19l2.2-5.8L20 11l-5.8-2.2Z\" />
    </svg>
  );
}

export function GripVerticalIcon(props: IconProps) {
  return (
    <svg {...defaultAttrs} {...props}>
      <circle cx=\"9\" cy=\"6\" r=\"1\" />
      <circle cx=\"15\" cy=\"6\" r=\"1\" />
      <circle cx=\"9\" cy=\"12\" r=\"1\" />
      <circle cx=\"15\" cy=\"12\" r=\"1\" />
      <circle cx=\"9\" cy=\"18\" r=\"1\" />
      <circle cx=\"15\" cy=\"18\" r=\"1\" />
    </svg>
  );
}
""",
        "src/components/layout/types.ts": """export type ChatRole = \"user\" | \"assistant\";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
};

export type SourceItem = {
  id: string;
  title: string;
  category: string;
  preview: string;
  content: string;
};
""",
        "src/components/layout/AppSidebar.tsx": """import { ChatIcon, LayersIcon, SparklesIcon } from \"../icons\";

type AppSidebarProps = {
  isOpen: boolean;
  onToggle: () => void;
  appTitle: string;
  history: string[];
};

const navItems = [
  { label: \"Conversations\", icon: ChatIcon },
  { label: \"Sources\", icon: LayersIcon },
  { label: \"Prompts\", icon: SparklesIcon },
];

export function AppSidebar({ isOpen, onToggle, appTitle, history }: AppSidebarProps) {
  return (
    <aside className={`layout-sidebar ${isOpen ? \"open\" : \"collapsed\"}`}>
      <button type=\"button\" className=\"icon-button sidebar-toggle\" onClick={onToggle}>
        {isOpen ? \"Hide\" : \"Show\"}
      </button>

      <div className=\"sidebar-brand\">
        <div className=\"brand-dot\" />
        {isOpen ? <span>{appTitle}</span> : <span>A</span>}
      </div>

      <nav className=\"sidebar-nav\" aria-label=\"Workspace navigation\">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button key={item.label} type=\"button\" className=\"sidebar-nav-item\">
              <Icon width={16} height={16} />
              {isOpen ? <span>{item.label}</span> : null}
            </button>
          );
        })}
      </nav>

      <div className=\"sidebar-history\">
        {isOpen ? <div className=\"sidebar-history-title\">Recent</div> : null}
        <div className=\"sidebar-history-list\">
          {history.map((item, idx) => (
            <button key={`${idx}-${item}`} type=\"button\" className=\"sidebar-history-item\" title={item}>
              {isOpen ? item : item.slice(0, 1)}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
""",
        "src/components/layout/ChatPane.tsx": """import type { ChatMessage } from \"./types\";
import { MenuIcon, SendIcon } from \"../icons\";

type ChatPaneProps = {
  appTitle: string;
  messages: ChatMessage[];
  input: string;
  isSending: boolean;
  runtimeError: string | null;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onToggleSidebar: () => void;
  onToggleSourceList: () => void;
};

export function ChatPane({
  appTitle,
  messages,
  input,
  isSending,
  runtimeError,
  onInputChange,
  onSubmit,
  onToggleSidebar,
  onToggleSourceList,
}: ChatPaneProps) {
  return (
    <div className=\"chat-pane\">
      <header className=\"chat-pane-header\">
        <button type=\"button\" className=\"icon-button\" onClick={onToggleSidebar}>
          <MenuIcon />
        </button>
        <div className=\"chat-pane-title\">
          <h1>{appTitle}</h1>
          <p>Production-grade shell template</p>
        </div>
        <button type=\"button\" className=\"ghost-button\" onClick={onToggleSourceList}>
          Sources
        </button>
      </header>

      <section className=\"chat-messages\" aria-label=\"Messages\">
        {messages.length === 0 ? (
          <div className=\"chat-empty\">
            <h2>Start a conversation</h2>
            <p>This shell mirrors your current workspace layout while staying fully generic.</p>
          </div>
        ) : (
          messages.map((message) => (
            <article key={message.id} className={`chat-bubble-row ${message.role === \"user\" ? \"user\" : \"assistant\"}`}>
              <div className=\"chat-bubble\">{message.content || (message.role === \"assistant\" ? \"...\" : \"\")}</div>
            </article>
          ))
        )}
      </section>

      {runtimeError ? <div className=\"runtime-error\">{runtimeError}</div> : null}

      <footer className=\"chat-input-bar\">
        <textarea
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          className=\"chat-input\"
          placeholder=\"Send a message...\"
          rows={1}
          onKeyDown={(event) => {
            if (event.key === \"Enter\" && !event.shiftKey) {
              event.preventDefault();
              onSubmit();
            }
          }}
        />
        <button type=\"button\" className=\"send-button\" onClick={onSubmit} disabled={isSending}>
          <SendIcon width={15} height={15} />
          {isSending ? \"Sending\" : \"Send\"}
        </button>
      </footer>
    </div>
  );
}
""",
        "src/components/layout/SourceListPane.tsx": """import { useMemo, useState } from \"react\";
import { BookIcon, SearchIcon } from \"../icons\";
import type { SourceItem } from \"./types\";

type SourceListPaneProps = {
  sources: SourceItem[];
  activeSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
  onClose: () => void;
};

export function SourceListPane({ sources, activeSourceId, onSelectSource, onClose }: SourceListPaneProps) {
  const [query, setQuery] = useState(\"\");

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return sources;
    return sources.filter((item) => {
      const text = `${item.title} ${item.preview} ${item.category}`.toLowerCase();
      return text.includes(normalized);
    });
  }, [query, sources]);

  return (
    <div className=\"source-list\">
      <header className=\"source-list-header\">
        <div className=\"source-list-title\">Source List</div>
        <button type=\"button\" className=\"ghost-button\" onClick={onClose}>Close</button>
      </header>

      <div className=\"source-search\">
        <SearchIcon width={14} height={14} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder=\"Search source placeholders\"
        />
      </div>

      <div className=\"source-list-content\" role=\"list\">
        {filtered.length === 0 ? (
          <div className=\"source-empty\">No matching sources.</div>
        ) : (
          filtered.map((source) => (
            <button
              key={source.id}
              type=\"button\"
              className={`source-list-item ${source.id === activeSourceId ? \"active\" : \"\"}`}
              onClick={() => onSelectSource(source.id)}
            >
              <div className=\"source-list-item-head\">
                <BookIcon width={14} height={14} />
                <span>{source.title}</span>
              </div>
              <p>{source.preview}</p>
              <small>{source.category}</small>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
""",
        "src/components/layout/SourceViewerPane.tsx": """import type { SourceItem } from \"./types\";

type SourceViewerPaneProps = {
  source: SourceItem | null;
  onClose?: () => void;
};

export function SourceViewerPane({ source, onClose }: SourceViewerPaneProps) {
  if (!source) {
    return (
      <div className=\"source-viewer empty\">
        <div className=\"source-viewer-empty\">
          <h3>Select a source</h3>
          <p>Use this panel for citations, retrieved references, and supporting context.</p>
        </div>
      </div>
    );
  }

  return (
    <div className=\"source-viewer\">
      <header className=\"source-viewer-header\">
        <div>
          <div className=\"source-viewer-category\">{source.category}</div>
          <h3>{source.title}</h3>
        </div>
        {onClose ? (
          <button type=\"button\" className=\"ghost-button\" onClick={onClose}>
            Close
          </button>
        ) : null}
      </header>
      <article className=\"source-viewer-content\">{source.content}</article>
    </div>
  );
}
""",
        "src/components/layout/LayoutShell.tsx": """import { useEffect, useMemo, useRef, useState } from \"react\";
import { AppSidebar } from \"./AppSidebar\";
import { ChatPane } from \"./ChatPane\";
import { SourceListPane } from \"./SourceListPane\";
import { SourceViewerPane } from \"./SourceViewerPane\";
import type { ChatMessage, SourceItem } from \"./types\";
import { CloseIcon, GripVerticalIcon, MenuIcon } from \"../icons\";
import { useIsMobile } from \"../../hooks/useIsMobile\";

type LayoutShellProps = {
  appTitle: string;
  messages: ChatMessage[];
  input: string;
  isSending: boolean;
  runtimeError: string | null;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  sources: SourceItem[];
};

export function LayoutShell({
  appTitle,
  messages,
  input,
  isSending,
  runtimeError,
  onInputChange,
  onSubmit,
  sources,
}: LayoutShellProps) {
  const isMobile = useIsMobile();
  const workspaceRef = useRef<HTMLDivElement | null>(null);

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isSourceListOpen, setIsSourceListOpen] = useState(true);
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const [lastActiveSourceId, setLastActiveSourceId] = useState<string | null>(null);
  const [sourceViewerWidth, setSourceViewerWidth] = useState(520);
  const [isResizing, setIsResizing] = useState(false);

  const history = useMemo(() => {
    const recentUserMessages = messages
      .filter((message) => message.role === \"user\")
      .slice(-6)
      .map((message) => message.content.trim())
      .filter((message) => message.length > 0)
      .reverse();
    if (recentUserMessages.length > 0) return recentUserMessages;
    return [\"Welcome conversation\", \"Design review\", \"Runtime notes\"];
  }, [messages]);

  const activeSource = useMemo(() => {
    const direct = sources.find((source) => source.id === activeSourceId) || null;
    if (direct) return direct;
    if (!lastActiveSourceId) return null;
    return sources.find((source) => source.id === lastActiveSourceId) || null;
  }, [activeSourceId, lastActiveSourceId, sources]);

  useEffect(() => {
    if (!activeSourceId) return;
    setLastActiveSourceId(activeSourceId);
  }, [activeSourceId]);

  useEffect(() => {
    if (!isMobile) return;
    setIsSidebarOpen(false);
    setIsSourceListOpen(false);
  }, [isMobile]);

  useEffect(() => {
    if (!isResizing || isMobile) return;

    const onMouseMove = (event: MouseEvent) => {
      const host = workspaceRef.current;
      if (!host) return;
      const hostBox = host.getBoundingClientRect();
      const fromRight = hostBox.right - event.clientX;
      const nextWidth = Math.min(Math.max(fromRight, 360), 920);
      setSourceViewerWidth(nextWidth);
    };

    const onMouseUp = () => setIsResizing(false);

    window.addEventListener(\"mousemove\", onMouseMove);
    window.addEventListener(\"mouseup\", onMouseUp);
    document.body.style.cursor = \"ew-resize\";
    document.body.style.userSelect = \"none\";

    return () => {
      window.removeEventListener(\"mousemove\", onMouseMove);
      window.removeEventListener(\"mouseup\", onMouseUp);
      document.body.style.cursor = \"\";
      document.body.style.userSelect = \"\";
    };
  }, [isMobile, isResizing]);

  const showViewer = Boolean(activeSource);

  return (
    <div className=\"layout-shell\">
      {!isSidebarOpen && isMobile ? (
        <button type=\"button\" className=\"mobile-sidebar-trigger\" onClick={() => setIsSidebarOpen(true)}>
          <MenuIcon width={16} height={16} />
        </button>
      ) : null}

      {isMobile ? (
        isSidebarOpen ? (
          <div className=\"mobile-overlay\" role=\"dialog\" aria-modal=\"true\">
            <div className=\"mobile-overlay-backdrop\" onClick={() => setIsSidebarOpen(false)} />
            <div className=\"mobile-overlay-panel sidebar\">
              <div className=\"mobile-overlay-top\">
                <button type=\"button\" className=\"icon-button\" onClick={() => setIsSidebarOpen(false)}>
                  <CloseIcon width={14} height={14} />
                </button>
              </div>
              <AppSidebar
                isOpen
                onToggle={() => setIsSidebarOpen(false)}
                appTitle={appTitle}
                history={history}
              />
            </div>
          </div>
        ) : null
      ) : (
        <AppSidebar
          isOpen={isSidebarOpen}
          onToggle={() => setIsSidebarOpen((value) => !value)}
          appTitle={appTitle}
          history={history}
        />
      )}

      <div className=\"layout-content\" ref={workspaceRef}>
        <main className=\"layout-main\">
          <ChatPane
            appTitle={appTitle}
            messages={messages}
            input={input}
            isSending={isSending}
            runtimeError={runtimeError}
            onInputChange={onInputChange}
            onSubmit={onSubmit}
            onToggleSidebar={() => setIsSidebarOpen((value) => !value)}
            onToggleSourceList={() => setIsSourceListOpen((value) => !value)}
          />
        </main>

        {!isMobile ? (
          <>
            <section
              className={`layout-source-viewer ${showViewer ? \"open\" : \"closed\"}`}
              style={{ width: showViewer ? sourceViewerWidth : 0 }}
            >
              <SourceViewerPane source={activeSource} />
              {showViewer ? (
                <button
                  type=\"button\"
                  className=\"resize-handle\"
                  onMouseDown={() => setIsResizing(true)}
                  aria-label=\"Resize source viewer\"
                >
                  <GripVerticalIcon width={14} height={14} />
                </button>
              ) : null}
            </section>

            <section className={`layout-source-list ${isSourceListOpen ? \"open\" : \"closed\"}`}>
              <SourceListPane
                sources={sources}
                activeSourceId={activeSourceId}
                onSelectSource={(sourceId) => setActiveSourceId(sourceId)}
                onClose={() => setIsSourceListOpen(false)}
              />
            </section>
          </>
        ) : (
          <>
            {isSourceListOpen ? (
              <div className=\"mobile-overlay\" role=\"dialog\" aria-modal=\"true\">
                <div className=\"mobile-overlay-backdrop\" onClick={() => setIsSourceListOpen(false)} />
                <div className=\"mobile-overlay-panel source-list\">
                  <SourceListPane
                    sources={sources}
                    activeSourceId={activeSourceId}
                    onSelectSource={(sourceId) => {
                      setActiveSourceId(sourceId);
                      setIsSourceListOpen(false);
                    }}
                    onClose={() => setIsSourceListOpen(false)}
                  />
                </div>
              </div>
            ) : null}

            {showViewer ? (
              <div className=\"mobile-viewer\" role=\"dialog\" aria-modal=\"true\">
                <SourceViewerPane source={activeSource} onClose={() => setActiveSourceId(null)} />
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
""",
        "src/styles.css": """:root {
  color-scheme: light;
  --font-display: \"Iowan Old Style\", \"Palatino Linotype\", \"Book Antiqua\", Palatino, serif;
  --font-body: \"Avenir Next\", \"Segoe UI\", sans-serif;
  --color-bg: #eff2f7;
  --color-panel: #ffffff;
  --color-border: #d8dfea;
  --color-accent: #115ad8;
  --color-accent-soft: #dce8ff;
  --color-text: #111b2d;
  --color-muted: #5f6f8a;
}

* {
  box-sizing: border-box;
}

html,
body,
#root {
  width: 100%;
  height: 100%;
  margin: 0;
}

body {
  font-family: var(--font-body);
  background: radial-gradient(circle at 15% 0%, #f9fbff 0%, var(--color-bg) 58%);
  color: var(--color-text);
}

button,
input,
textarea {
  font: inherit;
}

button {
  cursor: pointer;
}

.layout-shell {
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: transparent;
}

.layout-sidebar {
  flex-shrink: 0;
  width: 248px;
  height: 100%;
  border-right: 1px solid var(--color-border);
  background: color-mix(in oklab, var(--color-panel) 88%, #f5f8ff 12%);
  transition: width 220ms ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.layout-sidebar.collapsed {
  width: 72px;
}

.sidebar-toggle {
  margin: 10px;
  align-self: flex-end;
}

.sidebar-brand {
  margin: 6px 12px 10px;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid var(--color-border);
  background: #f7f9ff;
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-display);
  font-size: 14px;
  min-height: 40px;
}

.brand-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--color-accent);
  box-shadow: 0 0 0 5px color-mix(in oklab, var(--color-accent) 20%, transparent);
}

.sidebar-nav {
  padding: 0 10px;
  display: grid;
  gap: 6px;
}

.sidebar-nav-item,
.sidebar-history-item {
  width: 100%;
  border: 1px solid transparent;
  background: transparent;
  color: var(--color-text);
  border-radius: 10px;
  padding: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  text-align: left;
}

.sidebar-nav-item:hover,
.sidebar-history-item:hover {
  border-color: var(--color-border);
  background: #f7f9fd;
}

.sidebar-history {
  margin-top: auto;
  padding: 12px 10px;
}

.sidebar-history-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-muted);
  margin: 0 2px 8px;
}

.sidebar-history-list {
  display: grid;
  gap: 6px;
}

.sidebar-history-item {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.layout-content {
  min-width: 0;
  flex: 1;
  display: flex;
  height: 100%;
  overflow: hidden;
}

.layout-main {
  min-width: 0;
  flex: 1;
  display: flex;
  height: 100%;
  border-right: 1px solid color-mix(in oklab, var(--color-border) 45%, transparent);
}

.chat-pane {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: color-mix(in oklab, var(--color-panel) 84%, #edf2ff 16%);
}

.chat-pane-header {
  height: 58px;
  flex-shrink: 0;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  border-bottom: 1px solid var(--color-border);
  background: color-mix(in oklab, var(--color-panel) 88%, #f5f8ff 12%);
}

.chat-pane-title h1 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.chat-pane-title p {
  margin: 1px 0 0;
  color: var(--color-muted);
  font-size: 11px;
}

.chat-messages {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 18px;
  display: grid;
  gap: 12px;
}

.chat-empty {
  margin: auto;
  max-width: 460px;
  border: 1px dashed var(--color-border);
  border-radius: 16px;
  padding: 22px;
  background: rgba(255, 255, 255, 0.75);
}

.chat-empty h2 {
  margin: 0 0 6px;
  font-family: var(--font-display);
  font-size: 22px;
}

.chat-empty p {
  margin: 0;
  color: var(--color-muted);
  line-height: 1.45;
}

.chat-bubble-row {
  display: flex;
}

.chat-bubble-row.user {
  justify-content: flex-end;
}

.chat-bubble {
  max-width: min(78%, 760px);
  border-radius: 14px;
  border: 1px solid var(--color-border);
  padding: 10px 12px;
  white-space: pre-wrap;
  line-height: 1.45;
  font-size: 14px;
}

.chat-bubble-row.user .chat-bubble {
  background: var(--color-accent);
  color: #f7fbff;
  border-color: color-mix(in oklab, var(--color-accent) 62%, black);
}

.chat-bubble-row.assistant .chat-bubble {
  background: #fff;
  color: var(--color-text);
}

.runtime-error {
  flex-shrink: 0;
  margin: 0 14px 12px;
  border: 1px solid color-mix(in oklab, #f04438 40%, var(--color-border));
  background: #fff5f5;
  color: #7a1919;
  border-radius: 10px;
  padding: 9px 10px;
  font-size: 12px;
}

.chat-input-bar {
  flex-shrink: 0;
  padding: 12px 14px 14px;
  border-top: 1px solid var(--color-border);
  display: flex;
  gap: 8px;
  background: color-mix(in oklab, var(--color-panel) 90%, #eff4ff 10%);
}

.chat-input {
  flex: 1;
  min-height: 42px;
  max-height: 130px;
  resize: vertical;
  border: 1px solid var(--color-border);
  border-radius: 11px;
  background: #fff;
  color: var(--color-text);
  padding: 10px 12px;
}

.chat-input:focus {
  outline: 2px solid color-mix(in oklab, var(--color-accent) 25%, transparent);
  outline-offset: 0;
}

.send-button {
  height: 42px;
  padding: 0 14px;
  border-radius: 11px;
  border: none;
  background: var(--color-accent);
  color: #fff;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.send-button:disabled {
  opacity: 0.65;
}

.ghost-button,
.icon-button {
  border: 1px solid var(--color-border);
  background: #fff;
  color: var(--color-text);
  border-radius: 10px;
  min-height: 34px;
  padding: 0 11px;
}

.icon-button {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.ghost-button:hover,
.icon-button:hover,
.send-button:hover {
  filter: brightness(0.98);
}

.layout-source-viewer {
  position: relative;
  flex-shrink: 0;
  overflow: hidden;
  border-right: 1px solid var(--color-border);
  background: var(--color-panel);
  transition: width 220ms ease;
}

.layout-source-viewer.closed {
  border-right-color: transparent;
}

.resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 12px;
  border: none;
  border-right: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: ew-resize;
}

.layout-source-list {
  flex-shrink: 0;
  width: 300px;
  border-left: 1px solid var(--color-border);
  background: color-mix(in oklab, var(--color-panel) 90%, #f2f6ff 10%);
  overflow: hidden;
  transition: width 220ms ease, opacity 220ms ease;
}

.layout-source-list.closed {
  width: 0;
  opacity: 0;
  border-left-color: transparent;
}

.source-list,
.source-viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.source-list-header,
.source-viewer-header {
  min-height: 54px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.source-list-title {
  font-family: var(--font-display);
  font-size: 14px;
}

.source-search {
  margin: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  height: 38px;
  background: #fff;
}

.source-search input {
  border: none;
  outline: none;
  width: 100%;
  background: transparent;
}

.source-list-content {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 0 12px 12px;
  display: grid;
  gap: 8px;
}

.source-list-item {
  width: 100%;
  border-radius: 12px;
  border: 1px solid var(--color-border);
  background: #fff;
  padding: 10px;
  text-align: left;
}

.source-list-item.active {
  border-color: color-mix(in oklab, var(--color-accent) 45%, var(--color-border));
  background: color-mix(in oklab, var(--color-accent-soft) 50%, #fff);
}

.source-list-item-head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-weight: 600;
  margin-bottom: 6px;
}

.source-list-item p {
  margin: 0 0 8px;
  color: var(--color-muted);
  font-size: 12px;
  line-height: 1.35;
}

.source-list-item small {
  color: var(--color-muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.source-empty {
  margin: auto;
  color: var(--color-muted);
  font-size: 12px;
}

.source-viewer-header h3 {
  margin: 2px 0 0;
  font-family: var(--font-display);
  font-size: 18px;
}

.source-viewer-category {
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-muted);
  font-size: 11px;
}

.source-viewer-content {
  min-height: 0;
  overflow: auto;
  padding: 18px;
  white-space: pre-wrap;
  line-height: 1.55;
  color: color-mix(in oklab, var(--color-text) 86%, black);
}

.source-viewer.empty {
  align-items: center;
  justify-content: center;
}

.source-viewer-empty {
  margin: auto;
  width: min(360px, 92%);
  border: 1px dashed var(--color-border);
  border-radius: 14px;
  padding: 20px;
  background: #fff;
}

.source-viewer-empty h3 {
  margin: 0 0 6px;
  font-family: var(--font-display);
}

.source-viewer-empty p {
  margin: 0;
  color: var(--color-muted);
  line-height: 1.4;
}

.mobile-sidebar-trigger {
  position: fixed;
  right: 14px;
  bottom: 14px;
  z-index: 70;
  border: none;
  width: 42px;
  height: 42px;
  border-radius: 999px;
  background: var(--color-accent);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 30px rgba(17, 90, 216, 0.35);
}

.mobile-overlay,
.mobile-viewer {
  position: fixed;
  inset: 0;
  z-index: 80;
}

.mobile-overlay-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(8, 13, 24, 0.44);
}

.mobile-overlay-panel {
  position: absolute;
  top: 0;
  bottom: 0;
  background: var(--color-panel);
  box-shadow: 0 18px 42px rgba(15, 24, 42, 0.34);
  display: flex;
  flex-direction: column;
}

.mobile-overlay-panel.sidebar {
  width: min(300px, 82vw);
  left: 0;
}

.mobile-overlay-panel.source-list {
  width: min(330px, 90vw);
  right: 0;
}

.mobile-overlay-top {
  min-height: 44px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 8px;
  border-bottom: 1px solid var(--color-border);
}

.mobile-viewer {
  background: var(--color-panel);
}

@media (max-width: 900px) {
  .layout-shell {
    display: block;
  }

  .layout-content {
    width: 100%;
  }

  .chat-pane-header {
    padding-left: 12px;
    padding-right: 12px;
  }

  .chat-bubble {
    max-width: 90%;
  }
}
""",
    }


TEMPLATES: List[PublishedAppTemplate] = [
    PublishedAppTemplate(
        key="chat-classic",
        name="Classic Dialogue",
        description="Balanced chat-first layout with subtle panels.",
        thumbnail="classic",
        tags=["chat", "neutral"],
        entry_file="src/main.tsx",
        style_tokens={
            "fontDisplay": "'IBM Plex Serif', serif",
            "fontBody": "'IBM Plex Sans', sans-serif",
            "bg": "#f4f5f7",
            "panel": "#ffffff",
            "border": "#dde2ea",
            "accent": "#0f6cff",
            "accentSoft": "#dce8ff",
            "text": "#141c2b",
            "muted": "#5a6b85",
        },
    ),
    PublishedAppTemplate(
        key="chat-editorial",
        name="Editorial Stack",
        description="High-contrast editorial style for premium assistants.",
        thumbnail="editorial",
        tags=["chat", "editorial"],
        entry_file="src/main.tsx",
        style_tokens={
            "fontDisplay": "'Bodoni Moda', serif",
            "fontBody": "'Source Sans 3', sans-serif",
            "bg": "#fbf8f1",
            "panel": "#fffdf7",
            "border": "#e4d8c5",
            "accent": "#5f3c2b",
            "accentSoft": "#eadcc9",
            "text": "#23180f",
            "muted": "#6f5b4b",
        },
    ),
    PublishedAppTemplate(
        key="chat-neon",
        name="Neon Console",
        description="Dark neon style with bold contrast and sharp edges.",
        thumbnail="neon",
        tags=["chat", "dark"],
        entry_file="src/main.tsx",
        style_tokens={
            "fontDisplay": "'Syne', sans-serif",
            "fontBody": "'DM Sans', sans-serif",
            "bg": "#0d1117",
            "panel": "#141b24",
            "border": "#263446",
            "accent": "#22d3ee",
            "accentSoft": "#123844",
            "text": "#e8f1ff",
            "muted": "#8ba1bf",
        },
    ),
    PublishedAppTemplate(
        key="chat-soft",
        name="Soft Product",
        description="Rounded, calm interface for customer-facing support flows.",
        thumbnail="soft",
        tags=["chat", "friendly"],
        entry_file="src/main.tsx",
        style_tokens={
            "fontDisplay": "'Fraunces', serif",
            "fontBody": "'Manrope', sans-serif",
            "bg": "#eef3ff",
            "panel": "#f9fbff",
            "border": "#d2ddf6",
            "accent": "#3757f7",
            "accentSoft": "#d9e3ff",
            "text": "#1a2545",
            "muted": "#5e6c96",
        },
    ),
    PublishedAppTemplate(
        key="chat-grid",
        name="Layout Shell Premium",
        description="LayoutShell-style workspace with sidebar, resizable source viewer, and mobile overlays.",
        thumbnail="layout-shell",
        tags=["chat", "premium", "workspace"],
        entry_file="src/main.tsx",
        style_tokens={
            "fontDisplay": "'Sora', sans-serif",
            "fontBody": "'Nunito Sans', sans-serif",
            "bg": "#f3f6fc",
            "panel": "#ffffff",
            "border": "#d8dfec",
            "accent": "#115ad8",
            "accentSoft": "#dce8ff",
            "text": "#10243b",
            "muted": "#60758f",
        },
    ),
]


def list_templates() -> List[PublishedAppTemplate]:
    return TEMPLATES


def get_template(template_key: str) -> PublishedAppTemplate:
    for template in TEMPLATES:
        if template.key == template_key:
            return template
    raise KeyError(template_key)


def build_template_files(template_key: str) -> Dict[str, str]:
    template = get_template(template_key)
    if template_key == "chat-grid":
        return _build_layout_shell_template_files(template.style_tokens)
    return _build_default_chat_template_files(template.style_tokens)
