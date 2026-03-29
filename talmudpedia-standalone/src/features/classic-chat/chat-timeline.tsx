import {
  Check,
  Copy,
  RefreshCcw,
  Search,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useCallback, useMemo, useRef, type UIEvent } from "react";

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
  MessageAttachment,
  MessageAttachments,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Task } from "@/components/ai-elements/task";
import { UIBlocksBundleView, UIBlocksLoadingSkeleton } from "@/components/ui-blocks";
import { cn } from "@/lib/utils";

import { BotInputArea } from "./bot-input-area";
import { useLocale } from "./locale-context";
import { useStreamingMessageView } from "./use-streaming-message-view";
import type {
  ComposerSubmitPayload,
  TemplateMessage,
  TemplateReasoningBlock,
  TemplateRenderBlock,
  TemplateTaskBlock,
} from "./types";

type ChatTimelineProps = {
  copiedMessageId: string | null;
  dislikedMessageIds: Record<string, boolean>;
  errorMessage?: string | null;
  inputValue: string;
  isResponding: boolean;
  likedMessageIds: Record<string, boolean>;
  messages: TemplateMessage[];
  onCopyMessage: (messageId: string, text: string) => void;
  onInputValueChange: (value: string) => void;
  onLoadOlderMessages?: () => Promise<void> | void;
  onRetryMessage: (messageId: string) => void;
  onSubmit: (payload: ComposerSubmitPayload) => void | Promise<void>;
  onToggleDislike: (messageId: string) => void;
  onToggleLike: (messageId: string) => void;
  onTopVisibilityChange: (isAtTop: boolean) => void;
  hasOlderMessages?: boolean;
  isLoadingOlderMessages?: boolean;
};

function messageText(message: TemplateMessage) {
  if (message.text) return message.text;
  const firstTextBlock = message.blocks?.find((block) => block.kind === "text");
  return firstTextBlock?.kind === "text" ? firstTextBlock.content : "";
}

function renderAttachments(message: TemplateMessage) {
  if (!message.attachments?.length) {
    return null;
  }
  return (
    <MessageAttachments className="mb-1">
      {message.attachments.map((attachment) => {
        return (
          <MessageAttachment
            key={attachment.id}
            data={{
              filename: attachment.filename,
              mediaType: attachment.mimeType,
              type: "file",
              url: attachment.previewUrl || "",
            }}
            className={attachment.kind === "image" ? undefined : "w-56"}
          />
        );
      })}
    </MessageAttachments>
  );
}

function taskTone(status: TemplateTaskBlock["status"]) {
  if (status === "error") return "text-destructive";
  if (status === "running") return "text-foreground";
  return "text-muted-foreground";
}

function latestReasoningBlock(message: TemplateMessage): TemplateReasoningBlock | null {
  const blocks = message.blocks || [];
  for (let index = blocks.length - 1; index >= 0; index -= 1) {
    const block = blocks[index];
    if (block?.kind === "reasoning") {
      return block;
    }
  }
  return null;
}

function hasRunningTask(message: TemplateMessage): boolean {
  return (message.blocks || []).some(
    (block) => block.kind === "task" && block.status === "running",
  );
}

