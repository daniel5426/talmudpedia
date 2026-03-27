import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Clock, Plus, Square } from "lucide-react";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
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
import type { ArtifactCodingChatSession, ArtifactCodingModelOption } from "@/services/artifacts";

import { ArtifactCodingChatQuestionPanel } from "./ArtifactCodingChatQuestionPanel";
import { ArtifactCodingChatScrollBindings } from "./ArtifactCodingChatScrollBindings";
import { ArtifactCodingChatTimeline } from "./ArtifactCodingChatTimeline";
import {
  TimelineItem,
  isAssistantTimelineItem,
  isExplorationToolName,
  isToolTimelineItem,
  isUserTimelineItem,
} from "./chat-model";
import type { ArtifactCodingPendingQuestion } from "./stream-parsers";

type ArtifactCodingChatPanelProps = {
  isOpen: boolean;
  layoutMode?: "sidebar" | "playground";
  controlsDisabled?: boolean;
  isSending: boolean;
  isStopping: boolean;
  timeline: TimelineItem[];
  activeThinkingSummary: string;
  chatSessions: ArtifactCodingChatSession[];
  activeChatSessionId: string | null;
  onStartNewChat: () => void;
  onOpenHistory: () => void;
  onLoadChatSession: (sessionId: string) => Promise<void>;
  onSendMessage: (text: string) => Promise<void>;
  onStopRun: () => void;
  chatModels: ArtifactCodingModelOption[];
  selectedRunModelLabel: string;
  isModelSelectorOpen: boolean;
  onModelSelectorOpenChange: (next: boolean) => void;
  onSelectModelId: (modelId: string | null) => void;
  pendingQuestion: ArtifactCodingPendingQuestion | null;
  isAnsweringQuestion: boolean;
  runningSessionIds: string[];
  hasOlderHistory: boolean;
  isLoadingOlderHistory: boolean;
  onLoadOlderHistory: () => Promise<void>;
  onAnswerQuestion: (answers: string[][]) => Promise<void>;
  revertingRunId: string | null;
  onRevertToRun: (runId: string) => Promise<void>;
};

