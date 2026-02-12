import { useMemo, useRef, useState } from "react";
import { createRuntimeClient, type RuntimeEvent } from "./runtime-sdk";
import { theme } from "./theme";
import { BotInputArea } from "./components/BotInputArea";
import { SidebarProvider, Sidebar, SidebarInset, SidebarTrigger } from "./components/ui/sidebar";
import {
  Message,
  MessageContent,
  MessageResponse,
  MessageActions,
  MessageAction,
} from "./components/ai-elements/message";
import {
  ChainOfThought,
  ChainOfThoughtHeader,
  ChainOfThoughtContent,
  ChainOfThoughtStep,
} from "./components/ai-elements/chain-of-thought";
import { DirectionProvider } from "./components/direction-provider";

type ReasoningStatus = "pending" | "complete" | "error";

type ReasoningStep = {
  id: string;
  label: string;
  status: ReasoningStatus;
  description?: string;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  reasoningSteps?: ReasoningStep[];
};

type SourceCitation = {
  title: string;
  excerpt?: string;
};

const uid = () => Math.random().toString(36).slice(2, 10);

const extractTokenChunk = (event: RuntimeEvent): string => {
  if (event.event === "token" && typeof event.data?.content === "string") {
    return event.data.content;
  }
  if (event.type === "token" && typeof event.content === "string") {
    return event.content;
  }
  return "";
};

const extractReasoningStep = (event: RuntimeEvent): ReasoningStep | null => {
  const kind = String(event.event || event.type || "").toLowerCase();
  const data = event.data || {};
  const statusRaw = typeof data.status === "string" ? data.status.toLowerCase() : "";

  const isReasoning =
    kind.includes("reason") ||
    kind.includes("think") ||
    kind.includes("retriev") ||
    kind.includes("tool") ||
    statusRaw === "pending" ||
    statusRaw === "complete";

  if (!isReasoning) return null;

  const label =
    (typeof data.label === "string" && data.label) ||
    (typeof data.stage === "string" && data.stage) ||
    (typeof data.tool === "string" && data.tool) ||
    "Reasoning";

  let status: ReasoningStatus = "pending";
  if (kind.includes("error") || statusRaw === "error") status = "error";
  else if (kind.includes("done") || kind.includes("complete") || statusRaw === "complete") status = "complete";

  const description =
    (typeof data.description === "string" && data.description) ||
    (typeof data.query === "string" && `Query: ${data.query}`) ||
    undefined;

  return {
    id: uid(),
    label,
    status,
    description,
  };
};

const extractSources = (event: RuntimeEvent): SourceCitation[] => {
  const data = event.data || {};
  const raw = (data.citations || data.sources || []) as Array<Record<string, unknown>>;
  if (!Array.isArray(raw)) return [];

  return raw.reduce<SourceCitation[]>((acc, item) => {
    const title =
      (typeof item.title === "string" && item.title) ||
      (typeof item.sourceRef === "string" && item.sourceRef) ||
      (typeof item.ref === "string" && item.ref) ||
      "";
    if (!title) return acc;

    const excerpt =
      (typeof item.description === "string" && item.description) ||
      (typeof item.excerpt === "string" && item.excerpt) ||
      undefined;
    acc.push({ title, excerpt });
    return acc;
  }, []);
};

const mergeReasoningSteps = (existing: ReasoningStep[] = [], incoming: ReasoningStep): ReasoningStep[] => {
  const idx = existing.findIndex((step) => step.label.toLowerCase() === incoming.label.toLowerCase());
  if (idx < 0) return [...existing, incoming];
  const next = [...existing];
  next[idx] = {
    ...next[idx],
    status: incoming.status,
    description: incoming.description || next[idx].description,
  };
  return next;
};

