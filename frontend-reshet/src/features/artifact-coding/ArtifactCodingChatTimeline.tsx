import { useState, type ReactNode, type RefObject } from "react";
import { Check, Copy, RotateCcw } from "lucide-react";

import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Task, TaskContent, TaskItem, TaskItemFile, TaskTrigger } from "@/components/ai-elements/task";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import {
  TimelineItem,
  formatToolPathLabel,
  formatToolReadPath,
  isAssistantTimelineItem,
  isEditToolName,
  isExplorationToolName,
  isOrchestratorTimelineItem,
  isReadToolName,
  isSearchToolName,
  isToolTimelineItem,
  isUserTimelineItem,
} from "./chat-model";

type ArtifactCodingChatTimelineProps = {
  timeline: TimelineItem[];
  isSending: boolean;
  activeThinkingSummary: string;
  isLoadingOlderHistory: boolean;
  hasRunningTool: boolean;
  hasCurrentRunAssistantStream: boolean;
  lastToolAfterCurrentUserIsExploration: boolean;
  topSentinelRef: RefObject<HTMLDivElement | null>;
  revertingRunId: string | null;
  onRevertToRun: (runId: string) => Promise<void>;
};

export function ArtifactCodingChatTimeline(props: ArtifactCodingChatTimelineProps) {
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const {
  timeline,
  isSending,
  activeThinkingSummary,
  isLoadingOlderHistory,
  hasRunningTool,
  hasCurrentRunAssistantStream,
  lastToolAfterCurrentUserIsExploration,
  topSentinelRef,
  revertingRunId,
  onRevertToRun,
  } = props;
  const renderedItems: ReactNode[] = [];
  let index = 0;

  while (index < timeline.length) {
    const item = timeline[index];
    if (isUserTimelineItem(item)) {
      renderedItems.push(
        <Message key={item.id} from="user" className="group/usermsg max-w-full">
          <MessageContent className="relative">
            <MessageResponse>{item.description || "Request submitted."}</MessageResponse>
            {item.userDeliveryStatus && item.userDeliveryStatus !== "sent" ? (
              <div className="mt-1 text-[9px] text-muted-foreground">
                {item.userDeliveryStatus === "pending" ? "Sending..." : "Failed"}
              </div>
            ) : null}
          </MessageContent>
          {item.userDeliveryStatus === "sent" && item.runId ? (
            <div className=" flex justify-end">
              <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover/usermsg:opacity-100">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5 rounded-sm text-muted-foreground/75 hover:text-foreground"
                  onClick={async () => {
                    await navigator.clipboard.writeText(item.description || "");
                    setCopiedMessageId(item.id);
                    window.setTimeout(() => {
                      setCopiedMessageId((current) => (current === item.id ? null : current));
                    }, 1200);
                  }}
                  aria-label="Copy message"
                >
                  {copiedMessageId === item.id ? <Check className="!size-3" /> : <Copy className="!size-3" />}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5 rounded-sm text-muted-foreground/75 hover:text-foreground"
                  onClick={() => void onRevertToRun(item.runId!)}
                  disabled={revertingRunId === item.runId}
                  aria-label="Revert to this message"
                >
                  <RotateCcw className={cn(" !size-3", revertingRunId === item.runId ? "animate-spin" : "")} />
                </Button>
              </div>
            </div>
          ) : null}
        </Message>,
      );
      index += 1;
      continue;
    }

    if (isAssistantTimelineItem(item)) {
      renderedItems.push(
        <Message key={item.id} from="assistant" className="max-w-full">
          <MessageContent className="bg-transparent px-0 py-0">
            <MessageResponse>{item.description}</MessageResponse>
          </MessageContent>
        </Message>,
      );
      index += 1;
      continue;
    }

    if (isOrchestratorTimelineItem(item)) {
      renderedItems.push(
        <Message key={item.id} from="assistant" className="max-w-full">
          <MessageContent className="bg-transparent px-0 py-0">
            <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Orchestrator
            </div>
            <MessageResponse>{item.description}</MessageResponse>
          </MessageContent>
        </Message>,
      );
      index += 1;
      continue;
    }

    if (isToolTimelineItem(item)) {
      if (isExplorationToolName(String(item.toolName || ""))) {
        const streak: TimelineItem[] = [];
        while (index < timeline.length) {
          const candidate = timeline[index];
          if (!isToolTimelineItem(candidate) || !isExplorationToolName(String(candidate.toolName || ""))) {
            break;
          }
          streak.push(candidate);
          index += 1;
        }
        const readCount = streak.filter((entry) => isReadToolName(String(entry.toolName || ""))).length;
        const searchCount = streak.filter((entry) => isSearchToolName(String(entry.toolName || ""))).length;
        const hasRunningExplore = streak.some((entry) => (entry.toolStatus || "completed") === "running");
        const headerParts: string[] = [];
        if (readCount > 0) headerParts.push(`${readCount} ${readCount === 1 ? "file" : "files"}`);
        if (searchCount > 0) headerParts.push(`${searchCount} ${searchCount === 1 ? "search" : "searches"}`);
        const headerText = `Exploring ${headerParts.join(", ") || "artifact draft"}`;
        renderedItems.push(
          <Message key={`explore-group-${streak[0].id}`} from="assistant" className="max-w-full">
            <MessageContent className="bg-transparent px-0 py-0 text-sm">
              <Task defaultOpen={false} className="w-full">
                <TaskTrigger asChild title={headerText}>
                  <button
                    type="button"
                    className="group flex w-full items-center justify-between gap-2 rounded-md px-0 py-0.5 text-left text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {hasRunningExplore ? <Shimmer className="text-sm">{headerText}</Shimmer> : <span>{headerText}</span>}
                  </button>
                </TaskTrigger>
                <TaskContent className="mt-1">
                  {streak.map((entry) => {
                    const toolStatus = entry.toolStatus || "completed";
                    const isRead = isReadToolName(String(entry.toolName || ""));
                    const readPath = isRead ? formatToolReadPath(String(entry.toolPath || "")) : "";
                    const rowTitle = isRead
                      ? (readPath ? `Reading file ${readPath}` : "Reading file")
                      : (entry.toolDetail ? `Searching code ${entry.toolDetail}` : "Searching code");
                    return (
                      <TaskItem
                        key={entry.id}
                        className={cn("flex items-center gap-2 text-sm", toolStatus === "failed" ? "text-destructive" : "text-muted-foreground")}
                      >
                        {toolStatus === "running" ? <Shimmer className="text-sm">{rowTitle}</Shimmer> : <span>{rowTitle}</span>}
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
      const status = item.toolStatus || "completed";
      renderedItems.push(
        <Message key={item.id} from="assistant" className="max-w-full">
          <MessageContent className="bg-transparent px-0 py-0 text-sm">
            <Task defaultOpen className="w-full">
              <TaskItem className={cn("flex items-center gap-2 text-sm", status === "failed" ? "text-destructive" : "text-muted-foreground")}>
                {status === "running" ? (
                  <Shimmer className="text-sm">{item.title}</Shimmer>
                ) : (
                  <>
                    <span>{item.title}</span>
                    {item.toolPath && !isEditToolName(String(item.toolName || "")) ? <TaskItemFile>{formatToolPathLabel(String(item.toolPath || ""))}</TaskItemFile> : null}
                    {item.toolDetail ? <TaskItemFile>{item.toolDetail}</TaskItemFile> : null}
                  </>
                )}
              </TaskItem>
            </Task>
          </MessageContent>
        </Message>,
      );
      index += 1;
      continue;
    }

    index += 1;
  }

  return (
    <>
      <div ref={topSentinelRef} className="h-1 w-full shrink-0" />
      {isLoadingOlderHistory ? <div className="py-1 text-center text-[11px] text-muted-foreground">Loading older messages...</div> : null}
      {renderedItems}
      {isSending && !hasRunningTool && !hasCurrentRunAssistantStream && !lastToolAfterCurrentUserIsExploration ? (
        <Message from="assistant" className="max-w-full">
          <MessageContent className="bg-transparent px-0 py-0 text-sm text-muted-foreground">
            <Shimmer className="text-sm">
              {`Reasoning...${activeThinkingSummary && activeThinkingSummary !== "Thinking..." ? ` ${activeThinkingSummary}` : ""}`}
            </Shimmer>
          </MessageContent>
        </Message>
      ) : null}
    </>
  );
}
