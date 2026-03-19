import {
  Check,
  Copy,
  FileAudio,
  FileImage,
  FileText,
  RefreshCcw,
  Search,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useMemo } from "react";

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
} from "@/components/ai-elements/task";
import { cn } from "@/lib/utils";

import { BotInputArea } from "./bot-input-area";
import { useLocale } from "./locale-context";
import { AssistantWidgetBlock } from "./widget-block";
import type {
  ComposerSubmitPayload,
  TemplateAttachment,
  TemplateMessage,
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
  onRetryMessage: (messageId: string) => void;
  onSubmit: (payload: ComposerSubmitPayload) => void | Promise<void>;
  onToggleDislike: (messageId: string) => void;
  onToggleLike: (messageId: string) => void;
  onTopVisibilityChange: (isAtTop: boolean) => void;
};

function messageText(message: TemplateMessage) {
  if (message.text) return message.text;
  const firstTextBlock = message.blocks?.find((block) => block.kind === "text");
  return firstTextBlock?.kind === "text" ? firstTextBlock.content : "";
}

function attachmentIcon(attachment: TemplateAttachment) {
  if (attachment.kind === "audio") return FileAudio;
  if (attachment.kind === "image") return FileImage;
  return FileText;
}

function renderAttachments(message: TemplateMessage) {
  if (!message.attachments?.length) {
    return null;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {message.attachments.map((attachment) => {
        const Icon = attachmentIcon(attachment);
        return (
          <div
            key={attachment.id}
            className="flex max-w-full items-center gap-2 rounded-md border border-border/60 bg-background/70 px-2.5 py-2 text-xs"
          >
            {attachment.kind === "image" && attachment.previewUrl ? (
              <img
                alt={attachment.filename}
                className="h-10 w-10 rounded object-cover"
                src={attachment.previewUrl}
              />
            ) : (
              <Icon className="size-4 shrink-0 text-muted-foreground" />
            )}
            <span className="truncate">{attachment.filename}</span>
          </div>
        );
      })}
    </div>
  );
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

  if (block.kind === "widget") {
    return <AssistantWidgetBlock key={block.id} block={block} />;
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
  errorMessage,
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
  const { locale } = useLocale();
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
                <>
                  {message.plainText ? <MessageResponse>{message.plainText}</MessageResponse> : null}
                  {renderAttachments(message)}
                </>
              ) : (
                <>
                  {message.blocks?.map((block) => renderBlock(block))}
                  {message.runStatus && message.runStatus !== "completed" && !message.plainText ? (
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
