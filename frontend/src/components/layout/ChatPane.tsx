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

import { CopyIcon, RefreshCcwIcon, ThumbsUpIcon, ThumbsDownIcon, Volume2, Square, SearchIcon, Mic, Loader2 } from "lucide-react";
import { DirectionMode, useDirection } from "@/components/direction-provider";
import { BotImputArea } from "@/components/BotImputArea";
import { useChatController, type ChatController, type ChatMessage, type Citation } from "./useChatController";
import { clearPendingChatMessage, consumePendingChatMessage } from "@/lib/chatPrefill";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { chatService, ttsService } from "@/services";
import { useRouter, useSearchParams } from "next/navigation";
import { KesherLogo } from "@/components/ui/KesherLogo";
import { useGeminiLive } from "@/hooks/useGeminiLive";
import { useAuthStore } from "@/lib/store/useAuthStore";
// import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
// import "@livekit/components-styles";
import { LibrarySearchModal } from "./LibrarySearchModal";
import { ChatPaneHeader } from "./ChatPaneHeader";
import { usePullToRefresh } from "@/hooks/use-pull-to-refresh";

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

const CITATION_NUMERIC_PATTERN = /((\d+)(?::(\d+))?|(\d+)([ab])(?::(\d+))?)$/i;
const CITATION_RANGE_PATTERN = /^(.*?)(?:[–—-]\s*\d.*)$/;

const normalizeCitationRef = (value?: string | null) => {
  if (!value) return "";
  let next = value.trim();
  try {
    next = decodeURIComponent(next);
  } catch {
    next = value.trim();
  }
  next = next.replace(/^https?:\/\/[^/]+/i, "");
  next = next.replace(/^\/+/, "");
  next = next.replace(/_/g, " ");
  return next.trim();
};

const extractCitationIndexTitle = (value: string) => {
  let normalized = normalizeCitationRef(value);
  const rangeMatch = normalized.match(CITATION_RANGE_PATTERN);
  if (rangeMatch && rangeMatch[1]) {
    normalized = rangeMatch[1].trim();
  }
  const numericMatch = normalized.match(CITATION_NUMERIC_PATTERN);
  if (numericMatch && typeof numericMatch.index === "number") {
    normalized = normalized.slice(0, numericMatch.index);
  }
  normalized = normalized.replace(/[,:]+$/, "").trim();
  if (normalized) return normalized;
  return normalizeCitationRef(value);
};

const extractBookLabel = (value: string) => {
  let base = value.replace(/[_/]+/g, " ").replace(/-/g, " ").trim();
  const commaParts = base.split(",").map((p) => p.trim()).filter(Boolean);
  if (commaParts.length > 1) {
    base = commaParts[commaParts.length - 1];
  }
  const tokens = base.split(" ").filter(Boolean);
  if (tokens.length > 3) {
    return tokens.slice(0, 3).join(" ");
  }
  return base;
};

const deriveCitationGroup = (citation: Citation) => {
  const primary = citation.url || citation.title || citation.ref || citation.sourceRef || "";
  const indexTitle = extractCitationIndexTitle(primary);
  const labelSource = extractBookLabel(indexTitle || primary || "מקור");
  const label = convertToHebrew(labelSource);
  const key = labelSource.toLowerCase();
  return { key, label };
};

