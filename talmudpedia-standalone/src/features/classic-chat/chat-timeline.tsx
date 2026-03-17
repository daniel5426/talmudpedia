import {
  Check,
  Copy,
  RefreshCcw,
  Search,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useMemo } from "react";

import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtHeader,
  ChainOfThoughtStep,
} from "@/components/ai-elements/chain-of-thought";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  InlineCitation,
  InlineCitationCard,
  InlineCitationCardBody,
  InlineCitationCardTrigger,
  InlineCitationSource,
} from "@/components/ai-elements/inline-citation";
import {
  Message,
  MessageAction,
  MessageActions,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import { Shimmer } from "@/components/ai-elements/shimmer";
import {
  Task,
  TaskContent,
  TaskItem,
  TaskItemFile,
  TaskTrigger,
} from "@/components/ai-elements/task";
import { cn } from "@/lib/utils";

import { BotInputArea } from "./bot-input-area";
import type {
  TemplateMessage,
  TemplateRenderBlock,
  TemplateTaskBlock,
} from "./types";

type ChatTimelineProps = {
  copiedMessageId: string | null;
  dislikedMessageIds: Record<string, boolean>;
  inputValue: string;
  isResponding: boolean;
  likedMessageIds: Record<string, boolean>;
  messages: TemplateMessage[];
  onCopyMessage: (messageId: string, text: string) => void;
  onInputValueChange: (value: string) => void;
  onRetryMessage: (messageId: string) => void;
  onSubmit: (text: string) => void;
  onToggleDislike: (messageId: string) => void;
  onToggleLike: (messageId: string) => void;
  onTopVisibilityChange: (isAtTop: boolean) => void;
};

function messageText(message: TemplateMessage) {
  if (message.text) return message.text;
  const firstTextBlock = message.blocks?.find((block) => block.kind === "text");
  return firstTextBlock?.kind === "text" ? firstTextBlock.content : "";
}

function taskTone(status: TemplateTaskBlock["status"]) {
  if (status === "error") return "text-destructive";
  if (status === "running") return "text-foreground";
  return "text-muted-foreground";
}

function renderBlock(block: TemplateRenderBlock) {
  if (block.kind === "text") {
    return <MessageResponse key={block.id}>{block.content}</MessageResponse>;
  }

  if (block.kind === "reasoning") {
    return (
      <ChainOfThought
        key={block.id}
        className="rounded-xl border border-border/40 bg-muted/30 px-4 py-3"
        defaultOpen={false}
      >
        <ChainOfThoughtHeader>{block.title}</ChainOfThoughtHeader>
        <ChainOfThoughtContent>
          {block.steps.map((step) => (
            <ChainOfThoughtStep
              key={`${block.id}-${step}`}
              label={step}
              status="complete"
            />
          ))}
        </ChainOfThoughtContent>
      </ChainOfThought>
    );
  }

  if (block.kind === "task") {
    return (
      <Task
        key={block.id}
        className="rounded-xl border border-border/40 bg-muted/30 px-4 py-3"
        defaultOpen={block.status === "running"}
      >
        <TaskTrigger title={block.title}>
          <div className={cn("flex items-center gap-2 text-sm", taskTone(block.status))}>
            {block.status === "running" ? (
              <Shimmer>{block.title}</Shimmer>
            ) : (
              <span>{block.title}</span>
            )}
          </div>
        </TaskTrigger>
        <TaskContent>
          {block.items.map((item) => (
            <TaskItem key={`${block.id}-${item}`}>{item}</TaskItem>
          ))}
          {block.files?.map((file) => (
            <TaskItemFile key={`${block.id}-${file}`}>{file}</TaskItemFile>
          ))}
        </TaskContent>
      </Task>
    );
  }

  return (
    <InlineCitation key={block.id}>
      <InlineCitationCard>
        <InlineCitationCardTrigger
          sources={block.sources.map((source) => `https://${source.label.replace(/\s+/g, "-").toLowerCase()}.local`)}
        />
        <InlineCitationCardBody className="space-y-2 p-2">
          {block.sources.map((source) => (
            <InlineCitationSource
              key={source.id}
              className="rounded-xl p-3"
              description={block.title}
              title={source.label}
              url={source.href}
            />
          ))}
        </InlineCitationCardBody>
      </InlineCitationCard>
    </InlineCitation>
  );
}

export function ChatTimeline({
  copiedMessageId,
  dislikedMessageIds,
  inputValue,
  isResponding,
  likedMessageIds,
  messages,
  onCopyMessage,
  onInputValueChange,
  onRetryMessage,
  onSubmit,
  onToggleDislike,
  onToggleLike,
  onTopVisibilityChange,
}: ChatTimelineProps) {
  const hasMessages = messages.length > 0;

  const timelineMessages = useMemo(
    () =>
      messages.map((message) => ({
        ...message,
        plainText: messageText(message),
      })),
    [messages]
  );

  return (
    <Conversation
      className="flex min-h-0 flex-1 flex-col overflow-hidden"
      onScrollCapture={(event) => {
        const target = event.target as HTMLElement;
        if (typeof target.scrollTop === "number") {
          onTopVisibilityChange(target.scrollTop < 12);
        }
      }}
    >
      <ConversationContent
        className={cn(
          "flex w-full max-w-3xl mx-auto gap-6 pt-4 px-4",
          hasMessages ? "pb-36" : "justify-center"
        )}
      >
        <div className="h-px w-full shrink-0" />

        {timelineMessages.map((message) => (
          <Message
            key={message.id}
            from={message.role}
            className="w-full max-w-3xl"
          >
            <MessageContent
              className={cn(
                "gap-3",
                message.role === "assistant" && "overflow-hidden"
              )}
            >
              {message.role === "user" ? (
                <MessageResponse>{message.plainText}</MessageResponse>
              ) : (
                message.blocks?.map((block) => renderBlock(block))
              )}
            </MessageContent>

            {message.role === "assistant" && (
              <MessageActions className="mt-1.5 gap-1 ps-1">
                <MessageAction
                  label="Retry"
                  onClick={() => onRetryMessage(message.id)}
                  tooltip="Retry"
                >
                  <RefreshCcw className="size-3.5" />
                </MessageAction>
                <MessageAction
                  label="Like"
                  onClick={() => onToggleLike(message.id)}
                  tooltip="Like"
                >
                  <ThumbsUp
                    className="size-3.5"
                    fill={likedMessageIds[message.id] ? "currentColor" : "none"}
                  />
                </MessageAction>
                <MessageAction
                  label="Dislike"
                  onClick={() => onToggleDislike(message.id)}
                  tooltip="Dislike"
                >
                  <ThumbsDown
                    className="size-3.5"
                    fill={dislikedMessageIds[message.id] ? "currentColor" : "none"}
                  />
                </MessageAction>
                <MessageAction
                  label="Copy"
                  onClick={() => onCopyMessage(message.id, message.plainText)}
                  tooltip={copiedMessageId === message.id ? "Copied" : "Copy"}
                >
                  {copiedMessageId === message.id ? (
                    <Check className="size-3.5 text-emerald-500" />
                  ) : (
                    <Copy className="size-3.5" />
                  )}
                </MessageAction>
                <MessageAction label="Trace" tooltip="Trace">
                  <Search className="size-3.5" />
                </MessageAction>
              </MessageActions>
            )}
          </Message>
        ))}
      </ConversationContent>

      {hasMessages && <ConversationScrollButton className="bottom-32 bg-background" />}

      {/* Sticky input area at the bottom */}
      <div className="pointer-events-none sticky bottom-0 z-20 w-full px-4 pb-4">
        <div className="pointer-events-none mx-auto w-full max-w-3xl">
          <div className="pointer-events-none w-full bg-gradient-to-t from-background via-background/95 to-transparent px-2" />
          <div className="pointer-events-auto">
            <BotInputArea
              compact
              inputValue={inputValue}
              isLoading={isResponding}
              onInputValueChange={onInputValueChange}
              onSubmit={onSubmit}
            />
          </div>
        </div>
      </div>
    </Conversation>
  );
}
