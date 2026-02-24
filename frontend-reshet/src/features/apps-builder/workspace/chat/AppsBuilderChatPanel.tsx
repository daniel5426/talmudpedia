import { useMemo, useState } from "react";
import {
  Clock,
  PanelRightClose,
  Plus,
  Sparkles,
  Square,
  Undo2,
  X,
} from "lucide-react";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
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
import {
  Queue,
  QueueItem,
  QueueItemAction,
  QueueItemActions,
  QueueItemContent,
  QueueItemIndicator,
  QueueList,
  QueueSection,
  QueueSectionContent,
  QueueSectionLabel,
  QueueSectionTrigger,
} from "@/components/ai-elements/queue";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Task, TaskContent, TaskItem, TaskItemFile, TaskTrigger } from "@/components/ai-elements/task";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { CodingAgentChatSession, LogicalModel } from "@/services";

import {
  TimelineItem,
  formatToolPathLabel,
  formatToolReadPath,
  isAssistantTimelineItem,
  isToolTimelineItem,
  isUserTimelineItem,
} from "./chat-model";
import type { QueuedPrompt } from "./useAppsBuilderChat";

type AppsBuilderChatPanelProps = {
  isOpen: boolean;
  onOpenChange: (next: boolean) => void;
  isSending: boolean;
  isStopping: boolean;
  isUndoing: boolean;
  timeline: TimelineItem[];
  activeThinkingSummary: string;
  chatSessions: CodingAgentChatSession[];
  onStartNewChat: () => void;
  onLoadChatSession: (sessionId: string) => Promise<void>;
  onSendMessage: (text: string) => Promise<void>;
  onStopRun: () => void;
  onRevertToCheckpoint: (userItemId: string, checkpointId: string) => Promise<void>;
  chatModels: LogicalModel[];
  selectedRunModelLabel: string;
  isModelSelectorOpen: boolean;
  onModelSelectorOpenChange: (next: boolean) => void;
  onSelectModelId: (modelId: string | null) => void;
  queuedPrompts: QueuedPrompt[];
  onRemoveQueuedPrompt: (promptId: string) => void;
};

