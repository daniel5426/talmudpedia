import type { ChatMessage } from "./types";
import { MenuIcon, SendIcon } from "../icons";

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
    <div className="chat-pane">
      <header className="chat-pane-header">
        <button type="button" className="icon-button" onClick={onToggleSidebar}>
          <MenuIcon />
        </button>
        <div className="chat-pane-title">
          <h1>{appTitle}</h1>
          <p>Production-grade shell template</p>
        </div>
        <button type="button" className="ghost-button" onClick={onToggleSourceList}>
          Sources
        </button>
      </header>

      <section className="chat-messages" aria-label="Messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <h2>Start a conversation</h2>
            <p>This shell mirrors your current workspace layout while staying fully generic.</p>
          </div>
        ) : (
          messages.map((message) => (
            <article key={message.id} className={`chat-bubble-row ${message.role === "user" ? "user" : "assistant"}`}>
              <div className="chat-bubble">{message.content || (message.role === "assistant" ? "..." : "")}</div>
            </article>
          ))
        )}
      </section>

      {runtimeError ? <div className="runtime-error">{runtimeError}</div> : null}

      <footer className="chat-input-bar">
        <textarea
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          className="chat-input"
          placeholder="Send a message..."
          rows={1}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSubmit();
            }
          }}
        />
        <button type="button" className="send-button" onClick={onSubmit} disabled={isSending}>
          <SendIcon width={15} height={15} />
          {isSending ? "Sending" : "Send"}
        </button>
      </footer>
    </div>
  );
}
