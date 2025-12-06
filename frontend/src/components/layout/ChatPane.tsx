"use client";

import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { nanoid } from "nanoid";
import { convertToHebrew } from "@/lib/hebrewUtils";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
  useStickToBottomContext,
} from "@/components/ai-elements/conversation";
import { cn } from "@/lib/utils";
import {
  Message,
  MessageContent,
  MessageResponse,
  MessageActions,
  MessageAction,
  MessageAttachments,
  MessageAttachment,
} from "@/components/ai-elements/message";
import {
  InlineCitation,
  InlineCitationCard,
  InlineCitationCardTrigger,
  InlineCitationCardBody,
  InlineCitationSource,
} from "@/components/ai-elements/inline-citation";
import {
  ChainOfThought,
  ChainOfThoughtHeader,
  ChainOfThoughtContent,
  ChainOfThoughtStep,
} from "@/components/ai-elements/chain-of-thought";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { CopyIcon, RefreshCcwIcon, ThumbsUpIcon, ThumbsDownIcon, Share2, Trash2, MoreHorizontal } from "lucide-react";
import { DirectionMode, useDirection } from "@/components/direction-provider";
import { BotImputArea } from "@/components/BotImputArea";
import { useChatController, type ChatController, type ChatMessage } from "./useChatController";
import { clearPendingChatMessage, consumePendingChatMessage } from "@/lib/chatPrefill";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSearchParams } from "next/navigation";
import { KesherLogo } from "@/components/ui/KesherLogo";

const formatThinkingDuration = (durationMs?: number | null) => {
  if (!durationMs || durationMs <= 0) {
    return null;
  }
  const seconds = durationMs / 1000;
  if (seconds < 60) {
    const value =
      seconds < 10 ? seconds.toFixed(1) : Math.round(seconds).toString();
    const normalized = value.endsWith(".0") ? value.slice(0, -2) : value;
    return `${normalized} שניות`;
  }
  const minutes = Math.floor(seconds / 60);
  const minuteUnit = minutes === 1 ? "דקה" : "דקות";
  const remainingSeconds = Math.round(seconds % 60);
  if (remainingSeconds === 0) {
    return `${minutes} ${minuteUnit}`;
  }
  return `${minutes} ${minuteUnit} ${remainingSeconds} שניות`;
};

const buildThinkingLabel = (durationMs?: number | null) => {
  const formatted = formatThinkingDuration(durationMs);
  return formatted ? `חשב במשך ${formatted}` : null;
};

type ReasoningStepsListProps = {
  steps?: ChatMessage["reasoningSteps"];
  cacheKey: string;
  onSourceClick: (citations: ChatMessage["citations"]) => void;
  direction: DirectionMode;
};

type ReasoningStep = NonNullable<ChatMessage["reasoningSteps"]>[number];

const formatReasoningStepLabel = (step?: ReasoningStep): ReactNode => {
  if (!step) {
    return null;
  }

  if (typeof step.label === "string" && step.label.toLowerCase().includes("retrieval")) {
    const stepData = step as any;
    if (stepData.query !== undefined) {
      if (step.status === "pending") {
        return `מחפש "${stepData.query}"`;
      }
      if (step.status === "complete" && stepData.sources) {
        return `מצא ${stepData.sources.length} מקורות`;
      }
    }
    if (step.status === "complete") {
      const citationCount = step.citations?.length ?? 0;
      return `מצא ${citationCount} מקורות`;
    }
    return "מחפש מקורות";
  }

  if (typeof step.label === "string" && step.label === "Analysis") {
    return "מפענח את השאלה";
  }

  return step.label;
};

