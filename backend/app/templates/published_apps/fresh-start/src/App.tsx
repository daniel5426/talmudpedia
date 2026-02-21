import { FormEvent, useMemo, useState } from "react";

import { createRuntimeClient, RuntimeEvent } from "./runtime-sdk";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const pullEventText = (event: RuntimeEvent): string => {
  if (typeof event.content === "string" && event.content.trim()) {
    return event.content;
  }
  const payload = event.payload || {};
  const payloadText = payload.content;
  if (typeof payloadText === "string" && payloadText.trim()) {
    return payloadText;
  }
  return "";
};

export default function App() {
  const client = useMemo(() => createRuntimeClient(), []);
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const input = prompt.trim();
    if (!input || isStreaming) return;

    setError(null);
    setPrompt("");
    setIsStreaming(true);

    setMessages((prev) => [...prev, { role: "user", content: input }, { role: "assistant", content: "" }]);

    try {
      await client.stream(
        {
          input,
          messages: messages.map((message) => ({ role: message.role, content: message.content })),
        },
        (eventPayload) => {
          const next = pullEventText(eventPayload);
          if (!next) return;
          setMessages((prev) => {
            const copy = [...prev];
            const index = copy.length - 1;
            if (index < 0 || copy[index].role !== "assistant") {
              return [...copy, { role: "assistant", content: next }];
            }
            copy[index] = { ...copy[index], content: copy[index].content + next };
            return copy;
          });
        },
      );
    } catch (streamError) {
      setError(streamError instanceof Error ? streamError.message : "Failed to stream response");
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <main className="app-shell">
      <header>
        <h1>Fresh Start</h1>
        <p>Minimal starter with runtime SDK wiring.</p>
      </header>

      <section className="messages">
        {messages.length === 0 ? <p className="empty">Ask something to begin.</p> : null}
        {messages.map((message, index) => (
          <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
            <strong>{message.role === "user" ? "You" : "Assistant"}</strong>
            <p>{message.content || (isStreaming && message.role === "assistant" ? "..." : "")}</p>
          </article>
        ))}
      </section>

      <form className="composer" onSubmit={onSubmit}>
        <textarea
          value={prompt}
          onChange={(changeEvent) => setPrompt(changeEvent.target.value)}
          rows={3}
          placeholder="Describe what to build..."
        />
        <button type="submit" disabled={isStreaming || !prompt.trim()}>
          {isStreaming ? "Streaming..." : "Send"}
        </button>
      </form>

      {error ? <p className="error">{error}</p> : null}
    </main>
  );
}
