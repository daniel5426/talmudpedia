import { useState } from "react";

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

import { ChatEmptyState } from "./chat-empty-state";
import { EMPTY_SUGGESTIONS } from "./demo-data";
import { ChatHeader } from "./chat-header";
import { useLocale } from "./locale-context";
import { ChatSidebar } from "./chat-sidebar";
import { ChatTimeline } from "./chat-timeline";
import { useSession } from "./session-context";
import { useClassicChatState } from "./use-classic-chat-state";

export function ClassicChatApp() {
  const [isAtTop, setIsAtTop] = useState(true);
  const { locale } = useLocale();
  const { isLoading: isLoadingSession, session, setSelectedClientId } = useSession();
  const {
    activeThread,
    activeThreadId,
    activeThreadHasOlderHistory,
    activeThreadIsLoadingOlderHistory,
    copiedMessageId,
    dislikedMessageIds,
    hasMoreHistory,
    inputValue,
    isLoadingHistory,
    isResponding,
    likedMessageIds,
    loadMoreHistory,
    loadOlderMessages,
    removeThread,
    newChat,
    retryAssistantMessage,
    setActiveThreadId,
    setInputValue,
    submitError,
    submitMessage,
    threads,
    toggleDislike,
    toggleLike,
    copyMessage,
  } = useClassicChatState();

  const hasMessages = Boolean(activeThread?.messages.length);
  const isActiveThreadLoading =
    isLoadingHistory || Boolean(activeThreadId && (!activeThread || !activeThread.isLoaded));

  return (
    <SidebarProvider
    
      defaultOpen
      className="h-svh bg-background overflow-hidden [&_button]:shadow-none"
    >
      <ChatSidebar
        activeThreadId={activeThreadId}
        hasMoreHistory={hasMoreHistory}
        onLoadMoreHistory={loadMoreHistory}
        onNewChat={newChat}
        onRemoveThread={removeThread}
        onSelectThread={setActiveThreadId}
        threads={threads}
      />

      <SidebarInset   className="min-h-0 bg-transparent overflow-hidden">
        <div className="flex h-full flex-col overflow-hidden">
          <ChatHeader
            clients={(session?.availableClients || []).map((client) => ({
              id: client.id,
              name: client.name,
              sector: client.sector,
            }))}
            isLoadingClients={isLoadingSession}
            isScrolled={!isAtTop && hasMessages}
            onSelectedClientChange={(clientId) => {
              void setSelectedClientId(clientId);
            }}
            selectedClientId={session?.selectedClientId || null}
          />

          <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
            {isActiveThreadLoading ? (
              <div className="flex min-h-0 flex-1 items-center justify-center px-4 text-sm text-muted-foreground">
                Loading chat...
              </div>
            ) : hasMessages && activeThread ? (
              <ChatTimeline
                copiedMessageId={copiedMessageId}
                dislikedMessageIds={dislikedMessageIds}
                errorMessage={submitError}
                inputValue={inputValue}
                isResponding={isResponding}
                likedMessageIds={likedMessageIds}
                messages={activeThread.messages}
                onCopyMessage={copyMessage}
                onInputValueChange={setInputValue}
                onLoadOlderMessages={loadOlderMessages}
                onRetryMessage={retryAssistantMessage}
                onSubmit={submitMessage}
                onToggleDislike={toggleDislike}
                onToggleLike={toggleLike}
                onTopVisibilityChange={setIsAtTop}
                hasOlderMessages={activeThreadHasOlderHistory}
                isLoadingOlderMessages={activeThreadIsLoadingOlderHistory}
              />
            ) : (
              <ChatEmptyState
                errorMessage={submitError}
                inputValue={inputValue}
                isResponding={isResponding}
                onInputValueChange={setInputValue}
                onSubmit={submitMessage}
                suggestions={EMPTY_SUGGESTIONS[locale]}
              />
            )}
          </main>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
