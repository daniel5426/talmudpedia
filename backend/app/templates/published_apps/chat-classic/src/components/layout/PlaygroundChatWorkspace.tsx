import { CopyIcon, RefreshCcwIcon, SearchIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { BotInputArea } from "@/components/BotInputArea";
import { AssistantResponseTimeline } from "@/components/ai-elements/assistant-response-timeline";
import {
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageAction,
  MessageActions,
  MessageContent,
} from "@/components/ai-elements/message";
import { ChatPaneHeader } from "@/components/navigation/ChatPaneHeader";
import { KesherLogo } from "@/components/ui/KesherLogo";
import type { StoredChatSession } from "@/hooks/use-template-chat";
import { cn } from "@/lib/utils";

interface PlaygroundChatWorkspaceProps {
  activeSession: StoredChatSession | null;
  activeSessionId: string | null;
  isStreaming: boolean;
  streamingAssistantId: string | null;
  runtimeError: string | null;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onSubmit: (payload: { text: string }) => void;
  onStop: () => void;
  onCopy: (content: string) => void;
  onRetry: (content: string) => void;
  onShareChat: (sessionId: string) => void;
  onDeleteChat: (sessionId: string) => void;
}

export function PlaygroundChatWorkspace({
  activeSession,
  activeSessionId,
  isStreaming,
  streamingAssistantId,
  runtimeError,
  textareaRef,
  onSubmit,
  onStop,
  onCopy,
  onRetry,
  onShareChat,
  onDeleteChat,
}: PlaygroundChatWorkspaceProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(1000);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  const hasMessages = Boolean(activeSession?.messages.length);
  const isEmptyState = !hasMessages && !isStreaming;

  return (
    <div
      ref={containerRef}
      className={cn(
        "mx-auto flex h-full w-full max-w-3xl flex-col",
        isEmptyState ? "px-4" : "border-none px-4 pb-4",
      )}
    >
      <ChatPaneHeader
        chatId={activeSessionId}
        isEmptyState={isEmptyState}
        onDeleteChat={activeSessionId ? () => onDeleteChat(activeSessionId) : undefined}
        onShareChat={activeSessionId ? () => onShareChat(activeSessionId) : undefined}
      />

      <ConversationContent
        scrollClassName="admin-page-scroll"
        className={cn(
          "flex-1 p-0 pt-13",
          !isEmptyState && "pb-30",
          isEmptyState && "relative z-10 h-full justify-center",
        )}
      >
        {isEmptyState ? (
          <div className="animate-in fade-in slide-in-from-bottom-4 flex w-full flex-col items-center pb-34 text-center duration-500">
            <p className="pb-6 text-3xl font-semibold">Ready when you are.</p>
            <BotInputArea
              textareaRef={textareaRef}
              handleSubmit={onSubmit}
              isLoading={isStreaming}
              onStop={onStop}
              animate={false}
            />
          </div>
        ) : (
          <>
            {activeSession?.messages.map((message, index) => {
              const showAvatar = message.role === "assistant" && containerWidth >= 550;
              const isActiveAssistant =
                message.role === "assistant" && message.id === streamingAssistantId;

              return (
                <div key={`${message.id}-${index}`} className="flex w-full">
                  {showAvatar ? (
                    <div className="mr-2 shrink-0">
                      <KesherLogo variant="avatar" />
                    </div>
                  ) : null}
                  <Message from={message.role} className="max-w-3xl">
                    <MessageContent>
                      {message.role === "assistant" && message.blocks?.length ? (
                        <div className="overflow-hidden">
                          <AssistantResponseTimeline
                            blocks={message.blocks}
                            isLoading={Boolean(isActiveAssistant && isStreaming)}
                          />
                        </div>
                      ) : (
                        <div className="overflow-hidden whitespace-pre-wrap">
                          {message.content}
                        </div>
                      )}
                    </MessageContent>

                    {message.role === "assistant" ? (
                      <div className="mt-1 h-9 w-full">
                        {!(isActiveAssistant && isStreaming) ? (
                          <MessageActions>
                            <MessageAction
                              label="Copy"
                              onClick={() => onCopy(message.content || "")}
                              tooltip="Copy to clipboard"
                            >
                              <CopyIcon className="size-4" />
                            </MessageAction>
                            <MessageAction label="Trace" disabled tooltip="Trace">
                              <SearchIcon className="size-4" />
                            </MessageAction>
                          </MessageActions>
                        ) : null}
                      </div>
                    ) : (
                      <MessageActions className="ml-auto mt-1">
                        <MessageAction
                          label="Retry"
                          onClick={() => onRetry(message.content)}
                          tooltip="Regenerate response"
                        >
                          <RefreshCcwIcon className="size-4" />
                        </MessageAction>
                      </MessageActions>
                    )}
                  </Message>
                </div>
              );
            })}

            {runtimeError ? (
              <div className="rounded-xl border border-destructive/25 bg-destructive/[0.08] px-4 py-3 text-sm text-destructive">
                {runtimeError}
              </div>
            ) : null}
          </>
        )}
      </ConversationContent>

      {!isEmptyState ? (
        <div className="relative">
          <ConversationScrollButton className="bottom-full mb-3" />
          <BotInputArea
            textareaRef={textareaRef}
            handleSubmit={onSubmit}
            isLoading={isStreaming}
            onStop={onStop}
          />
        </div>
      ) : null}
    </div>
  );
}