const groupCitationsBySource = (citations?: Citation[]) => {
  const groups: Record<string, { label: string; items: Citation[] }> = {};
  (citations || []).forEach((citation) => {
    const { key, label } = deriveCitationGroup(citation);
    const bucket = groups[key] || { label, items: [] };
    bucket.items.push(citation);
    groups[key] = bucket;
  });
  return groups;
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
              const grouped = groupCitationsBySource(step.citations);
              return (
                <div className="mt-2 space-y-2">
                  {Object.entries(grouped).map(([groupKey, group]) => (
                    <InlineCitation key={groupKey} className="cursor-pointer">
                      <InlineCitationCard>
                        <InlineCitationCardTrigger
                          sources={Array(group.items.length).fill(group.label)}
                          className="cursor-pointer"
                          onClick={() => onSourceClick(group.items)}
                        />
                        <InlineCitationCardBody className="cursor-pointer max-h-96 overflow-y-auto">
                          {group.items.map((citation, cIdx) => (
                            <InlineCitationSource
                              key={cIdx}
                              sourceRef={citation.sourceRef}
                              firstRef={citation.firstRef}
                              totalSegments={citation.totalSegments}
                              rangeRef={citation.rangeRef}
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

export function ChatWorkspace({
  controller,
  chatId,
  isVoiceModeActive,
  handleToggleVoiceMode,
  analyser
}: {
  controller: ReturnType<typeof useChatController>;
  chatId?: string;
  isVoiceModeActive: boolean;
  handleToggleVoiceMode: () => void;
  analyser?: AnalyserNode | null;
}) {
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
    messages.length === 0 && !isLoading && streamingContent === "" && !isLoadingHistory && !isVoiceModeActive;

  const [playingId, setPlayingId] = useState<string | null>(null);
  const [loadingSpeakId, setLoadingSpeakId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stopPlayback = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      if (audioRef.current.src.startsWith("blob:")) {
        URL.revokeObjectURL(audioRef.current.src);
      }
      audioRef.current = null;
    }
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }
    setPlayingId(null);
    setLoadingSpeakId(null);
  }, []);

  const handleSpeak = useCallback(
    async (message: ChatMessage) => {
      if (!message.content) return;

      if (playingId === message.id) {
        stopPlayback();
        return;
      }

      stopPlayback();

      setLoadingSpeakId(message.id);
      try {
        const controller = new AbortController();
        abortRef.current = controller;
        const { url, cleanup } = await ttsService.stream(message.content, controller.signal);
        cleanupRef.current = cleanup;

        const audio = new Audio(url);
        audioRef.current = audio;
        setPlayingId(message.id);
        audio.onended = () => {
          stopPlayback();
        };
        audio.onerror = () => {
          stopPlayback();
        };
        await audio.play();
      } catch (error) {
        console.error(error);
        setPlayingId(null);
      } finally {
        setLoadingSpeakId(null);
      }
    },
    [playingId, stopPlayback]
  );

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        if (audioRef.current.src.startsWith("blob:")) {
          URL.revokeObjectURL(audioRef.current.src);
        }
      }
    };
  }, []);

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
        isEmptyState ? "px-4" : "px-4 pb-4 bg-transparent"
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
      <ConversationContent className={cn("flex-1 p-0 pt-13", isEmptyState && "h-full justify-center relative z-10")}>
        {isEmptyState ? (
          <div className="flex w-full flex-col items-center text-center pb-34 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <p className="text-3xl font-semibold pb-6">
            גלה מה מחפש לבך בתורה.</p>
            
                <BotImputArea 
                  textareaRef={controller.textareaRef}
                  handleSubmit={controller.handleSubmit}
                  isLoading={controller.isLoading}
                  isVoiceModeActive={isVoiceModeActive}
                  onToggleVoiceMode={handleToggleVoiceMode}
                  analyser={analyser}
                  animate={false}
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
                            const grouped = groupCitationsBySource(msg.citations);
                            return (
                              <div className="mt-1 space-y-2">
                                {Object.entries(grouped).map(([groupKey, group]) => (
                                  <InlineCitation key={groupKey}>
                                    <InlineCitationCard>
                                      <InlineCitationCardTrigger
                                        sources={Array(group.items.length).fill(group.label)}
                                        onClick={() => handleSourceClick(group.items)}
                                      />
                                      <InlineCitationCardBody className="max-h-96 overflow-y-auto">
                                        {group.items.map((citation, idx) => (
                                          <InlineCitationSource
                                            key={idx}
                                            sourceRef={citation.ref}
                                            firstRef={citation.firstRef}
                                            totalSegments={citation.totalSegments}
                                            rangeRef={citation.rangeRef}
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
                        <div dir={direction}>
                          {msg.isFinal === undefined && !msg.isVoice ? (
                            msg.content
                          ) : msg.isFinal || msg.isVoice ? (
                            <div className="flex items-center justify-end">
                              <div className="rounded-full bg-muted p-2">
                                <Mic className="size-4 text-muted-foreground" />
                              </div>
                            </div>
                          ) : null}
                        </div>
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
                          label={playingId === msg.id ? "Stop" : "Read"}
                          onClick={() => handleSpeak(msg)}
                          tooltip={
                            playingId === msg.id
                              ? "Stop playback"
                              : loadingSpeakId === msg.id
                              ? "Loading..."
                              : "Read aloud"
                          }
                          disabled={loadingSpeakId === msg.id || !msg.content}
                        >
                          {playingId === msg.id ? (
                            <Square className="size-4" />
                          ) : (
                            <Volume2 className="size-4" />
                          )}
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
                                  <span className="animate-pulse text-muted-foreground text-sm">
                                    חושב
                                  </span>
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
                                      <span className="animate-pulse text-muted-foreground text-sm">
                                        {formattedLabel}
                                      </span>
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
                isVoiceModeActive={isVoiceModeActive}
                onToggleVoiceMode={handleToggleVoiceMode}
                analyser={analyser}
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
  
  // Auto (Agent Router) - Get layout store for active chat management
  const setActiveChatId = useLayoutStore((state) => state.setActiveChatId);
  const [searchOpen, setSearchOpen] = React.useState(false);
  
  const router = useRouter();

  const handleRefresh = useCallback(() => {
    window.location.reload();
  }, []);

  const { pullDistance, isRefreshing, onTouchStart, onTouchMove, onTouchEnd } = usePullToRefresh({
    onRefresh: handleRefresh
  });

  const onChatCreated = React.useCallback((newChatId: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("chatId", newChatId);
      router.replace(`?${params.toString()}`);
  }, [router, searchParams]);

  // Auto (Agent Router) - Share chat handler - copies chat URL to clipboard
  const handleShareChat = React.useCallback(() => {
    if (!effectiveChatId) return;
    const url = chatService.getShareUrl(effectiveChatId);
    navigator.clipboard.writeText(url);
    alert("Link copied to clipboard!");
  }, [effectiveChatId]);

  // Auto (Agent Router) - Delete chat handler - confirms and deletes chat, then navigates
  const handleDeleteChat = React.useCallback(async () => {
    if (!effectiveChatId) return;
    if (!confirm("Are you sure you want to delete this chat?")) return;
    await chatService.delete(effectiveChatId);
    setActiveChatId(null);
    window.location.href = "/chat";
  }, [effectiveChatId, setActiveChatId]);

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || e.key === "/") {
        const target = e.target as HTMLElement | null;
        if (target && (target.isContentEditable || target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement)) {
          return;
        }
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const defaultController = useChatController();
  const chatController = controller ?? defaultController;
  
  const [isVoiceModeActive, setIsVoiceModeActive] = useState(false);
  
  const isEmptyState =
    chatController.messages.length === 0 && !chatController.isLoading && !chatController.streamingContent && !chatController.isLoadingHistory && !isVoiceModeActive;

  // Construct WebSocket URL
  const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const wsBackendUrl = backendUrl.replace(/^http/, 'ws');
  const token = useAuthStore((state) => state.token);
  // API path in backend/main.py is mounted at /api/voice/session (via include_router prefix=/api/voice)
  // Wait, in main.py: app.include_router(voice_ws.router, prefix="/api/voice", tags=["voice"])
  // And in voice_ws.py: @router.websocket("/session")
  // So the full path is /api/voice/session
  const voiceUrl = `${wsBackendUrl}/api/voice/session?chat_id=${effectiveChatId || ''}${token ? `&token=${encodeURIComponent(token)}` : ""}`;
  
  const { upsertLiveVoiceMessage } = chatController;

  const handleLiveText = React.useCallback(
    (msg: { role: "user" | "assistant"; content: string; is_final?: boolean }) => {
      upsertLiveVoiceMessage({
        role: msg.role,
        content: msg.content,
        isFinal: Boolean(msg.is_final),
      });
    },
    [upsertLiveVoiceMessage]
  );

  const handleLiveTool = React.useCallback(
    (msg: { tool: string; status?: string; query?: string; citations?: Citation[] }) => {
      if (msg.tool !== "retrieve_sources") {
        return;
      }
      const reasoningStep = {
        label: "Retrieval",
        status: msg.status === "pending" ? "pending" : "complete",
        icon: SearchIcon,
        query: msg.query,
        citations: msg.citations,
        sources: msg.citations,
      } as any;

      upsertLiveVoiceMessage({
        role: "assistant",
        content: "",
        citations: msg.citations,
        reasoningSteps: [reasoningStep],
      });
    },
    [upsertLiveVoiceMessage]
  );

  const { connect, disconnect, startRecording, isConnected, analyser, ensureAudioContext } = useGeminiLive(
    voiceUrl,
    onChatCreated,
    handleLiveText,
    handleLiveTool
  );

  useEffect(() => {
      if (isVoiceModeActive) {
          connect();
      } else {
          disconnect();
      }
  }, [isVoiceModeActive, connect, disconnect]);

  useEffect(() => {
      if (isConnected && isVoiceModeActive) {
          startRecording();
      }
  }, [isConnected, isVoiceModeActive, startRecording]);



  const handleToggleVoiceMode = async () => {
    if (isVoiceModeActive) {
      setIsVoiceModeActive(false);
      
      if (effectiveChatId) {
        await chatController.refresh();
      } else {
        await new Promise(resolve => setTimeout(resolve, 500));
        try {
            window.location.reload();
        } catch (error) {
          console.error("Failed to refresh:", error);
        }
      }
    } else {
        ensureAudioContext();
        setIsVoiceModeActive(true);
    }
  };

  const mainContent = (
    <ChatWorkspace
      controller={chatController}
      chatId={chatId}
      isVoiceModeActive={isVoiceModeActive}
      handleToggleVoiceMode={handleToggleVoiceMode}
      analyser={analyser}
    />
  );

  const roomContent = (
    <>
      <LibrarySearchModal open={searchOpen} onOpenChange={setSearchOpen} />
      <div className="relative h-full flex flex-col bg-background">
        <div 
          className="absolute top-0 left-0 right-0 h-10 flex items-center justify-center z-10 pointer-events-none"
          style={{ 
            opacity: pullDistance > 0 ? Math.min(pullDistance / 80, 1) : 0,
            transform: `translateY(${Math.min(pullDistance / 2, 40)}px)` 
          }}
        >
          {isRefreshing ? (
             <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          ) : (
             <RefreshCcwIcon 
               className="h-5 w-5 text-muted-foreground transition-transform duration-200" 
               style={{ transform: `rotate(${pullDistance * 3}deg)` }}
             />
          )}
        </div>
        <Conversation 
          className="relative flex min-h-full flex-col overflow-hidden bg-background transition-transform duration-200 ease-out"
          style={{ transform: `translateY(${pullDistance}px)` }}
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
        >
          <div
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute inset-0 transition-opacity duration-700 ease-in-out",
              isEmptyState ? "opacity-100" : "opacity-0"
            )}
            style={{ background: "linear-gradient(to bottom right,#cce4e6,#008E96)" }}
          />
          <ChatPaneHeader
            chatId={effectiveChatId}
            onSearchOpen={() => setSearchOpen(true)}
            onShareChat={handleShareChat}
            onDeleteChat={handleDeleteChat}
            isEmptyState={isEmptyState}
          />
          {mainContent}
        </Conversation>
      </div>
    </>
  );

  return roomContent;
}