const ReasoningStepsList = ({
  steps = [],
  cacheKey,
  onSourceClick,
  direction,
}: ReasoningStepsListProps) => {
  const [overrides, setOverrides] = useState<Record<number, boolean>>({});
  const latestIndex = steps.length - 1;

  const toggleStep = useCallback(
    (index: number) => {
      setOverrides((prev) => {
        const current = prev[index] ?? index === latestIndex;
        const nextValue = !current;
        const defaultValue = index === latestIndex;
        if (nextValue === defaultValue) {
          if (prev[index] === undefined) {
            return prev;
          }
          const rest = { ...prev };
          delete rest[index];
          return rest;
        }
        return {
          ...prev,
          [index]: nextValue,
        };
      });
    },
    [latestIndex]
  );

  if (!steps.length) {
    return null;
  }

  return (
    <>
      {steps.map((step, idx) => {
        const expanded = overrides[idx] ?? idx === latestIndex;
        const stepData = step as any;
        const isRetrievalStep =
          typeof step.label === "string" &&
          step.label.toLowerCase().includes("retrieval");

        return (
          <ChainOfThoughtStep
            key={`${cacheKey}-${idx}`}
            icon={step.icon}
            label={formatReasoningStepLabel(step)}
            status={step.status}
            description={expanded ? step.description : undefined}
            isCollapsible
            isExpanded={expanded}
            onToggle={() => toggleStep(idx)}
            dir={direction}
          >
            {expanded &&
              isRetrievalStep &&
              step.status === "complete" &&
              stepData.query && (
                <div className="mt-2 text-sm text-muted-foreground">
                  <span>שאילתה: {stepData.query}</span>
                </div>
              )}
            {expanded && step.citations && step.citations.length > 0 && (() => {
              const citationsByUrl = step.citations.reduce((acc, citation) => {
                const url = citation.url;
                if (!acc[url]) {
                  acc[url] = [];
                }
                acc[url].push(citation);
                return acc;
              }, {} as Record<string, typeof step.citations>);

              return (
                <div className="mt-2 space-y-2">
                  {Object.entries(citationsByUrl).map(([url, citations]) => (
                    <InlineCitation key={url} className="cursor-pointer">
                      <InlineCitationCard>
                        <InlineCitationCardTrigger
                          sources={citations.map((citation) => convertToHebrew(citation.url))}
                          className="cursor-pointer"
                          onClick={() => onSourceClick(citations)}
                        />
                        <InlineCitationCardBody className="cursor-pointer max-h-96 overflow-y-auto">
                          {citations.map((citation, cIdx) => (
                            <InlineCitationSource
                              key={cIdx}
                              sourceRef={citation.sourceRef}
                              title={convertToHebrew(citation.title)}
                              description={citation.description}
                              className="p-4"
                            />
                          ))}
                        </InlineCitationCardBody>
                      </InlineCitationCard>
                    </InlineCitation>
                  ))}
                </div>
              );
            })()}
          </ChainOfThoughtStep>
        );
      })}
    </>
  );
};

type ChatPaneProps = {
  controller?: ChatController;
  chatId?: string;
};

