import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Clock,
  GitBranch,
  Plus,
  Square,
  X,
} from "lucide-react";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { ChatContextStatus } from "@/components/ai-elements/chat-context-status";
import {
  ModelSelector,
  ModelSelectorContent,
  ModelSelectorEmpty,
  ModelSelectorGroup,
  ModelSelectorInput,
  ModelSelectorItem,
  ModelSelectorList,
  ModelSelectorName,
  ModelSelectorTrigger,
} from "@/components/ai-elements/model-selector";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
} from "@/components/ai-elements/prompt-input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { AppVersionListItem, CodingAgentChatSession, OpenCodeCodingModelOption, PublishedAppRevision } from "@/services";
import type { ContextWindow } from "@/services/context-window";

import {
  TimelineItem,
  isExplorationToolName,
  isAssistantTimelineItem,
  isToolTimelineItem,
  isUserTimelineItem,
} from "./chat-model";
import { AppsBuilderChatScrollBindings } from "./AppsBuilderChatScrollBindings";
import { AppsBuilderChatQuestionPanel } from "./AppsBuilderChatQuestionPanel";
import { AppsBuilderChatTimeline } from "./AppsBuilderChatTimeline";
import type { CodingAgentPendingQuestion } from "./stream-parsers";
import type { QueuedPrompt } from "./useAppsBuilderChat";
import { AppsBuilderVersionHistoryPanel } from "./AppsBuilderVersionHistoryPanel";
import { useAppsBuilderChatThreadTabs } from "./useAppsBuilderChat.thread-tabs";

type AppsBuilderChatPanelProps = {
  isOpen: boolean;
  isSending: boolean;
  isStopping: boolean;
  timeline: TimelineItem[];
  activeThinkingSummary: string;
  activeContextStatus: ContextWindow | null;
  chatSessions: CodingAgentChatSession[];
  activeChatSessionId: string | null;
  onActivateDraftChat: () => void;
  onStartNewChat: () => void;
  onOpenHistory: () => void;
  onLoadChatSession: (sessionId: string) => Promise<void>;
  onSendMessage: (text: string) => Promise<void>;
  onStopRun: () => void;
  chatModels: OpenCodeCodingModelOption[];
  selectedRunModelLabel: string;
  isModelSelectorOpen: boolean;
  onModelSelectorOpenChange: (next: boolean) => void;
  onSelectModelId: (modelId: string | null) => void;
  queuedPrompts: QueuedPrompt[];
  pendingQuestion: CodingAgentPendingQuestion | null;
  isAnsweringQuestion: boolean;
  isSendBlockedBySandbox: boolean;
  sendBlockedReason: string | null;
  runningSessionIds: string[];
  sendingSessionIds: string[];
  sessionTitleHintsBySessionId: Record<string, string>;
  hasOlderHistory: boolean;
  isLoadingOlderHistory: boolean;
  onLoadOlderHistory: () => Promise<void>;
  onRemoveQueuedPrompt: (promptId: string) => void;
  onAnswerQuestion: (answers: string[][]) => Promise<void>;
  versions: AppVersionListItem[];
  selectedVersionId: string | null;
  selectedVersion: PublishedAppRevision | null;
  isLoadingVersions: boolean;
  isRestoringVersion: boolean;
  isPublishingVersion: boolean;
  publishStatus: string | null;
  onRefreshVersions: () => void;
  onSelectVersion: (versionId: string) => void;
  onRestoreVersion: (versionId?: string) => void;
  onPublishVersion: (versionId?: string) => void;
  onViewCodeVersion: (versionId: string) => void;
};

