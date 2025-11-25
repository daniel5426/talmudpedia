"use client";

import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import type { FileUIPart } from "ai";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { convertToHebrew } from "@/lib/hebrewUtils";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store/useAuthStore";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
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
  PromptInput,
  PromptInputTextarea,
  PromptInputBody,
  PromptInputFooter,
  PromptInputTools,
  PromptInputActionMenu,
  PromptInputActionMenuTrigger,
  PromptInputActionMenuContent,
  PromptInputActionAddAttachments,
  PromptInputButton,
  PromptInputProvider,
  PromptInputAttachments,
  PromptInputAttachment as NewPromptInputAttachment,
  PromptInputSubmit,
  PromptInputSpeechButton,
} from "@/components/ai-elements/prompt-input";
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
import {
  CopyIcon,
  RefreshCcwIcon,
  ThumbsUpIcon,
  ThumbsDownIcon,
  GlobeIcon,
  SearchIcon,
  DotIcon,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { nanoid } from "nanoid";
import Image from "next/image";
import { DirectionMode, useDirection } from "@/components/direction-provider";
import { BotImputArea } from "@/components/BotImputArea";
import { KesherLoader } from "@/components/kesher-loader";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: Date;
  attachments?: FileUIPart[];
  citations?: Array<{ title: string; url: string; description: string }>;
  reasoningSteps?: Array<{
    label: string;
    status: "active" | "complete" | "pending";
    icon: LucideIcon;
    description?: string;
    citations?: Array<{ title: string; url: string; description: string }>;
  }>;
  thinkingDurationMs?: number;
}

const normalizeReasoningStatus = (
  status?: string
): "active" | "complete" | "pending" => {
  if (status === "active" || status === "pending" || status === "complete") {
    return status;
  }
  return "complete";
};
const getReasoningLabelKey = (label: ReactNode) => {
  if (typeof label === "string") return label;
  if (typeof label === "number") return label.toString();
  if (typeof label === "boolean") return label ? "true" : "false";
  return JSON.stringify(label);
};
const mergeReasoningSteps = (
  steps?: ChatMessage["reasoningSteps"],
  options?: { finalize?: boolean }
) => {
  const finalize = options?.finalize ?? false;
  if (!steps || steps.length === 0) {
    return [];
  }
  const merged: ChatMessage["reasoningSteps"] = [];
  const indexMap = new Map<string, number>();
  steps.forEach((step) => {
    const key = getReasoningLabelKey(step.label);
    if (indexMap.has(key)) {
      const idx = indexMap.get(key)!;
      const incomingStatus = normalizeReasoningStatus(step.status);
      merged[idx] = {
        ...merged[idx],
        ...step,
        description: step.description ?? merged[idx].description,
        citations:
          step.citations && step.citations.length > 0
            ? step.citations
            : merged[idx].citations,
        icon: step.icon ?? merged[idx].icon,
        status: finalize
          ? "complete"
          : incomingStatus || merged[idx].status || "complete",
      };
    } else {
      const normalizedStatus = finalize
        ? "complete"
        : normalizeReasoningStatus(step.status);
      const nextStep = { ...step, status: normalizedStatus };
      indexMap.set(key, merged.push(nextStep) - 1);
    }
  });
  return merged;
};

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
  if (typeof step.label === "string" && step.label === "Retrieval") {
    if (step.status === "complete") {
      const citationCount = step.citations?.length ?? 0;
      return `מצה ${citationCount} מקורות`;
    }
    return "מחפש מקורות";
  }
  if (typeof step.label === "string" && step.label === "Analysis") {
    return "מפענך את השאלה";
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
            {expanded && step.citations && step.citations.length > 0 && (
              <div className="mt-2">
                <InlineCitation className="cursor-pointer">
                  <InlineCitationCard>
                    <InlineCitationCardTrigger
                      sources={step.citations.map((citation) => citation.url)}
                      className="cursor-pointer"
                      onClick={() => onSourceClick(step.citations)}
                    />
                    <InlineCitationCardBody className="cursor-pointer max-h-96 overflow-y-auto">
                      {step.citations.map((citation, cIdx) => (
                        <InlineCitationSource
                          key={cIdx}
                          title={convertToHebrew(citation.title)}
                          sourceRef={citation.title}
                          url={citation.url}
                          description={citation.description}
                          className="p-4"
                        />
                      ))}
                    </InlineCitationCardBody>
                  </InlineCitationCard>
                </InlineCitation>
              </div>
            )}
          </ChainOfThoughtStep>
        );
      })}
    </>
  );
};

