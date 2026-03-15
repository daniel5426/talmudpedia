import { useEffect, useMemo } from "react";
import { Copy, RotateCcw } from "lucide-react";

import { AssistantResponseTimeline } from "@/components/ai-elements/assistant-response-timeline";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageAction,
  MessageActions,
  MessageContent,
} from "@/components/ai-elements/message";
import { BotInputArea } from "@/components/BotInputArea";
import { DirectionProvider, useDirection } from "@/components/direction-provider";
import { AppSidebar } from "@/components/navigation/AppSidebar";
import { ChatPaneHeader } from "@/components/navigation/ChatPaneHeader";
import { ThemeProvider } from "@/components/theme-provider";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useTemplateChat } from "@/hooks/use-template-chat";
import { cn } from "@/lib/utils";

function ChatShell() {
  const {
    sessions,
    activeSession,
    activeSessionId,
    isStreaming,
    streamingAssistantId,
    runtimeError,
    textareaRef,
    selectSession,
    startNewChat,
    removeSession,
    shareSession,
    resendPrompt,
    copyMessage,
    handleSubmit,
    stopStreaming,
  } = useTemplateChat();
  const { direction } = useDirection();

  const hasMessages = Boolean(activeSession?.messages.length);
  const isEmptyState = !hasMessages && !isStreaming;
  const orderedSessions = useMemo(
    () =>
      [...sessions].sort(
        (left, right) =>
          new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime(),
      ),
    [sessions],
  );

  useEffect(() => {
    document.title = activeSession?.title
      ? `${activeSession.title} | Agent Template`
      : "Agent Template";
  }, [activeSession?.title]);

  return (
    <SidebarProvider defaultOpen>
      <div className="flex h-screen w-full bg-background text-foreground">
        <AppSidebar
          sessions={orderedSessions}
          activeSessionId={activeSessionId}
          onNewChat={startNewChat}
          onSelectSession={selectSession}
          onDeleteSession={removeSession}
          onShareSession={shareSession}
        />
        <SidebarInset className="min-w-0 bg-background">
          <main className="flex h-screen min-w-0">
            <Conversation
              dir={direction}
              className="chat-surface relative flex-1 overflow-hidden border-none"
            >
              <div
                aria-hidden="true"
                className={cn(
                  "chat-empty-gradient pointer-events-none absolute inset-0 transition-opacity duration-700 ease-in-out",
                  isEmptyState ? "opacity-100" : "opacity-0",
                )}
              />
              <ChatPaneHeader
                isEmptyState={isEmptyState}
                title={activeSession?.title || "New conversation"}
                subtitle="Polished base runtime shell for generic agents"
              />
              <div
                className={cn(
                  "relative z-10 mx-auto flex h-full w-full max-w-3xl flex-col",
                  isEmptyState ? "px-4" : "px-4 pb-4",
                )}
                dir={direction}
              >
                <ConversationContent
                  className={cn(
                    "flex-1 gap-6 p-0 pt-[3.25rem]",
                    isEmptyState ? "h-full justify-center pb-20" : "pb-32",
                  )}
                >
                  {isEmptyState ? (
                    <div className="animate-in fade-in slide-in-from-bottom-4 flex w-full flex-col items-center text-center duration-500">
                      <div className="glass-panel shadow-soft mb-8 rounded-3xl border border-border/60 px-5 py-2">
                        <p className="text-[11px] font-medium uppercase tracking-[0.24em] text-muted-foreground">
                          Standard Agent Base
                        </p>
                      </div>
                      <p className="pb-6 text-3xl font-semibold tracking-tight">
                        Ready when you are.
                      </p>
                      <p className="pb-8 text-sm text-muted-foreground">
                        Ask in plain language. Tool activity, reasoning progress, and streaming
                        responses land in the same timeline.
                      </p>
                      <BotInputArea
                        textareaRef={textareaRef}
                        handleSubmit={handleSubmit}
                        isLoading={isStreaming}
                        onStop={stopStreaming}
                        animate={false}
                      />
                    </div>
                  ) : (
                    <>
                      {activeSession?.messages.map((message) => {
                        const isActiveAssistant =
                          message.role === "assistant" &&
                          message.id === streamingAssistantId;
                        return (
                          <Message
                            key={message.id}
                            from={message.role}
                            className="max-w-full"
                          >
                            <MessageContent
                              className={cn(
                                message.role === "assistant" &&
                                  "bg-transparent px-0 py-0",
                              )}
                            >
                              {message.role === "assistant" && message.blocks?.length ? (
                                <AssistantResponseTimeline
                                  blocks={message.blocks}
                                  isLoading={Boolean(isActiveAssistant && isStreaming)}
                                />
                              ) : (
                                <div className="whitespace-pre-wrap text-sm leading-7">
                                  {message.content}
                                </div>
                              )}
                            </MessageContent>
                            {message.role === "assistant" ? (
                              <MessageActions className="mt-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
                                <MessageAction
                                  tooltip="Copy response"
                                  onClick={() => copyMessage(message.content)}
                                >
                                  <Copy className="size-3.5" />
                                </MessageAction>
                              </MessageActions>
                            ) : (
                              <MessageActions className="ml-auto mt-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover/usermsg:opacity-100">
                                <MessageAction
                                  tooltip="Send again"
                                  onClick={() => resendPrompt(message.content)}
                                >
                                  <RotateCcw className="size-3.5" />
                                </MessageAction>
                              </MessageActions>
                            )}
                          </Message>
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
                      handleSubmit={handleSubmit}
                      isLoading={isStreaming}
                      onStop={stopStreaming}
                    />
                  </div>
                ) : null}
              </div>
            </Conversation>
          </main>
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}

export function App() {
  return (
    <ThemeProvider>
      <DirectionProvider initialDirection="ltr">
        <ChatShell />
      </DirectionProvider>
    </ThemeProvider>
  );
}