function renderBlock(block: TemplateRenderBlock) {
  if (block.kind === "text") {
    return <MessageResponse key={block.id}>{block.content}</MessageResponse>;
  }

  if (block.kind === "reasoning") {
    return null;
  }

  if (block.kind === "task") {
    return (
      <Task
        key={block.id}
        className="border-0 bg-transparent p-0 shadow-none"
        defaultOpen={false}
      >
        <div className={cn("text-[0.90rem]", taskTone(block.status))}>
          {block.status === "running" ? <Shimmer>{block.title}</Shimmer> : <span>{block.title}</span>}
        </div>
      </Task>
    );
  }

  if (block.kind === "ui_blocks_bundle") {
    return <UIBlocksBundleView key={block.id} bundle={block.bundle} />;
  }

  if (block.kind === "ui_blocks_loading") {
    return <UIBlocksLoadingSkeleton key={block.id} />;
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
              className="rounded-md p-3"
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
  errorMessage,
  inputValue,
  isResponding,
  likedMessageIds,
  messages,
  onCopyMessage,
  onInputValueChange,
  onLoadOlderMessages,
  onRetryMessage,
  onSubmit,
  onToggleDislike,
  onToggleLike,
  onTopVisibilityChange,
  hasOlderMessages = false,
  isLoadingOlderMessages = false,
}: ChatTimelineProps) {
  const { locale } = useLocale();
  const renderedMessages = useStreamingMessageView(messages);
  const hasMessages = renderedMessages.length > 0;
  const loadInFlightRef = useRef(false);

  const timelineMessages = useMemo(
    () =>
      renderedMessages.map((message) => ({
        ...message,
        plainText: messageText(message),
        latestReasoning: latestReasoningBlock(message),
        hasRunningTask: hasRunningTask(message),
      })),
    [renderedMessages]
  );

  const handleScrollCapture = useCallback((event: UIEvent<HTMLElement>) => {
    const target = event.target as HTMLElement;
    if (typeof target.scrollTop !== "number") {
      return;
    }
    const isAtTop = target.scrollTop < 12;
    onTopVisibilityChange(isAtTop);
    if (!isAtTop || !hasOlderMessages || isLoadingOlderMessages || !onLoadOlderMessages || loadInFlightRef.current) {
      return;
    }
    const previousScrollHeight = target.scrollHeight;
    const previousScrollTop = target.scrollTop;
    loadInFlightRef.current = true;
    Promise.resolve(onLoadOlderMessages())
      .then(() => {
        requestAnimationFrame(() => {
          target.scrollTop = Math.max(
            0,
            target.scrollHeight - previousScrollHeight + previousScrollTop,
          );
        });
      })
      .finally(() => {
        requestAnimationFrame(() => {
          loadInFlightRef.current = false;
        });
      });
  }, [hasOlderMessages, isLoadingOlderMessages, onLoadOlderMessages, onTopVisibilityChange]);

  return (
    <Conversation
      className="flex min-h-0 flex-1 flex-col overflow-hidden no-scrollbar"
      onScrollCapture={handleScrollCapture}
    >
      <ConversationContent
        className={cn(
          "flex w-full max-w-3xl mx-auto gap-6 pt-4 px-4",
          hasMessages ? "pb-36" : "justify-center"
        )}
      >
        <div className="h-px w-full shrink-0" />
        {isLoadingOlderMessages ? (
          <div className="w-full text-center text-xs text-muted-foreground">
            Loading older messages...
          </div>
        ) : null}

        {timelineMessages.map((message) => (
          <Message
            key={message.id}
            from={message.role}
            className="w-full max-w-3xl"
          >
            {message.role === "user" ? renderAttachments(message) : null}

            <MessageContent
              className={cn(
                "gap-3",
                message.role === "assistant" && "overflow-hidden"
              )}
            >
              {message.role === "user" ? (
                <>{message.plainText ? <MessageResponse>{message.plainText}</MessageResponse> : null}</>
              ) : (
                <>
                  {message.blocks?.map((block) => renderBlock(block))}
                  {message.runStatus && message.runStatus !== "completed" && !message.hasRunningTask && message.latestReasoning ? (
                    <div className="px-1 py-1 text-[0.90rem] text-muted-foreground">
                      <Shimmer>
                        {message.latestReasoning.steps[message.latestReasoning.steps.length - 1] ||
                          (locale === "he" ? "חושב..." : "Reasoning...")}
                      </Shimmer>
                    </div>
                  ) : null}
                  {message.runStatus && message.runStatus !== "completed" && !message.plainText && !(message.blocks?.length) ? (
                    <div className="px-1 py-1 text-[0.90rem] text-muted-foreground">
                      <Shimmer>{locale === "he" ? "חושב..." : "Thinking..."}</Shimmer>
                    </div>
                  ) : null}
                </>
              )}
            </MessageContent>

            {message.role === "assistant" && message.runStatus === "completed" && (
              <MessageActions className="mt-1.5 gap-1 ps-1">
                <MessageAction
                  label={locale === "he" ? "נסה שוב" : "Retry"}
                  onClick={() => onRetryMessage(message.id)}
                  tooltip={locale === "he" ? "נסה שוב" : "Retry"}
                >
                  <RefreshCcw className="size-3.5" />
                </MessageAction>
                <MessageAction
                  label={locale === "he" ? "אהבתי" : "Like"}
                  onClick={() => onToggleLike(message.id)}
                  tooltip={locale === "he" ? "אהבתי" : "Like"}
                >
                  <ThumbsUp
                    className="size-3.5"
                    fill={likedMessageIds[message.id] ? "currentColor" : "none"}
                  />
                </MessageAction>
                <MessageAction
                  label={locale === "he" ? "לא אהבתי" : "Dislike"}
                  onClick={() => onToggleDislike(message.id)}
                  tooltip={locale === "he" ? "לא אהבתי" : "Dislike"}
                >
                  <ThumbsDown
                    className="size-3.5"
                    fill={dislikedMessageIds[message.id] ? "currentColor" : "none"}
                  />
                </MessageAction>
                <MessageAction
                  label={locale === "he" ? "העתק" : "Copy"}
                  onClick={() => onCopyMessage(message.id, message.plainText)}
                  tooltip={
                    copiedMessageId === message.id
                      ? locale === "he"
                        ? "הועתק"
                        : "Copied"
                      : locale === "he"
                        ? "העתק"
                        : "Copy"
                  }
                >
                  {copiedMessageId === message.id ? (
                    <Check className="size-3.5 text-emerald-500" />
                  ) : (
                    <Copy className="size-3.5" />
                  )}
                </MessageAction>
                <MessageAction
                  label={locale === "he" ? "טרייס" : "Trace"}
                  tooltip={locale === "he" ? "טרייס" : "Trace"}
                >
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
              errorMessage={errorMessage}
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
