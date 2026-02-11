import { useMemo, useState } from "react";
import { createRuntimeClient, type RuntimeEvent } from "./runtime-sdk";
import { theme } from "./theme";

type Message = { role: "user" | "assistant"; content: string };

const extractTokenChunk = (event: RuntimeEvent): string => {
  if (event.event === "token" && typeof event.data?.content === "string") {
    return event.data.content;
  }
  if (event.type === "token" && typeof event.content === "string") {
    return event.content;
  }
  return "";
};

export function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const runtime = useMemo(() => createRuntimeClient(), []);

  const title = useMemo(() => "Your AI App", []);

  const submit = async () => {
    const text = input.trim();
    if (!text || isSending) return;

    setRuntimeError(null);
    setIsSending(true);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: "" }]);

    const applyEvent = (event: RuntimeEvent) => {
      const chunk = extractTokenChunk(event);
      if (event.type === "error") {
        setRuntimeError(event.content || "Runtime streaming error");
      }
      if (!chunk) return;
      setMessages((prev) => {
        const next = [...prev];
        const lastIndex = next.length - 1;
        if (lastIndex >= 0 && next[lastIndex].role === "assistant") {
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
      const message = error instanceof Error ? error.message : "Failed to stream runtime response";
      setRuntimeError(message);
      setMessages((prev) => {
        const next = [...prev];
        const lastIndex = next.length - 1;
        if (lastIndex >= 0 && next[lastIndex].role === "assistant") {
          next[lastIndex] = { role: "assistant", content: message };
          return next;
        }
        return [...next, { role: "assistant", content: message }];
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
        height: "100vh",
        display: "flex",
      }}
    >
      <aside
        style={{
          width: sidebarOpen ? 240 : 0,
          transition: "width 180ms ease",
          overflow: "hidden",
          borderRight: `1px solid ${theme.border}`,
          background: theme.panel,
          padding: sidebarOpen ? 16 : 0,
        }}
      >
        <h3 style={{ margin: 0, fontFamily: theme.fontDisplay }}>History</h3>
        <p style={{ color: theme.muted, fontSize: 12 }}>Connect persisted chats here.</p>
      </aside>

      <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <header
          style={{
            height: 56,
            borderBottom: `1px solid ${theme.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 16px",
            background: theme.panel,
          }}
        >
          <button onClick={() => setSidebarOpen((v) => !v)}>Sidebar</button>
          <h1 style={{ margin: 0, fontSize: 16, fontFamily: theme.fontDisplay }}>{title}</h1>
          <button onClick={() => setSourceOpen((v) => !v)}>Source</button>
        </header>

        <section style={{ flex: 1, overflow: "auto", padding: 20 }}>
          {messages.length === 0 ? (
            <p style={{ color: theme.muted }}>Start a conversation.</p>
          ) : (
            messages.map((message, idx) => (
              <div key={`${message.role}-${idx}`} style={{ marginBottom: 12, textAlign: message.role === "user" ? "right" : "left" }}>
                <span
                  style={{
                    display: "inline-block",
                    background: message.role === "user" ? theme.accent : theme.panel,
                    color: message.role === "user" ? "#fff" : theme.text,
                    padding: "10px 12px",
                    borderRadius: 12,
                    maxWidth: "75%",
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
              padding: "8px 12px",
              fontSize: 12,
            }}
          >
            {runtimeError}
          </div>
        )}

        <footer style={{ borderTop: `1px solid ${theme.border}`, padding: 12, display: "flex", gap: 8 }}>
          <input
            style={{
              flex: 1,
              border: `1px solid ${theme.border}`,
              borderRadius: 10,
              padding: "10px 12px",
              background: theme.panel,
              color: theme.text,
            }}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Send a message"
          />
          <button
            onClick={submit}
            disabled={isSending}
            style={{
              borderRadius: 10,
              border: "none",
              background: theme.accent,
              color: "white",
              padding: "10px 14px",
              opacity: isSending ? 0.7 : 1,
            }}
          >
            {isSending ? "Sending..." : "Send"}
          </button>
        </footer>
      </main>

      <aside
        style={{
          width: sourceOpen ? 320 : 0,
          transition: "width 180ms ease",
          overflow: "hidden",
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
