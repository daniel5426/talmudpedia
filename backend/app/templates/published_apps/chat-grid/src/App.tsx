import { useEffect, useMemo, useState } from "react";
import { LayoutShell } from "./components/layout/LayoutShell";
import type { ChatMessage, SourceItem } from "./components/layout/types";
import { createRuntimeClient, type RuntimeEvent } from "./runtime-sdk";
import { theme } from "./theme";

const defaultSources: SourceItem[] = [
  {
    id: "src-1",
    title: "Policy Summary",
    category: "Reference",
    preview: "Short operational summary for assistant behavior and escalation paths.",
    content:
      "Use this panel for citations, retrieval snippets, or linked references. In production, wire this section to your runtime metadata and retrieval outputs.",
  },
  {
    id: "src-2",
    title: "Troubleshooting Notes",
    category: "Guide",
    preview: "Fallback patterns when responses fail or stream interruptions occur.",
    content:
      "When the model stream fails, render a clear fallback state and preserve user input. Add retry hints and keep the last successful partial response visible for continuity.",
  },
  {
    id: "src-3",
    title: "Deployment Checklist",
    category: "Operations",
    preview: "Pre-launch checks for authentication, observability, and release readiness.",
    content:
      "Before launch, validate auth gates, monitor stream latency, and test publish snapshots across desktop and mobile viewports. Keep rollback procedures documented.",
  },
  {
    id: "src-4",
    title: "Editorial Style Guide",
    category: "Design",
    preview: "Tone, layout rhythm, and visual standards for premium chat experiences.",
    content:
      "Prefer strong hierarchy, balanced whitespace, and clear panel ownership. Keep interaction transitions short and purposeful. Avoid noisy micro-interactions that reduce legibility.",
  },
];

const extractTokenChunk = (event: RuntimeEvent): string => {
  if (event.event === "token" && typeof event.data?.content === "string") {
    return event.data.content;
  }
  if (event.type === "token" && typeof event.content === "string") {
    return event.content;
  }
  return "";
};

const extractSources = (event: RuntimeEvent): SourceItem[] => {
  if (event.event !== "retrieval" || !event.data) return [];
  const rawResults = (event.data as { results?: unknown[] }).results;
  if (!Array.isArray(rawResults)) return [];

  return rawResults
    .slice(0, 8)
    .map((result, index) => {
      const asRecord = (result && typeof result === "object") ? (result as Record<string, unknown>) : {};
      const metadata = (asRecord.metadata && typeof asRecord.metadata === "object") ? (asRecord.metadata as Record<string, unknown>) : {};
      const title = typeof metadata.ref === "string" ? metadata.ref : `Source ${index + 1}`;
      const preview = typeof metadata.text === "string" ? metadata.text : "Retrieved supporting content";
      const category = typeof metadata.source === "string" ? metadata.source : "Retrieved";
      const content = typeof asRecord.page_content === "string" ? asRecord.page_content : preview;
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
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const [sources, setSources] = useState<SourceItem[]>(defaultSources);

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--font-display", theme.fontDisplay);
    root.style.setProperty("--font-body", theme.fontBody);
    root.style.setProperty("--color-bg", theme.bg);
    root.style.setProperty("--color-panel", theme.panel);
    root.style.setProperty("--color-border", theme.border);
    root.style.setProperty("--color-accent", theme.accent);
    root.style.setProperty("--color-accent-soft", theme.accentSoft);
    root.style.setProperty("--color-text", theme.text);
    root.style.setProperty("--color-muted", theme.muted);
  }, []);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || isSending) return;

    setRuntimeError(null);
    setIsSending(true);
    setInput("");

    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: "user", content: text },
      { id: `assistant-${Date.now()}`, role: "assistant", content: "" },
    ]);

    const applyEvent = (event: RuntimeEvent) => {
      const chunk = extractTokenChunk(event);
      if (event.type === "error") {
        setRuntimeError(event.content || "Runtime streaming error");
      }

      const retrieved = extractSources(event);
      if (retrieved.length > 0) {
        setSources(retrieved);
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
      const result = await runtime.stream({ input: text, chat_id: chatId || undefined }, applyEvent);
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
          next[lastIndex] = { ...next[lastIndex], content: message };
          return next;
        }
        return [...next, { id: `assistant-error-${Date.now()}`, role: "assistant", content: message }];
      });
    } finally {
      setIsSending(false);
    }
  };

  return (
    <LayoutShell
      appTitle="Layout Shell Premium"
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