function ChatWorkspace({ controller, chatId }: { controller: ChatController; chatId?: string }) {
  // Auto (Agent Router) - Extract controller methods and state
  const {
    messages,
    streamingContent,
    currentReasoning,
    isLoading,
    isLoadingHistory,
    liked,
    disliked,
    copiedMessageId,
    lastThinkingDurationMs,
    handleSubmit,
    handleStop,
    handleCopy,
    handleLike,
    handleDislike,
    handleRetry,
    handleSourceClick,
    textareaRef,
  } = controller;
  // Auto (Agent Router) - Get direction for RTL/LTR layout
  const { direction } = useDirection();
  // Auto (Agent Router) - Refs for container and scroll management
  const containerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // Auto (Agent Router) - Container width state for responsive layout
  const [containerWidth, setContainerWidth] = useState<number>(1000);
  // Auto (Agent Router) - Scroll to bottom context for auto-scrolling
  const { scrollToBottom } = useStickToBottomContext();
  // Auto (Agent Router) - Determine if chat is in empty state
  const isEmptyState =
    messages.length === 0 && !isLoading && streamingContent === "" && !isLoadingHistory;

  // Auto (Agent Router) - Refs for managing pending prefill and chat ID tracking
  const pendingPrefillHandledRef = useRef(false);
  const setActiveChatId = useLayoutStore((state) => state.setActiveChatId);
  const prevPropChatIdRef = useRef<string | undefined>(undefined);
  
  // Auto (Agent Router) - Get chatId from URL if not provided as prop (for useEffect tracking)
  const searchParams = useSearchParams();
  const urlChatId = searchParams.get('chatId');
  const effectiveChatId = chatId || urlChatId;

  // Auto (Agent Router) - Auto-scroll to bottom when content changes
  useEffect(() => {
    if (messages.length > 0 || streamingContent || isLoading) {
      const timeoutId = setTimeout(() => {
        scrollToBottom();
      }, 100);
      return () => clearTimeout(timeoutId);
    }
  }, [messages, streamingContent, currentReasoning, isLoading, scrollToBottom]);

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

  // Auto (Agent Router) - Sync chatId with layout store when it changes
  useEffect(() => {
    if (effectiveChatId) {
      setActiveChatId(effectiveChatId);
    } else if (prevPropChatIdRef.current) {
      setActiveChatId(null);
    }
    prevPropChatIdRef.current = effectiveChatId || undefined;
  }, [effectiveChatId, setActiveChatId]);

  useEffect(() => {
    if (pendingPrefillHandledRef.current) return;
    if (messages.length > 0 || isLoading || streamingContent) {
      pendingPrefillHandledRef.current = true;
      return;
    }
    const pending = consumePendingChatMessage();
    if (!pending) return;
    pendingPrefillHandledRef.current = true;
    handleSubmit(pending);
  }, [handleSubmit, isLoading, messages.length, streamingContent]);

  useEffect(() => {
    if (!pendingPrefillHandledRef.current) return;
    if (messages.length === 0 && streamingContent === "" && !isLoading) {
      return;
    }
    clearPendingChatMessage();
  }, [messages.length, streamingContent, isLoading]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "flex flex-col h-full max-w-3xl mx-auto w-full",
        isEmptyState ? "px-4" : "px-4 pt-4 pb-4 bg-transparent"
      )}
      dir={direction}
    >
      {isEmptyState && containerWidth >= 650 && (
        <div
          dir="ltr"
          className="absolute inset-0 pointer-events-none overflow-visible z-0"
        >
          <KesherLogo
            variant="background"
            className="-translate-x-[40%] -translate-y-[20%] top-1/4"
          />
          <KesherLogo
            variant="background"
            className="translate-x-[40%] translate-y-[50%] right-0"
          />
          <KesherLogo
            variant="accent"
            className="-translate-x-[10%] translate-y-[10%] right-0"
          />
        </div>
      )}
      <ConversationContent className={cn("flex-1 p-0", isEmptyState && "h-full justify-center relative z-10")}>
        {isEmptyState ? (
          <div className="flex w-full flex-col items-center text-center pb-20">
            <p className="text-3xl font-semibold pb-6">
            גלה מה מחפש לבך בתורה.</p>
            <BotImputArea
              className="w-full max-w-3xl"
              textareaRef={textareaRef}
              handleSubmit={handleSubmit}
              isLoading={isLoading}
              onStop={handleStop}
            />
          </div>
        ) : (
          <>
            {messages.length > 0 &&
              messages.map((msg) => (
                <div key={msg.id} className="flex w-full">
                  {msg.role === "assistant" && containerWidth >= 550 && (
                    <div
                      className={cn(
                        "shrink-0",
                        direction === "rtl" ? "ml-2" : "mr-2"
                      )}
                    >
                      <KesherLogo variant="avatar" />
                    </div>
                  )}
                  <Message from={msg.role} className="max-w-3xl" dir={direction}>
                    {msg.role === "user" &&
                      msg.attachments &&
                      msg.attachments.length > 0 && (
                        <MessageAttachments dir={direction} className="mb-2">
                          {msg.attachments.map((attachment) => (
                            <MessageAttachment
                              data={attachment}
                              key={attachment.url || nanoid()}
                            />
                          ))}
                        </MessageAttachments>
                      )}

                    <MessageContent dir={direction}>
                      {msg.role === "assistant" ? (
                        <>
                          {msg.reasoningSteps && msg.reasoningSteps.length > 0 && (
                            <div className="space-y-2">
                              <ChainOfThought
                                dir={direction}
                                className={
                                  direction === "rtl" ? "text-right" : "text-left"
                                }
                                defaultOpen={false}
                              >
                                <ChainOfThoughtHeader
                                  dir={direction}
                                  renderLabel={() => {
                                    const thinkingLabel = buildThinkingLabel(
                                      msg.thinkingDurationMs
                                    );
                                    if (thinkingLabel) {
                                      return thinkingLabel;
                                    }
                                    const latestStep =
                                      msg.reasoningSteps?.[
                                        msg.reasoningSteps.length - 1
                                      ];
                                    const latestLabel =
                                      formatReasoningStepLabel(latestStep);
                                    return latestLabel ?? "חושב...";
                                  }}
                                />
                                <ChainOfThoughtContent dir={direction}>
                                  <ReasoningStepsList
                                    key={`reasoning-${msg.id}`}
                                    steps={msg.reasoningSteps}
                                    cacheKey={msg.id}
                                    onSourceClick={handleSourceClick}
                                    direction={direction}
                                  />
                                </ChainOfThoughtContent>
                              </ChainOfThought>
                            </div>
                          )}

                          <div dir={direction}>
                            <MessageResponse>{msg.content}</MessageResponse>
                          </div>

                          {msg.citations && msg.citations.length > 0 && (() => {
                            const citationsByUrl = msg.citations.reduce((acc, citation) => {
                              const url = citation.url;
                              if (!acc[url]) {
                                acc[url] = [];
                              }
                              acc[url].push(citation);
                              console.log("citation.ref", citation.ref);
                              return acc;
                            }, {} as Record<string, typeof msg.citations>);

                            return (
                              <div className="mt-1 space-y-2">
                                {Object.entries(citationsByUrl).map(([url, citations]) => (
                                  <InlineCitation key={url}>
                                    <InlineCitationCard>
                                      <InlineCitationCardTrigger
                                        sources={citations.map((c) => convertToHebrew(c.url))}
                                        onClick={() => handleSourceClick(citations)}
                                      />
                                      <InlineCitationCardBody className="max-h-96 overflow-y-auto">
                                        {citations.map((citation, idx) => (
                                          <InlineCitationSource
                                            key={idx}
                                            sourceRef={citation.ref}
                                            title={convertToHebrew(citation.title)}
                                            description={citation.description}
                                            className="p-4"
                                          />
                                        ))}
                                      </InlineCitationCardBody>
                                    </InlineCitationCard>
                                  </InlineCitation>
                                ))}
                              </div>
                            );
                          })()}
                        </>
                      ) : (
                        <div dir={direction}>{msg.content}</div>
                      )}
                    </MessageContent>

                    {msg.role === "assistant" && (
                      <MessageActions>
                        <MessageAction
                          label="Retry"
                          onClick={() => handleRetry(msg)}
                          tooltip="Regenerate response"
                        >
                          <RefreshCcwIcon className="size-4" />
                        </MessageAction>
                        <MessageAction
                          label="Like"
                          onClick={() => handleLike(msg)}
                          tooltip="Like this response"
                        >
                          <ThumbsUpIcon
                            className="size-4"
                            fill={liked[msg.id] ? "currentColor" : "none"}
                          />
                        </MessageAction>
                        <MessageAction
                          label="Dislike"
                          onClick={() => handleDislike(msg)}
                          tooltip="Dislike this response"
                        >
                          <ThumbsDownIcon
                            className="size-4"
                            fill={disliked[msg.id] ? "currentColor" : "none"}
                          />
                        </MessageAction>
                        <MessageAction
                          label="Copy"
                          onClick={() => handleCopy(msg.content || "", msg.id)}
                          tooltip={
                            copiedMessageId === msg.id ? "Copied!" : "Copy to clipboard"
                          }
                        >
                          <CopyIcon
                            className={cn(
                              "size-4 transition-all",
                              copiedMessageId === msg.id && "scale-125 text-green-500"
                            )}
                          />
                        </MessageAction>
                      </MessageActions>
                    )}
                  </Message>
                </div>
              ))}

            {isLoading && (
              <div className="flex w-full" dir={direction}>
                {containerWidth >= 550 && (
                  <div
                    className={cn(
                      "shrink-0",
                      direction === "rtl" ? "ml-2" : "mr-2"
                    )}
                  >
                    <KesherLogo variant="avatar" />
                  </div>
                )}
                <Message from="assistant" className="max-w-3xl" dir={direction}>
                  <MessageContent>
                    {currentReasoning && currentReasoning.length > 0 && (
                      <div className="mb-1 space-y-4">
                        <ChainOfThought defaultOpen={false} dir={direction}>
                          <ChainOfThoughtHeader
                            renderLabel={({ isOpen }) => {
                              if (isOpen) {
                                return (
                                  <Shimmer as="span" className="text-sm">
                                    חושב
                                  </Shimmer>
                                );
                              }
                              const thinkingLabel = buildThinkingLabel(
                                lastThinkingDurationMs
                              );
                              if (thinkingLabel) {
                                return thinkingLabel;
                              }
                              if (currentReasoning.length > 0) {
                                const latestStep =
                                  currentReasoning[currentReasoning.length - 1];
                                const formattedLabel =
                                  formatReasoningStepLabel(latestStep);
                                if (formattedLabel) {
                                  if (typeof formattedLabel === "string") {
                                    return (
                                      <Shimmer as="span" className="text-sm">
                                        {formattedLabel}
                                      </Shimmer>
                                    );
                                  }
                                  return formattedLabel;
                                }
                              }
                              return "חושב...";
                            }}
                          />
                          <ChainOfThoughtContent>
                            <ReasoningStepsList
                              key="streaming"
                              steps={currentReasoning}
                              cacheKey="streaming"
                              onSourceClick={handleSourceClick}
                              direction={direction}
                            />
                          </ChainOfThoughtContent>
                        </ChainOfThought>
                      </div>
                    )}

                    <div dir={direction}>
                      <MessageResponse>{streamingContent}</MessageResponse>
                    </div>
                  </MessageContent>
                </Message>
              </div>
            )}

            <div ref={messagesEndRef} />
          </>
        )}
      </ConversationContent>

      {!isEmptyState && (
        <>
          <ConversationScrollButton />
          <BotImputArea
            textareaRef={textareaRef}
            handleSubmit={handleSubmit}
            isLoading={isLoading}
            onStop={handleStop}
          />
        </>
      )}
    </div>
  );
}