export function ArtifactCodingChatPanel({
  isOpen,
  layoutMode = "sidebar",
  controlsDisabled = false,
  isSending,
  isStopping,
  timeline,
  activeThinkingSummary,
  chatSessions,
  activeChatSessionId,
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
  pendingQuestion,
  isAnsweringQuestion,
  runningSessionIds,
  hasOlderHistory,
  isLoadingOlderHistory,
  onLoadOlderHistory,
  onAnswerQuestion,
  revertingRunId,
  onRevertToRun,
}: ArtifactCodingChatPanelProps) {
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const [scrollContainer, setScrollContainer] = useState<HTMLElement | null>(null);
  const topSentinelRef = useRef<HTMLDivElement>(null);
  const isLoadingOlderRef = useRef(false);
  const handleScrollContainerChange = useCallback((node: HTMLElement | null) => {
    setScrollContainer((current) => (current === node ? current : node));
  }, []);

  const hasRunningTool = useMemo(
    () => timeline.some((item) => isToolTimelineItem(item) && item.toolStatus === "running"),
    [timeline],
  );
  const lastUserIndex = useMemo(() => {
    for (let index = timeline.length - 1; index >= 0; index -= 1) {
      if (isUserTimelineItem(timeline[index])) return index;
    }
    return -1;
  }, [timeline]);
  const hasCurrentRunAssistantStream = useMemo(() => {
    if (lastUserIndex < 0) return false;
    for (let index = lastUserIndex + 1; index < timeline.length; index += 1) {
      const item = timeline[index];
      if (isAssistantTimelineItem(item) && item.assistantStreamId) return true;
    }
    return false;
  }, [lastUserIndex, timeline]);
  const lastToolAfterCurrentUser = useMemo(() => {
    if (lastUserIndex < 0) return null;
    for (let index = timeline.length - 1; index > lastUserIndex; index -= 1) {
      if (isToolTimelineItem(timeline[index])) return timeline[index];
    }
    return null;
  }, [lastUserIndex, timeline]);
  const lastToolAfterCurrentUserIsExploration = useMemo(
    () => Boolean(lastToolAfterCurrentUser && isExplorationToolName(String(lastToolAfterCurrentUser.toolName || ""))),
    [lastToolAfterCurrentUser],
  );
  const runningSessionIdSet = useMemo(() => new Set(runningSessionIds), [runningSessionIds]);
  const activeSessionIsRunning = useMemo(
    () => Boolean(activeChatSessionId && runningSessionIdSet.has(activeChatSessionId)),
    [activeChatSessionId, runningSessionIdSet],
  );

  useEffect(() => {
    const sentinel = topSentinelRef.current;
    const root = scrollContainer;
    if (!sentinel || !root || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        if (!hasOlderHistory || isLoadingOlderHistory || isLoadingOlderRef.current) return;
        const previousHeight = root.scrollHeight;
        const previousTop = root.scrollTop;
        isLoadingOlderRef.current = true;
        void onLoadOlderHistory().finally(() => {
          const nextHeight = root.scrollHeight;
          root.scrollTop = nextHeight - previousHeight + previousTop;
          isLoadingOlderRef.current = false;
        });
      },
      { root, threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasOlderHistory, isLoadingOlderHistory, onLoadOlderHistory, scrollContainer]);

  useEffect(() => {
    if (!scrollContainer) return;
    const handleScroll = () => setIsScrolled(scrollContainer.scrollTop > 5);
    scrollContainer.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => scrollContainer.removeEventListener("scroll", handleScroll);
  }, [scrollContainer]);

  if (!isOpen) {
    return null;
  }

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 shrink-0 flex-col overflow-hidden bg-background",
        layoutMode === "playground" ? "w-full" : "w-[430px]",
      )}
    >
      <div className="relative z-10 flex h-7 shrink-0 items-center gap-1 bg-background px-2 pt-2">
        <div
          className={cn(
            "pointer-events-none absolute inset-x-0 top-full z-10 h-8 bg-gradient-to-b from-background via-background/90 to-transparent transition-opacity duration-300",
            isScrolled ? "opacity-100" : "opacity-0",
          )}
          aria-hidden="true"
        />
        <div className="flex min-w-0 flex-1 items-center gap-2 px-1">
          {activeSessionIsRunning ? <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" /> : null}
        </div>
        <div className="flex mr-1 mb-2 border rounded-md items-center gap-1">
        <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-foreground" onClick={onStartNewChat} aria-label="Create new chat" disabled={controlsDisabled}>
          <Plus className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-muted-foreground hover:text-foreground"
          disabled={controlsDisabled}
          onClick={() => {
            onOpenHistory();
            setIsHistoryOpen(true);
          }}
          aria-label="Chat history"
        >
          <Clock className="h-3.5 w-3.5" />
        </Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col px-3 pb-2 pt-1">
        <Conversation className="flex min-h-0 flex-1 flex-col transition-all">
          <ArtifactCodingChatScrollBindings onScrollContainerChange={handleScrollContainerChange} />
          <ConversationContent className="gap-2 px-0 py-0 pb-30">
            <ArtifactCodingChatTimeline
              timeline={timeline}
              isSending={isSending}
              activeThinkingSummary={activeThinkingSummary}
              isLoadingOlderHistory={isLoadingOlderHistory}
              hasRunningTool={hasRunningTool}
              hasCurrentRunAssistantStream={hasCurrentRunAssistantStream}
              lastToolAfterCurrentUserIsExploration={lastToolAfterCurrentUserIsExploration}
              topSentinelRef={topSentinelRef}
              revertingRunId={revertingRunId}
              onRevertToRun={onRevertToRun}
            />
          </ConversationContent>
          <ConversationScrollButton />
        </Conversation>

        {pendingQuestion ? (
          <ArtifactCodingChatQuestionPanel
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
                placeholder="Ask the artifact agent to edit this artifact"
                className="min-h-15 max-h-40 bg-transparent px-3 pt-2.5 text-sm"
                disabled={controlsDisabled || isAnsweringQuestion}
              />
            </PromptInputBody>
            <PromptInputFooter className="justify-between px-2 pb-1.5 pt-0">
              <ModelSelector open={isModelSelectorOpen} onOpenChange={onModelSelectorOpenChange}>
                <ModelSelectorTrigger asChild>
                  <Button type="button" variant="ghost" size="sm" className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground" disabled={controlsDisabled}>
                    {selectedRunModelLabel}
                  </Button>
                </ModelSelectorTrigger>
                <ModelSelectorContent className="max-w-xs">
                  <ModelSelectorInput placeholder="Search models..." />
                  <ModelSelectorList>
                    <ModelSelectorEmpty>No models</ModelSelectorEmpty>
                    <ModelSelectorGroup heading="Run model">
                      {chatModels.map((model) => (
                        <ModelSelectorItem
                          key={model.id || "auto"}
                          value={`${model.label} ${model.id || "auto"}`}
                          onSelect={() => {
                            onSelectModelId(model.id);
                            onModelSelectorOpenChange(false);
                          }}
                        >
                          <ModelSelectorName>{model.label}</ModelSelectorName>
                        </ModelSelectorItem>
                      ))}
                    </ModelSelectorGroup>
                  </ModelSelectorList>
                </ModelSelectorContent>
              </ModelSelector>
              {isSending ? (
                <Button type="button" size="icon" variant="ghost" className="h-6 w-6 text-muted-foreground hover:text-foreground" onClick={onStopRun} aria-label={isStopping ? "Stopping" : "Stop"} disabled={controlsDisabled}>
                  <Square className="h-3 w-3 fill-current" />
                </Button>
              ) : (
                <PromptInputSubmit size="icon-sm" variant="ghost" className="h-6 w-6 text-muted-foreground hover:text-foreground" aria-label="Send" disabled={controlsDisabled || isAnsweringQuestion} />
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
                      <div className="flex items-center gap-2">
                        <div className="whitespace-normal text-sm leading-snug [overflow-wrap:anywhere]">{session.title}</div>
                        {runningSessionIdSet.has(session.id) ? <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" /> : null}
                      </div>
                      <div className="text-xs text-muted-foreground">{new Date(session.last_message_at).toLocaleDateString()}</div>
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