export function AppsBuilderChatPanel({
  isOpen,
  onOpenChange,
  isSending,
  isStopping,
  isUndoing,
  timeline,
  activeThinkingSummary,
  chatSessions,
  onStartNewChat,
  onLoadChatSession,
  onSendMessage,
  onStopRun,
  onRevertToCheckpoint,
  chatModels,
  selectedRunModelLabel,
  isModelSelectorOpen,
  onModelSelectorOpenChange,
  onSelectModelId,
  queuedPrompts,
  onRemoveQueuedPrompt,
}: AppsBuilderChatPanelProps) {
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
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

  const renderedTimeline = useMemo(() => {
    const renderUserDeliveryLabel = (status?: TimelineItem["userDeliveryStatus"]) => {
      if (!status || status === "sent") return null;
      if (status === "pending") return "Sending...";
      if (status === "queued") return "Queued";
      return "Failed";
    };

    const isReadTool = (toolName?: string) => {
      const normalized = String(toolName || "").trim().toLowerCase();
      return normalized === "read" || normalized.includes("read_file");
    };
    const renderStandardToolRow = (item: TimelineItem) => {
      const status = item.toolStatus || "completed";
      return (
        <Message key={item.id} from="assistant" className="max-w-full">
          <MessageContent className="bg-transparent px-0 py-0 text-sm">
            <Task defaultOpen className="w-full">
              <TaskItem
                className={cn(
                  "flex items-center gap-2 text-sm",
                  status === "failed" ? "text-destructive" : "text-muted-foreground",
                )}
              >
                {status === "running" ? (
                  <Shimmer className="flex items-center gap-2 text-sm">
                    <span>{item.title}</span>
                    {item.toolPath ? <TaskItemFile>{formatToolPathLabel(item.toolPath)}</TaskItemFile> : null}
                  </Shimmer>
                ) : (
                  <>
                    <span>{item.title}</span>
                    {item.toolPath ? <TaskItemFile>{formatToolPathLabel(item.toolPath)}</TaskItemFile> : null}
                  </>
                )}
              </TaskItem>
            </Task>
          </MessageContent>
        </Message>
      );
    };

    const renderedItems: JSX.Element[] = [];
    let index = 0;

    while (index < timeline.length) {
      const item = timeline[index];
      if (isUserTimelineItem(item)) {
        renderedItems.push(
          <Message key={item.id} from="user" className="group/usermsg max-w-full">
            <MessageContent className="relative">
              <MessageResponse>{item.description || "Request submitted."}</MessageResponse>
              {renderUserDeliveryLabel(item.userDeliveryStatus) ? (
                <div className="mt-1 text-[11px] text-muted-foreground">
                  {renderUserDeliveryLabel(item.userDeliveryStatus)}
                </div>
              ) : null}
              {item.checkpointId && (
                <button
                  type="button"
                  className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-md bg-muted text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground group-hover/usermsg:opacity-100"
                  onClick={() => {
                    void onRevertToCheckpoint(item.id, item.checkpointId!);
                  }}
                  disabled={isUndoing}
                  aria-label="Revert to this point"
                >
                  <Undo2 className="h-3 w-3" />
                </button>
              )}
            </MessageContent>
          </Message>
        );
        index += 1;
        continue;
      }

      if (isAssistantTimelineItem(item)) {
        renderedItems.push(
          <Message key={item.id} from="assistant" className="max-w-full">
            <MessageContent className="bg-transparent px-0 py-0">
              <MessageResponse>
                {item.description ||
                  "I can help with code changes in this app workspace. Tell me what you want to change."}
              </MessageResponse>
            </MessageContent>
          </Message>
        );
        index += 1;
        continue;
      }

      if (isToolTimelineItem(item)) {
        if (isReadTool(item.toolName)) {
          const readStreak: TimelineItem[] = [];
          while (index < timeline.length) {
            const maybeRead = timeline[index];
            if (!isToolTimelineItem(maybeRead) || !isReadTool(maybeRead.toolName)) {
              break;
            }
            readStreak.push(maybeRead);
            index += 1;
          }

          const readCount = readStreak.length;
          const hasRunningRead = readStreak.some((entry) => (entry.toolStatus || "completed") === "running");
          const headerText = `Researching ${readCount} ${readCount === 1 ? "file" : "files"}`;

          renderedItems.push(
            <Message key={`read-group-${readStreak[0].id}`} from="assistant" className="max-w-full">
              <MessageContent className="bg-transparent px-0 py-0 text-sm">
                <Task defaultOpen={false} className="w-full">
                  <TaskTrigger asChild title={headerText}>
                    <button
                      type="button"
                      className="group flex w-full items-center justify-between gap-2 rounded-md px-0 py-0.5 text-left text-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {hasRunningRead ? (
                        <Shimmer className="text-sm">{headerText}</Shimmer>
                      ) : (
                        <span className="text-sm">{headerText}</span>
                      )}
                    </button>
                  </TaskTrigger>
                  <TaskContent className="mt-1">
                    {readStreak.map((readEntry) => {
                      const readStatus = readEntry.toolStatus || "completed";
                      const readPath = formatToolReadPath(String(readEntry.toolPath || ""));
                      const readTitle = readPath ? `Reading file ${readPath}` : "Reading file";
                      return (
                        <TaskItem
                          key={readEntry.id}
                          className={cn("flex items-center gap-2 text-sm", readStatus === "failed" ? "text-destructive" : "text-muted-foreground")}
                        >
                          {readStatus === "running" ? (
                            <Shimmer className="text-sm">{readTitle}</Shimmer>
                          ) : (
                            <span>{readTitle}</span>
                          )}
                        </TaskItem>
                      );
                    })}
                  </TaskContent>
                </Task>
              </MessageContent>
            </Message>,
          );
          continue;
        }

        renderedItems.push(renderStandardToolRow(item));
        index += 1;
        continue;
      }

      renderedItems.push(
        <Message key={item.id} from="assistant" className="max-w-full">
          <MessageContent className="bg-transparent px-0 py-0 text-xs text-muted-foreground">
            <div>
              {item.title}
              {item.description ? ` ${item.description}` : ""}
            </div>
          </MessageContent>
        </Message>
      );
      index += 1;
    }

    return renderedItems;
  }, [isUndoing, onRevertToCheckpoint, timeline]);

  if (!isOpen) {
    return (
      <div className="flex h-full w-10 shrink-0 flex-col items-center border-l border-border/60 bg-muted/20 pt-3">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => onOpenChange(true)}
          aria-label="Open agent panel"
        >
          <Sparkles className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <aside className="flex h-full min-h-0 w-[430px] shrink-0 flex-col overflow-hidden border-l border-border/60 bg-background">
      <div className="flex items-center justify-end gap-0.5 px-2 py-1.5">
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-muted-foreground hover:text-foreground"
          onClick={onStartNewChat}
          aria-label="New chat"
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-muted-foreground hover:text-foreground"
          onClick={() => setIsHistoryOpen(true)}
          aria-label="Chat history"
        >
          <Clock className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-muted-foreground hover:text-foreground"
          onClick={() => onOpenChange(false)}
          aria-label="Close agent panel"
        >
          <PanelRightClose className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col px-3 pb-3">
        <Conversation className="flex min-h-0 flex-1 flex-col">
          <ConversationContent className="gap-2 px-0 py-0 pb-3">
            {renderedTimeline}
            {isSending && !hasRunningTool && !hasCurrentRunAssistantStream ? (
              <Message from="assistant" className="max-w-full">
                <MessageContent className="bg-transparent px-0 py-0 text-sm text-muted-foreground">
                  <Shimmer className="text-sm">
                    {`Reasoning...${activeThinkingSummary && activeThinkingSummary !== "Thinking..." ? ` ${activeThinkingSummary}` : ""}`}
                  </Shimmer>
                </MessageContent>
              </Message>
            ) : null}
          </ConversationContent>
          <ConversationScrollButton />
        </Conversation>

        {queuedPrompts.length > 0 ? (
          <Queue className="mb-2">
            <QueueSection defaultOpen>
              <QueueSectionTrigger>
                <QueueSectionLabel count={queuedPrompts.length} label="queued prompts" />
              </QueueSectionTrigger>
              <QueueSectionContent>
                <QueueList>
                  {queuedPrompts.map((prompt) => (
                    <QueueItem key={prompt.id}>
                      <div className="flex items-start gap-2">
                        <QueueItemIndicator />
                        <QueueItemContent>{prompt.text}</QueueItemContent>
                        <QueueItemActions>
                          <QueueItemAction
                            aria-label="Remove queued prompt"
                            onClick={() => onRemoveQueuedPrompt(prompt.id)}
                            title="Remove"
                          >
                            <X className="h-3 w-3" />
                          </QueueItemAction>
                        </QueueItemActions>
                      </div>
                    </QueueItem>
                  ))}
                </QueueList>
              </QueueSectionContent>
            </QueueSection>
          </Queue>
        ) : null}

        <div className="shrink-0 pt-1">
          <PromptInput
            onSubmit={async (message) => {
              await onSendMessage(message.text);
            }}
            className="rounded-xl border border-border/40 bg-muted/30 shadow-none"
          >
            <PromptInputBody>
              <PromptInputTextarea
                placeholder="Plan, @ for context, / for commands"
                className="min-h-10 max-h-40 bg-transparent px-3 pt-2.5 text-sm"
              />
            </PromptInputBody>
            <PromptInputFooter className="justify-between px-2 pb-1.5 pt-0">
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
                    <ModelSelectorEmpty>No active chat models</ModelSelectorEmpty>
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
                          value={`${model.name} ${model.slug}`}
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
                <PromptInputSubmit
                  size="icon-sm"
                  variant="ghost"
                  className="h-6 w-6 text-muted-foreground hover:text-foreground"
                  aria-label="Send"
                />
              )}
            </PromptInputFooter>
          </PromptInput>
        </div>
      </div>

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
                        void onLoadChatSession(session.id);
                        setIsHistoryOpen(false);
                      }}
                    >
                      <div className="whitespace-normal text-sm leading-snug [overflow-wrap:anywhere]">{session.title}</div>
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