export function ChatPane({ controller, chatId }: ChatPaneProps) {
  // Auto (Agent Router) - Get chatId from URL search params if not provided as prop
  const searchParams = useSearchParams();
  const effectiveChatId = chatId || searchParams.get('chatId');
  
  // Auto (Agent Router) - Get direction for button positioning
  const { direction } = useDirection();
  const isRTL = direction === "rtl";
  
  // Auto (Agent Router) - Get layout store for active chat management
  const setActiveChatId = useLayoutStore((state) => state.setActiveChatId);
  
  // Auto (Agent Router) - Share chat handler - copies chat URL to clipboard
  const handleShareChat = React.useCallback(() => {
    if (!effectiveChatId) return;
    const params = new URLSearchParams({ chatId: effectiveChatId });
    const url = `${window.location.origin}/chat?${params.toString()}`;
    navigator.clipboard.writeText(url);
    alert("Link copied to clipboard!");
  }, [effectiveChatId]);

  // Auto (Agent Router) - Delete chat handler - confirms and deletes chat, then navigates
  const handleDeleteChat = React.useCallback(async () => {
    if (!effectiveChatId) return;
    if (!confirm("Are you sure you want to delete this chat?")) return;
    await api.deleteChat(effectiveChatId);
    setActiveChatId(null);
    window.location.href = "/chat";
  }, [effectiveChatId, setActiveChatId]);

  const defaultController = useChatController();
  const chatController = controller ?? defaultController;
  const isEmptyState =
    chatController.messages.length === 0 && !chatController.isLoading && !chatController.streamingContent && !chatController.isLoadingHistory;
  return (
    <Conversation className="relative overflow-hidden bg-background">
      {/* Auto (Agent Router) - Background gradient overlay */}
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute inset-0 transition-opacity duration-700 ease-in-out",
          isEmptyState ? "opacity-100" : "opacity-0"
        )}
        style={{ background: "linear-gradient(to bottom right,#cce4e6,#008E96)" }}
      />
      {/* Auto (Agent Router) - Full-width button container positioned absolutely at top, outside scroll area */}
      {effectiveChatId && (
        <div
          className={cn(
            "absolute top-4 z-20 flex items-center gap-2 w-full px-4 pointer-events-none",
            isRTL ? "justify-start" : "justify-end"
          )}
        >
          <div className="pointer-events-auto">
            {/* Auto (Agent Router) - 3-dot dropdown menu with Share and Delete options */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="flex items-center gap-2 hover:bg-sidebar-accent"
                >
                  <MoreHorizontal className="h-4 w-4" />
                  <span className="sr-only">More options</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-48"
                side="bottom"
                align="end"
              >
                <DropdownMenuItem
                  onClick={handleShareChat}
                  className="cursor-pointer"
                >
                  <Share2 className="mr-2 h-4 w-4" />
                  <span>שתף</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={handleDeleteChat}
                  className="cursor-pointer text-red-600 focus:text-red-600"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  <span>מחק</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      )}
      <ChatWorkspace controller={chatController} chatId={chatId} />
    </Conversation>
  );
}