export function App() {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sources, setSources] = useState<SourceCitation[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const [sourceOpen, setSourceOpen] = useState(true);

  const runtime = useMemo(() => createRuntimeClient(), []);

  const updateMessage = (id: string, updater: (value: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? updater(item) : item)));
  };

  const handleSubmit = async ({ text }: { text: string; files: Array<{ id: string; filename: string }> }) => {
    const prompt = text.trim();
    if (!prompt || isSending) return;

    const userId = uid();
    const assistantId = uid();

    setRuntimeError(null);
    setSources([]);
    setIsSending(true);

    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: prompt },
      { id: assistantId, role: "assistant", content: "", reasoningSteps: [] },
    ]);

    try {
      const result = await runtime.stream({ input: prompt, chat_id: chatId || undefined }, (event: RuntimeEvent) => {
        const chunk = extractTokenChunk(event);
        const reasoning = extractReasoningStep(event);
        const sourceHits = extractSources(event);

        if (event.type === "error") {
          setRuntimeError(event.content || "Runtime streaming error");
        }

        if (reasoning) {
          updateMessage(assistantId, (current) => ({
            ...current,
            reasoningSteps: mergeReasoningSteps(current.reasoningSteps || [], reasoning),
          }));
        }

        if (sourceHits.length > 0) {
          setSources((prev) => {
            const known = new Set(prev.map((item) => `${item.title}|${item.excerpt || ""}`));
            const next = [...prev];
            sourceHits.forEach((item) => {
              const key = `${item.title}|${item.excerpt || ""}`;
              if (!known.has(key)) {
                known.add(key);
                next.push(item);
              }
            });
            return next;
          });
        }

        if (!chunk) return;

        updateMessage(assistantId, (current) => ({
          ...current,
          content: `${current.content}${chunk}`,
        }));
      });

      if (result.chatId) setChatId(result.chatId);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to stream runtime response";
      setRuntimeError(message);
      updateMessage(assistantId, (current) => ({ ...current, content: message }));
    } finally {
      setIsSending(false);
    }
  };

  return (
    <DirectionProvider initialDirection="ltr">
      <SidebarProvider defaultOpen>
        <div className="chat-app" style={{ ["--bg" as string]: theme.bg }}>
        <Sidebar className="chat-sidebar">
          <div className="sidebar-brand">
            <div className="sidebar-brand-mark">K</div>
            <div>
              <p className="sidebar-brand-title">Kesher Panel</p>
              <p className="sidebar-brand-sub">Published runtime</p>
            </div>
          </div>
          <button className="sidebar-new-chat" type="button">+ New Chat</button>
          <nav className="sidebar-nav">
            <p className="sidebar-nav-title">Recent</p>
            <button type="button" className="sidebar-nav-item active">Torah learning flow</button>
            <button type="button" className="sidebar-nav-item">Halacha Q&A</button>
            <button type="button" className="sidebar-nav-item">Source comparison</button>
          </nav>
        </Sidebar>

        <SidebarInset className="chat-main">
          <header className="chat-header">
            <div className="chat-header-left">
              <SidebarTrigger />
              <div>
                <h1>Chat Pane Runtime</h1>
                <p>same component architecture: Sidebar + BotInputArea + Message + ChainOfThought</p>
              </div>
            </div>
            <button className="ghost-button" type="button" onClick={() => setSourceOpen((v) => !v)}>Sources</button>
          </header>

          <section className="messages-pane">
            {messages.length === 0 ? (
              <div className="empty-state">
                <h2>Ready when you are</h2>
                <p>Ask a question to see streaming responses with chain-of-thought and source grouping.</p>
              </div>
            ) : (
              messages.map((msg) => (
                <Message key={msg.id} from={msg.role} className="max-w-3xl">
                  {msg.role === "assistant" && msg.reasoningSteps && msg.reasoningSteps.length > 0 ? (
                    <ChainOfThought>
                      <ChainOfThoughtHeader>Thinking</ChainOfThoughtHeader>
                      <ChainOfThoughtContent>
                        {msg.reasoningSteps.map((step) => (
                          <ChainOfThoughtStep
                            key={step.id}
                            label={step.label}
                            description={step.description}
                            status={step.status === "error" ? "pending" : step.status === "complete" ? "complete" : "active"}
                          />
                        ))}
                      </ChainOfThoughtContent>
                    </ChainOfThought>
                  ) : null}

                  <MessageContent>
                    <MessageResponse>{msg.content || (msg.role === "assistant" && isSending ? "Thinking..." : "")}</MessageResponse>
                  </MessageContent>

                  {msg.role === "assistant" ? (
                    <MessageActions>
                      <MessageAction onClick={() => navigator.clipboard.writeText(msg.content || "")} label="Copy">Copy</MessageAction>
                      <MessageAction onClick={() => handleSubmit({ text: "Retry and improve the previous answer", files: [] })} label="Retry">Retry</MessageAction>
                      <MessageAction label="Like">Like</MessageAction>
                    </MessageActions>
                  ) : null}
                </Message>
              ))
            )}
          </section>

          {runtimeError ? <div className="runtime-error">{runtimeError}</div> : null}

          <footer className="bot-input-area">
            <BotInputArea
              textareaRef={textareaRef}
              handleSubmit={handleSubmit}
              isLoading={isSending}
              animate={false}
            />
          </footer>
        </SidebarInset>

        <aside className={`source-pane ${sourceOpen ? "open" : "closed"}`}>
          <div className="source-pane-header">
            <h3>Sources</h3>
            <p>retrieval stream</p>
          </div>
          {sources.length === 0 ? (
            <p className="source-empty">No sources yet. Retrieved citations will appear here.</p>
          ) : (
            <ul className="source-list">
              {sources.map((source, idx) => (
                <li key={`${source.title}-${idx}`}>
                  <strong>{source.title}</strong>
                  {source.excerpt ? <span>{source.excerpt}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </aside>
        </div>
      </SidebarProvider>
    </DirectionProvider>
  );
}
