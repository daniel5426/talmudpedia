import { useMemo, useState } from "react";
import {
  Clock,
  PanelRightClose,
  Plus,
  Sparkles,
  Square,
  Undo2,
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
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { CodingAgentChatSession, LogicalModel } from "@/services";

import {
  TimelineItem,
  isAssistantTimelineItem,
  isToolTimelineItem,
  isUserTimelineItem,
} from "./chat-model";

type AppsBuilderChatPanelProps = {
  isOpen: boolean;
  onOpenChange: (next: boolean) => void;
  isSending: boolean;
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
};

export function AppsBuilderChatPanel({
  isOpen,
  onOpenChange,
  isSending,
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
}: AppsBuilderChatPanelProps) {
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);

  const renderedTimeline = useMemo(() => {
    if (timeline.length === 0) {
      return (
        <Message from="assistant" className="max-w-full">
          <MessageContent className="bg-transparent px-0 py-0 text-sm text-muted-foreground">
            <MessageResponse>
              Ask for a code change to start a live run. You will see tool calls and assistant responses here.
            </MessageResponse>
          </MessageContent>
        </Message>
      );
    }

    const rendered: JSX.Element[] = [];
    let i = 0;
    while (i < timeline.length) {
      const item = timeline[i];

      if (isUserTimelineItem(item)) {
        rendered.push(
          <Message key={item.id} from="user" className="group/usermsg max-w-full">
            <MessageContent className="relative">
              <MessageResponse>{item.description || "Request submitted."}</MessageResponse>
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
          </Message>,
        );
        i++;
        continue;
      }

      if (isAssistantTimelineItem(item)) {
        rendered.push(
          <Message key={item.id} from="assistant" className="max-w-full">
            <MessageContent className="bg-transparent px-0 py-0">
              <MessageResponse>
                {item.description ||
                  "I can help with code changes in this app workspace. Tell me what you want to change."}
              </MessageResponse>
            </MessageContent>
          </Message>,
        );
        i++;
        continue;
      }

      if (isToolTimelineItem(item)) {
        if (item.title === "Reading file") {
          const groupStart = i;
          let readCount = 0;
          let hasRunning = false;
          while (i < timeline.length && isToolTimelineItem(timeline[i]) && timeline[i].title === "Reading file") {
            readCount++;
            if (timeline[i].toolStatus === "running") hasRunning = true;
            i++;
          }
          rendered.push(
            <Message key={timeline[groupStart].id} from="assistant" className="max-w-full">
              <MessageContent className="bg-transparent px-0 py-0 text-xs">
                <div className="inline-flex items-center gap-2 rounded-md px-1 py-0.5">
                  <span
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      hasRunning ? "animate-pulse bg-foreground/70" : "bg-emerald-500",
                    )}
                  />
                  <span
                    className={cn(
                      "text-xs",
                      hasRunning ? "animate-pulse text-foreground/75" : "text-muted-foreground",
                    )}
                  >
                    Explored {readCount} {readCount === 1 ? "file" : "files"}
                  </span>
                </div>
              </MessageContent>
            </Message>,
          );
          continue;
        }

        const status = item.toolStatus || "completed";
        rendered.push(
          <Message key={item.id} from="assistant" className="max-w-full">
            <MessageContent className="bg-transparent px-0 py-0 text-xs">
              <div className="inline-flex items-center gap-2 rounded-md px-1 py-0.5">
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    status === "running"
                      ? "animate-pulse bg-foreground/70"
                      : status === "failed"
                        ? "bg-destructive"
                        : "bg-emerald-500",
                  )}
                />
                <span
                  className={cn(
                    "text-xs",
                    status === "running"
                      ? "animate-pulse text-foreground/75"
                      : status === "failed"
                        ? "text-destructive"
                        : "text-muted-foreground",
                  )}
                >
                  {item.title}
                </span>
              </div>
            </MessageContent>
          </Message>,
        );
        i++;
        continue;
      }

      rendered.push(
        <Message key={item.id} from="assistant" className="max-w-full">
          <MessageContent className="bg-transparent px-0 py-0 text-xs text-muted-foreground">
            <div>{item.title}{item.description ? ` ${item.description}` : ""}</div>
          </MessageContent>
        </Message>,
      );
      i++;
    }

    return rendered;
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
            {isSending && !timeline.some((item) => item.kind === "assistant" && item.assistantStreamId) ? (
              <Message from="assistant" className="max-w-full">
                <MessageContent className="bg-transparent px-0 py-0 text-xs text-muted-foreground">
                  <span className="animate-pulse">
                    Thinking... {activeThinkingSummary && activeThinkingSummary !== "Thinking..." ? activeThinkingSummary : ""}
                  </span>
                </MessageContent>
              </Message>
            ) : null}
          </ConversationContent>
          <ConversationScrollButton />
        </Conversation>

        <div className="shrink-0 pt-1">
          <PromptInput
            onSubmit={async (message) => {
              if (isSending) {
                onStopRun();
                return;
              }
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
                  aria-label="Stop"
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
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Chat History</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-1 py-2">
            {chatSessions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No previous chats yet.</p>
            ) : (
              chatSessions.map((session) => (
                <button
                  key={session.id}
                  type="button"
                  className="rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-muted"
                  onClick={() => {
                    void onLoadChatSession(session.id);
                    setIsHistoryOpen(false);
                  }}
                >
                  <div className="truncate">{session.title}</div>
                  <div className="text-xs text-muted-foreground">
                    {new Date(session.last_message_at).toLocaleDateString()}
                  </div>
                </button>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </aside>
  );
}