export function AppsBuilderChatPanel({
  isOpen,
  isSending,
  isStopping,
  timeline,
  activeThinkingSummary,
  activeContextStatus,
  chatSessions,
  activeChatSessionId,
  onActivateDraftChat,
  onStartNewChat,
  onOpenHistory,
  onLoadChatSession,
  onSendMessage,
  onStopRun,
  chatModels,
  selectedRunModelLabel,
  isModelSelectorOpen,
  onModelSelectorOpenChange,
  onSelectModelId,
  queuedPrompts,
  pendingQuestion,
  isAnsweringQuestion,
  isSendBlockedBySandbox,
  sendBlockedReason,
  runningSessionIds,
  sendingSessionIds,
  sessionTitleHintsBySessionId,
  hasOlderHistory,
  isLoadingOlderHistory,
  onLoadOlderHistory,
  onRemoveQueuedPrompt,
  onAnswerQuestion,
  versions,
  selectedVersionId,
  selectedVersion,
  isLoadingVersions,
  isRestoringVersion,
  isPublishingVersion,
  publishStatus,
  onRefreshVersions,
  onSelectVersion,
  onRestoreVersion,
  onPublishVersion,
  onViewCodeVersion,
}: AppsBuilderChatPanelProps) {
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isVersionsOpen, setIsVersionsOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const [scrollContainer, setScrollContainer] = useState<HTMLElement | null>(null);
  const topSentinelRef = useRef<HTMLDivElement>(null);
  const isLoadingOlderRef = useRef(false);
  const wasVersionsOpenRef = useRef(false);
  const handleScrollContainerChange = useCallback((node: HTMLElement | null) => {
    setScrollContainer((current) => (current === node ? current : node));
  }, []);

  useEffect(() => {
    const sentinel = topSentinelRef.current;
    const root = scrollContainer;
    if (!sentinel || !root) return;
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) {
          return;
        }
        if (!hasOlderHistory || isLoadingOlderHistory || isLoadingOlderRef.current) {
          return;
        }
        const scrollNode = root;
        const previousHeight = scrollNode?.scrollHeight || 0;
        const previousTop = scrollNode?.scrollTop || 0;
        isLoadingOlderRef.current = true;
        void onLoadOlderHistory().finally(() => {
          if (scrollNode) {
            const nextHeight = scrollNode.scrollHeight;
            scrollNode.scrollTop = nextHeight - previousHeight + previousTop;
          }
          isLoadingOlderRef.current = false;
        });
      },
      { root, threshold: 0 }
    );
    observer.observe(sentinel);
    return () => {
      observer.disconnect();
    };
  }, [hasOlderHistory, isLoadingOlderHistory, onLoadOlderHistory, scrollContainer]);

  useEffect(() => {
    const scrollNode = scrollContainer;
    if (!scrollNode) return;

    const handleScroll = () => {
      setIsScrolled(scrollNode.scrollTop > 5);
    };

    scrollNode.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => scrollNode.removeEventListener("scroll", handleScroll);
  }, [scrollContainer]);

  useEffect(() => {
    const wasOpen = wasVersionsOpenRef.current;
    wasVersionsOpenRef.current = isVersionsOpen;
    if (!isVersionsOpen || wasOpen) {
      return;
    }
    onRefreshVersions();
  }, [isVersionsOpen, onRefreshVersions]);

  const hasRunningTool = useMemo(
    () => timeline.some((item) => isToolTimelineItem(item) && item.toolStatus === "running"),
    [timeline],
  );
  const lastUserIndex = useMemo(() => {
    for (let index = timeline.length - 1; index >= 0; index -= 1) {
      if (isUserTimelineItem(timeline[index])) {
        return index;
      }
    }
    return -1;
  }, [timeline]);
  const hasCurrentRunAssistantStream = useMemo(() => {
    if (lastUserIndex < 0) {
      return false;
    }
    for (let index = lastUserIndex + 1; index < timeline.length; index += 1) {
      const item = timeline[index];
      if (isAssistantTimelineItem(item) && item.assistantStreamId) {
        return true;
      }
    }
    return false;
  }, [lastUserIndex, timeline]);
  const lastToolAfterCurrentUser = useMemo(() => {
    if (lastUserIndex < 0) return null;
    for (let index = timeline.length - 1; index > lastUserIndex; index -= 1) {
      const item = timeline[index];
      if (isToolTimelineItem(item)) {
        return item;
      }
    }
    return null;
  }, [lastUserIndex, timeline]);
  const lastToolAfterCurrentUserIsExploration = useMemo(
    () => Boolean(lastToolAfterCurrentUser && isExplorationToolName(String(lastToolAfterCurrentUser.toolName || ""))),
    [lastToolAfterCurrentUser],
  );
  const {
    threadTabs,
    handleOpenThreadTab,
    handleStartNewThreadTab,
    handleActivateDraftThreadTab,
    handleCloseThreadTab,
    handleTabsWheel,
  } = useAppsBuilderChatThreadTabs({
    chatSessions,
    activeChatSessionId,
    runningSessionIds: Array.from(new Set([...runningSessionIds, ...sendingSessionIds])),
    timeline,
    sessionTitleHintsBySessionId,
    onActivateDraftChat,
    onLoadChatSession,
    onStartNewChat,
  });
  const runningSessionIdSet = useMemo(
    () => new Set([...runningSessionIds, ...sendingSessionIds]),
    [runningSessionIds, sendingSessionIds],
  );
  const sendBlocked = !isSending && (isAnsweringQuestion || isSendBlockedBySandbox);
  const sendBlockedHint = isAnsweringQuestion
    ? "Answer the pending question before sending a new prompt."
    : sendBlockedReason;

  if (!isOpen) {
    return null;
  }

  return (
    <aside className="flex h-full min-h-0 w-[430px] shrink-0 flex-col overflow-hidden border-l border-border/60 bg-background">
      {!isVersionsOpen ? (
        <div className="relative z-10 flex h-7 pt-2 shrink-0 items-center gap-1 px-2 bg-background">
          <div
            className={cn(
              "pointer-events-none absolute mt-1 inset-x-0 top-full z-10 h-8 bg-gradient-to-b from-background via-background/90 to-transparent transition-opacity duration-300",
              isScrolled ? "opacity-100" : "opacity-0"
            )}
            aria-hidden="true"
          />
          <div
            className="min-w-0 flex-1 overflow-x-auto overflow-y-hidden [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
            onWheel={handleTabsWheel}
          >
            <div className="flex w-max items-center gap-1 pr-2">
              {threadTabs.map((session) => {
                const isSessionTab = session.kind === "session" || session.kind === "provisional";
                const sessionId = session.kind === "session"
                  ? session.session.id
                  : session.kind === "provisional"
                    ? session.sessionId
                    : "__draft__";
                const sessionTitle = session.title;
                const isActive = isSessionTab
                  ? activeChatSessionId === sessionId
                  : !activeChatSessionId;
                return (
                  <div key={session.id} className="h-7.5 group/thread relative shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      className={cn(
                        "h-7 max-w-[150px] shrink-0 gap-1 rounded-md px-2 text-[12px]",
                        isActive
                          ? "bg-muted text-foreground"
                          : "text-muted-foreground hover:text-foreground group-hover/thread:bg-muted group-hover/thread:text-foreground",
                      )}
                      onClick={() => {
                        if (session.kind === "draft") {
                          handleActivateDraftThreadTab();
                          return;
                        }
                        if (isSessionTab) {
                          handleOpenThreadTab(sessionId);
                          return;
                        }
                        handleStartNewThreadTab();
                      }}
                      aria-label={`Open chat ${sessionTitle}`}
                    >
                      <span className="truncate">{sessionTitle}</span>
                      {isSessionTab && runningSessionIdSet.has(sessionId) ? (
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
                      ) : null}
                    </Button>
                    <button
                      type="button"
                      aria-label={`Close tab ${sessionTitle}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        handleCloseThreadTab(sessionId);
                      }}
                      className="absolute inset-y-0 bg-muted hover:bg-muted right-0.5 my-auto flex h-fit w-fit items-center justify-center rounded-sm text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 group-hover/thread:opacity-100"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-foreground"
            onClick={handleStartNewThreadTab}
            aria-label="Create new chat"
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-foreground"
            onClick={() => {
              onOpenHistory();
              setIsHistoryOpen(true);
            }}
            aria-label="Chat history"
          >
            <Clock className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              "h-6 w-6 text-muted-foreground hover:text-foreground",
              isVersionsOpen ? "bg-muted text-foreground" : "",
            )}
            onClick={() => setIsVersionsOpen((prev) => !prev)}
            aria-label="Version history"
          >
            <GitBranch className="h-3.5 w-3.5" />
          </Button>
        </div>
      ) : null}
      {isVersionsOpen ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <AppsBuilderVersionHistoryPanel
            versions={versions}
            selectedVersionId={selectedVersionId}
            selectedVersion={selectedVersion}
            isLoadingVersions={isLoadingVersions}
            isRestoringVersion={isRestoringVersion}
            isPublishingVersion={isPublishingVersion}
            publishStatus={publishStatus}
            onClose={() => setIsVersionsOpen(false)}
            onRefreshVersions={onRefreshVersions}
            onSelectVersion={onSelectVersion}
            onRestoreVersion={onRestoreVersion}
            onPublishVersion={onPublishVersion}
            onViewCodeVersion={onViewCodeVersion}
            onOpenHistory={() => {
              onOpenHistory();
              setIsHistoryOpen(true);
            }}
          />
        </div>
      ) : (
        <div className="flex min-h-0 pt-1 flex-1 flex-col px-3 pb-3">
        <Conversation className="flex min-h-0 pb-[-200px] flex-1 flex-col transition-all">
          <AppsBuilderChatScrollBindings onScrollContainerChange={handleScrollContainerChange} />
          <ConversationContent className="gap-2 px-0 py-0 pb-3">
            <AppsBuilderChatTimeline
              timeline={timeline}
              isSending={isSending}
              activeThinkingSummary={activeThinkingSummary}
              isLoadingOlderHistory={isLoadingOlderHistory}
              hasRunningTool={hasRunningTool}
              hasCurrentRunAssistantStream={hasCurrentRunAssistantStream}
              lastToolAfterCurrentUserIsExploration={lastToolAfterCurrentUserIsExploration}
              topSentinelRef={topSentinelRef}
            />
          </ConversationContent>
          <ConversationScrollButton />
        </Conversation>

        {queuedPrompts.length > 0 ? (
          <section
            aria-label="Queued prompts"
            data-testid="queued-prompts-panel"
            className="mb-2 overflow-hidden rounded-lg border border-border/50 bg-muted/20"
          >
            <header className="flex items-center justify-between border-b border-border/50 px-3 py-1.5">
              <p className="text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground">Queue</p>
              <span className="text-[11px] text-muted-foreground">{queuedPrompts.length}</span>
            </header>
            <ul className="max-h-28 space-y-0.5 overflow-y-auto p-1.5" role="list">
              {queuedPrompts.map((prompt, index) => (
                <li
                  key={prompt.id}
                  className="group flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-background/80"
                >
                  <span className="mt-0.5 text-[10px] text-muted-foreground">{index + 1}.</span>
                  <p className="min-w-0 flex-1 line-clamp-2 text-xs leading-5 text-foreground/90">{prompt.text}</p>
                  <button
                    type="button"
                    aria-label="Remove queued prompt"
                    onClick={() => onRemoveQueuedPrompt(prompt.id)}
                    className="inline-flex h-5 w-5 items-center justify-center rounded-sm bg-muted text-muted-foreground opacity-70 transition-colors hover:bg-accent hover:text-foreground"
                    title="Remove"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {pendingQuestion ? (
          <AppsBuilderChatQuestionPanel
            key={pendingQuestion.requestId}
            pendingQuestion={pendingQuestion}
            isAnsweringQuestion={isAnsweringQuestion}
            onAnswerQuestion={onAnswerQuestion}
          />
        ) : null}

        <div className="shrink-0 bg-transparent">
          <PromptInput
            onSubmit={async (message) => {
              await onSendMessage(message.text);
            }}
            className="rounded-xl border border-border bg-transparent shadow-none"
          >
            <PromptInputBody className="bg-transparent">
              <PromptInputTextarea
                placeholder="Plan, @ for context, / for commands"
                className="min-h-15 max-h-40 bg-transparent px-3 pt-2.5 text-sm"
                disabled={isAnsweringQuestion}
              />
            </PromptInputBody>
            <PromptInputFooter className="justify-between px-2 pb-1.5 pt-0">
              <div className="flex items-center gap-1">
                <ModelSelector open={isModelSelectorOpen} onOpenChange={onModelSelectorOpenChange}>
                  <ModelSelectorTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground"
                      aria-label="Select run model"
                    >
                      {selectedRunModelLabel}
                    </Button>
                  </ModelSelectorTrigger>
                  <ModelSelectorContent className="max-w-xs">
                    <ModelSelectorInput placeholder="Search models..." />
                    <ModelSelectorList>
                      <ModelSelectorEmpty>No OpenCode models</ModelSelectorEmpty>
                      <ModelSelectorGroup heading="Run model">
                        <ModelSelectorItem
                          value="auto"
                          onSelect={() => {
                            onSelectModelId(null);
                            onModelSelectorOpenChange(false);
                          }}
                        >
                          <ModelSelectorName>Auto</ModelSelectorName>
                        </ModelSelectorItem>
                        {chatModels.map((model) => (
                          <ModelSelectorItem
                            key={model.id}
                            value={`${model.name} ${model.id}`}
                            onSelect={() => {
                              onSelectModelId(model.id);
                              onModelSelectorOpenChange(false);
                            }}
                          >
                            <ModelSelectorName>{model.name}</ModelSelectorName>
                          </ModelSelectorItem>
                        ))}
                      </ModelSelectorGroup>
                    </ModelSelectorList>
                  </ModelSelectorContent>
                </ModelSelector>
                <ChatContextStatus contextStatus={activeContextStatus} />
              </div>
              {isSending ? (
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-6 w-6 text-muted-foreground hover:text-foreground"
                  onClick={onStopRun}
                  aria-label={isStopping ? "Stopping" : "Stop"}
                >
                  <Square className="h-3 w-3 fill-current" />
                </Button>
              ) : (
                sendBlocked && sendBlockedHint ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="inline-flex">
                        <PromptInputSubmit
                          size="icon-sm"
                          variant="ghost"
                          className="h-6 w-6 text-muted-foreground hover:text-foreground"
                          aria-label="Send"
                          disabled
                        />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top">{sendBlockedHint}</TooltipContent>
                  </Tooltip>
                ) : (
                  <PromptInputSubmit
                    size="icon-sm"
                    variant="ghost"
                    className="h-6 w-6 text-muted-foreground hover:text-foreground"
                    aria-label="Send"
                    disabled={sendBlocked}
                  />
                )
              )}
            </PromptInputFooter>
          </PromptInput>
        </div>
        </div>
      )}

      <Dialog open={isHistoryOpen} onOpenChange={setIsHistoryOpen}>
        <DialogContent className="w-[min(44rem,calc(100vw-2rem))] max-w-[calc(100vw-2rem)] overflow-hidden p-0 sm:max-w-2xl">
          <div className="flex max-h-[75vh] min-h-0 flex-col p-6">
            <DialogHeader className="shrink-0 pr-8">
              <DialogTitle>Chat History</DialogTitle>
            </DialogHeader>
            <div className="mt-2 min-h-0 flex-1 overflow-y-auto">
              <div className="flex flex-col gap-1 pb-1">
                {chatSessions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No previous chats yet.</p>
                ) : (
                  chatSessions.map((session) => (
                    <button
                      key={session.id}
                      type="button"
                      className="w-full overflow-hidden rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-muted"
                      onClick={() => {
                        handleOpenThreadTab(session.id);
                        setIsHistoryOpen(false);
                      }}
                    >
                      <div className="flex items-center gap-2">
                        <div className="whitespace-normal text-sm leading-snug [overflow-wrap:anywhere]">{session.title}</div>
                        {runningSessionIdSet.has(session.id) ? (
                          <span
                            className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500"
                            aria-label="Session has an active run"
                          />
                        ) : null}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {new Date(session.last_message_at).toLocaleDateString()}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </aside>
  );
}