function ChatContent() {
  // Use selectors to prevent unnecessary re-renders
  const setSourceListOpen = useLayoutStore((state) => state.setSourceListOpen);
  const activeChatId = useLayoutStore((state) => state.activeChatId);
  const setActiveChatId = useLayoutStore((state) => state.setActiveChatId);
  const setSourceList = useLayoutStore((state) => state.setSourceList);
  
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [streamingContent, setStreamingContent] = useState("");
  const [currentReasoning, setCurrentReasoning] = useState<
    ChatMessage["reasoningSteps"]
  >([]);
  const { direction } = useDirection();
  const [liked, setLiked] = useState<Record<string, boolean>>({});
  const [disliked, setDisliked] = useState<Record<string, boolean>>({});
  const [lastThinkingDurationMs, setLastThinkingDurationMs] = useState<
    number | null
  >(null);
  const [containerWidth, setContainerWidth] = useState<number>(1000);
  

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const citationsRef = useRef<ChatMessage["citations"]>([]);
  const reasoningRef = useRef<ChatMessage["reasoningSteps"]>([]);
  const thinkingStartRef = useRef<number | null>(null);
  const thinkingDurationRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isInitializingChatRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { scrollToBottom } = useStickToBottomContext();

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

  // Load chat history when activeChatId changes
  useEffect(() => {
    let isCancelled = false;

    async function loadHistory() {
      // If we are initializing a new chat from a response, don't abort the current request
      if (isInitializingChatRef.current) {
        isInitializingChatRef.current = false;
        return;
      }

      if (!isCancelled) {
        setIsInitialLoading(true);
      }

      // Abort any ongoing request when switching chats
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }

      if (!activeChatId) {
        if (!isCancelled) {
          setMessages([]);
          setIsInitialLoading(false);
        }
        return;
      }

      try {
        const history = await api.getChatHistory(activeChatId);
        if (isCancelled) {
          return;
        }
        const formattedMessages: ChatMessage[] = history.messages.map((msg) => {
          const reasoningStepsRaw = msg.reasoning_steps
            ? msg.reasoning_steps.map((step: any) => {
                const baseCitations = Array.isArray(step.citations)
                  ? step.citations
                  : undefined;
                const fallbackCitations =
                  step.step === "Retrieval" &&
                  (!baseCitations || baseCitations.length === 0)
                    ? msg.citations
                    : baseCitations;
                return {
                  label: step.step,
                  status: normalizeReasoningStatus(step.status),
                  icon: step.step === "Retrieval" ? SearchIcon : DotIcon,
                  description: step.message,
                  citations: fallbackCitations,
                };
              })
            : [];
          const reasoningSteps =
            reasoningStepsRaw.length > 0
              ? mergeReasoningSteps(reasoningStepsRaw, { finalize: true })
              : [];
          return {
            id: nanoid(),
            role: msg.role,
            content: msg.content,
            createdAt: new Date(), // In a real app, use msg.created_at
            citations: msg.citations,
            reasoningSteps:
              reasoningSteps.length > 0 ? reasoningSteps : undefined,
            thinkingDurationMs: (msg as any).thinking_duration_ms ?? undefined,
          };
        });
        setMessages(formattedMessages);
      } catch (error) {
        if (!isCancelled) {
          console.error("Failed to load chat history", error);
        }
      } finally {
        if (!isCancelled) {
          setIsInitialLoading(false);
        }
      }
    }
    loadHistory();

    return () => {
      isCancelled = true;
    };
  }, [activeChatId]);

  const handleSourceClick = (citations: ChatMessage["citations"]) => {
    if (!citations) return;
    const sources = citations.map((c) => ({
      id: nanoid(),
      score: 1,
      metadata: {
        index_title: c.title,
        ref: c.title,
        text: c.description,
        version_title: "Sefaria",
      },
    }));
    setSourceList(sources);
    setSourceListOpen(true);
  };

  const handleSubmit = async (message: {
    text: string;
    files: FileUIPart[];
  }) => {
    console.log("handleSubmit called", message);
    if (!message.text.trim() && message.files.length === 0) return;

    const userMessage: ChatMessage = {
      id: nanoid(),
      role: "user",
      content: message.text,
      createdAt: new Date(),
      attachments: message.files,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    setStreamingContent("");
    setCurrentReasoning([]);
    setLastThinkingDurationMs(null);

    citationsRef.current = [];
    reasoningRef.current = [];
    thinkingStartRef.current = Date.now();
    thinkingDurationRef.current = null;

    (async () => {
      try {
        if (abortControllerRef.current) {
          abortControllerRef.current.abort();
        }

        const abortController = new AbortController();
        abortControllerRef.current = abortController;

        console.log("sending fetch");
        const token = useAuthStore.getState().token;
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }
        const response = await fetch("/api/py/chat", {
          method: "POST",
          headers,
          body: JSON.stringify({
            message: message.text,
            chatId: activeChatId,
          }),
          signal: abortController.signal,
        });
        console.log("fetch done", response.status);

        if (!response.ok) throw new Error("Chat request failed");

        const newChatId = response.headers.get("X-Chat-ID");
        if (newChatId && newChatId !== activeChatId) {
          isInitializingChatRef.current = true;
          setActiveChatId(newChatId);
        }

        const reader = response.body?.getReader();
        if (!reader) return;

        let aiContent = "";
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (abortController.signal.aborted) {
            reader.cancel();
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const event = JSON.parse(line);

              if (event.type === "token") {
                if (!thinkingDurationRef.current && thinkingStartRef.current) {
                  const duration = Date.now() - thinkingStartRef.current;
                  thinkingDurationRef.current = duration;
                  setLastThinkingDurationMs(duration);
                }
                aiContent += event.content;
                setStreamingContent(aiContent);
              } else if (event.type === "citation") {
                const newCitation = event.data;
                citationsRef.current = [
                  ...(citationsRef.current || []),
                  newCitation,
                ];
              } else if (event.type === "reasoning") {
                console.log("[REASONING EVENT]", event.data);
                const stepData = event.data;
                const step = {
                  label: stepData.step,
                  status: stepData.status,
                  icon: stepData.step === "Retrieval" ? SearchIcon : DotIcon,
                  description: stepData.message,
                  citations: stepData.citations,
                };

                setCurrentReasoning((prev) => {
                  const existing = prev || [];
                  const index = existing.findIndex(
                    (s) => s.label === step.label
                  );
                  let newSteps;
                  if (index !== -1) {
                    newSteps = [...existing];
                    newSteps[index] = { ...newSteps[index], ...step };
                  } else {
                    newSteps = [...existing, step];
                  }
                  const merged = mergeReasoningSteps(newSteps);
                  reasoningRef.current = merged;
                  console.log("[REASONING STEPS UPDATED]", merged);
                  return merged;
                });
              }
            } catch (e) {
              console.error("Error parsing JSON stream line:", line, e);
            }
          }
        }

        const aiMessage: ChatMessage = {
          id: nanoid(),
          role: "assistant",
          content: aiContent,
          createdAt: new Date(),
          citations: citationsRef.current,
          reasoningSteps: (() => {
            const merged = mergeReasoningSteps(reasoningRef.current, {
              finalize: true,
            });
            return merged.length > 0 ? merged : undefined;
          })(),
          thinkingDurationMs: thinkingDurationRef.current ?? undefined,
        };

        setMessages((prev) => [...prev, aiMessage]);
        setStreamingContent("");
        setCurrentReasoning([]);
      } catch (error: any) {
        if (error.name === "AbortError") {
          console.log("Request aborted");
          return;
        }
        console.error("Chat error:", error);
      } finally {
        if (!abortControllerRef.current?.signal.aborted) {
          setIsLoading(false);
          abortControllerRef.current = null;
        }
      }
    })();
  };

  const handleCopy = (content: string) => {
    navigator.clipboard.writeText(content);
  };

  const handleRetry = () => {
    console.log("Retrying...");
  };
  console.log("layoutSize", containerWidth);
  return (
    <>
    {isInitialLoading && (
      <div className="flex flex-col pb-40 items-center justify-center h-full max-w-3xl mx-auto w-full bg-background p-6">
        <KesherLoader size={78} />
      </div>
    )}
    {messages.length === 0 && !isInitialLoading && (
    <div className="flex flex-col pb-40 items-center justify-center h-full max-w-3xl mx-auto w-full bg-background p-6 ">
      <div className="">
        <ConversationEmptyState
          className="pb-5"
          icon={
            <Image
              src="/kesher.png"
              alt="Kesher"
              width={78}
              height={78}
              className="h-22 w-22 text-muted-foreground/50"
            />
          }
          title="ברוך הבה לקשר"
          description="המקום שבו אפשר לחפש ולעיין בכל התורה כולה במשפט אחד"
        />
      </div>
      <BotImputArea textareaRef={textareaRef} handleSubmit={handleSubmit} />
      </div>
    )}
    <div
      ref={containerRef}
      className={`flex flex-col h-full max-w-3xl mx-auto w-full bg-background p-6 pb-4`}
      dir={direction}
    >
      <ConversationContent>
        
          {messages.length > 0 && messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex w-full`}
            >
                  {msg.role === "assistant" && containerWidth >= 550 && (
                    <div className={cn("shrink-0", direction === "rtl" ? "ml-2" : "mr-4")}>
                      <Image
                        src="/kesher.png"
                        alt="Kesher"
                        width={40}
                        height={40}
                        className="h-6 w-6 rounded-md object-cover hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
                        priority
                      />
                    </div>
                  )}
                  <Message
                    from={msg.role}
                    className="max-w-3xl"
                    dir={direction}
                  >
                    {msg.role === "user" &&
                      msg.attachments &&
                      msg.attachments.length > 0 && (
                        <MessageAttachments className="mb-2">
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
                          {msg.reasoningSteps &&
                            msg.reasoningSteps.length > 0 && (
                              <div className="space-y-2">
                                <ChainOfThought
                                  dir={direction}
                                  className={direction === "rtl" ? "text-right" : "text-left"}
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

                          <div className="" dir={direction}>
                            <MessageResponse>{msg.content}</MessageResponse>
                          </div>

                          {/* Citations */}
                          {msg.citations && msg.citations.length > 0 && (
                            <div className="mt-1">
                              <InlineCitation>
                                <InlineCitationCard>
                                  <InlineCitationCardTrigger
                                    sources={msg.citations.map((c) => c.url)}
                                    onClick={() => handleSourceClick(msg.citations)}
                                  />
                                  <InlineCitationCardBody className="max-h-96 overflow-y-auto">
                                    {msg.citations.map((citation, idx) => (
                                      <InlineCitationSource
                                        key={idx}
                                        title={convertToHebrew(citation.title)}
                                        sourceRef={citation.title}
                                        url={citation.url}
                                        description={citation.description}
                                        className="p-4"
                                      />
                                    ))}
                                  </InlineCitationCardBody>
                                </InlineCitationCard>
                              </InlineCitation>
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="" dir={direction}>
                          {msg.content}
                        </div>
                      )}
                    </MessageContent>

                    {msg.role === "assistant" && (
                      <MessageActions>
                        <MessageAction
                          label="Retry"
                          onClick={handleRetry}
                          tooltip="Regenerate response"
                        >
                          <RefreshCcwIcon className="size-4" />
                        </MessageAction>
                        <MessageAction
                          label="Like"
                          onClick={() =>
                            setLiked((prev) => ({
                              ...prev,
                              [msg.id]: !prev[msg.id],
                            }))
                          }
                          tooltip="Like this response"
                        >
                          <ThumbsUpIcon
                            className="size-4"
                            fill={liked[msg.id] ? "currentColor" : "none"}
                          />
                        </MessageAction>
                        <MessageAction
                          label="Dislike"
                          onClick={() =>
                            setDisliked((prev) => ({
                              ...prev,
                              [msg.id]: !prev[msg.id],
                            }))
                          }
                          tooltip="Dislike this response"
                        >
                          <ThumbsDownIcon
                            className="size-4"
                            fill={disliked[msg.id] ? "currentColor" : "none"}
                          />
                        </MessageAction>
                        <MessageAction
                          label="Copy"
                          onClick={() => handleCopy(msg.content || "")}
                          tooltip="Copy to clipboard"
                        >
                          <CopyIcon className="size-4" />
                        </MessageAction>
                      </MessageActions>
                    )}
                  </Message>
            </div>
          ))
        }
        {isLoading && (
          <div className="flex w-full" dir={direction}>
            {containerWidth >= 550 && (
              <div className={cn("shrink-0", direction === "rtl" ? "ml-4" : "mr-4")}>
                <Image
                  src="/kesher.png"
                  alt="Kesher"
                  width={40}
                  height={40}
                  className="h-6 w-6 rounded-md object-cover hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
                  priority
                />
              </div>
            )}
            <Message from="assistant" className="max-w-3xl" dir={direction}>
              <MessageContent>
                {/* Streaming Reasoning */}
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
                              currentReasoning[
                                currentReasoning.length - 1
                              ];
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
                          key={`streaming-${activeChatId || "new"}`}
                          steps={currentReasoning}
                          cacheKey={`streaming-${activeChatId || "new"}`}
                          onSourceClick={handleSourceClick}
                          direction={direction}
                        />
                      </ChainOfThoughtContent>
                    </ChainOfThought>
                  </div>
                )}

                <div className="" dir={direction}>
                  <MessageResponse>{streamingContent}</MessageResponse>
                </div>
              </MessageContent>
            </Message>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </ConversationContent>

      {/* Scroll to Bottom Button - uses Conversation's built-in context */}
      <ConversationScrollButton />

      {/* Fixed Input Area */}
        <BotImputArea className="w-full max-w-3xl px-4 mx-auto" textareaRef={textareaRef} handleSubmit={handleSubmit} />

    </div>
    </>
  );
}

export function ChatPane() {
  return (
    <Conversation>
      <ChatContent />
    </Conversation>
  );
}
