import type { RefObject } from "react";

import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Task, TaskContent, TaskItem, TaskItemFile, TaskTrigger } from "@/components/ai-elements/task";
import { cn } from "@/lib/utils";

import {
  TimelineItem,
  formatToolPathLabel,
  formatToolReadPath,
  isAssistantTimelineItem,
  isEditToolName,
  isExplorationToolName,
  isReadToolName,
  isSearchToolName,
  isToolTimelineItem,
  isUserTimelineItem,
} from "./chat-model";

type AppsBuilderChatTimelineProps = {
  timeline: TimelineItem[];
  isSending: boolean;
  activeThinkingSummary: string;
  isLoadingOlderHistory: boolean;
  hasRunningTool: boolean;
  hasCurrentRunAssistantStream: boolean;
  lastToolAfterCurrentUserIsExploration: boolean;
  topSentinelRef: RefObject<HTMLDivElement | null>;
};

export function AppsBuilderChatTimeline({
  timeline,
  isSending,
  activeThinkingSummary,
  isLoadingOlderHistory,
  hasRunningTool,
  hasCurrentRunAssistantStream,
  lastToolAfterCurrentUserIsExploration,
  topSentinelRef,
}: AppsBuilderChatTimelineProps) {
  const renderUserDeliveryLabel = (status?: TimelineItem["userDeliveryStatus"]) => {
    if (!status || status === "sent") return null;
    if (status === "pending") return "Sending...";
    return "Failed";
  };

  const renderStandardToolRow = (item: TimelineItem) => {
    const status = item.toolStatus || "completed";
    const showPathBadge = item.toolPath && !isEditToolName(String(item.toolName || ""));
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
                  {showPathBadge ? <TaskItemFile>{formatToolPathLabel(String(item.toolPath || ""))}</TaskItemFile> : null}
                  {item.toolDetail ? <TaskItemFile>{item.toolDetail}</TaskItemFile> : null}
                </Shimmer>
              ) : (
                <>
                  <span>{item.title}</span>
                  {showPathBadge ? <TaskItemFile>{formatToolPathLabel(String(item.toolPath || ""))}</TaskItemFile> : null}
                  {item.toolDetail ? <TaskItemFile>{item.toolDetail}</TaskItemFile> : null}
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
      if (item.userDeliveryStatus === "queued") {
        index += 1;
        continue;
      }
      renderedItems.push(
        <Message key={item.id} from="user" className="group/usermsg max-w-full">
          <MessageContent className="relative">
            <MessageResponse>{item.description || "Request submitted."}</MessageResponse>
            {renderUserDeliveryLabel(item.userDeliveryStatus) ? (
              <div className="mt-1 text-[9px] text-muted-foreground">
                {renderUserDeliveryLabel(item.userDeliveryStatus)}
              </div>
            ) : null}
          </MessageContent>
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

    if (isToolTimelineItem(item)) {
      if (isExplorationToolName(String(item.toolName || ""))) {
        const explorationStreak: TimelineItem[] = [];
        while (index < timeline.length) {
          const candidate = timeline[index];
          if (!isToolTimelineItem(candidate) || !isExplorationToolName(String(candidate.toolName || ""))) {
            break;
          }
          explorationStreak.push(candidate);
          index += 1;
        }

        const readItems = explorationStreak.filter((entry) => isReadToolName(String(entry.toolName || "")));
        const searchItems = explorationStreak.filter((entry) => isSearchToolName(String(entry.toolName || "")));
        const readCount = readItems.length;
        const searchCount = searchItems.length;
        const hasRunningExplore = explorationStreak.some((entry) => (entry.toolStatus || "completed") === "running");
        const headerParts: string[] = [];
        if (readCount > 0) {
          headerParts.push(`${readCount} ${readCount === 1 ? "file" : "files"}`);
        }
        if (searchCount > 0) {
          headerParts.push(`${searchCount} ${searchCount === 1 ? "search" : "searches"}`);
        }
        const headerText = `Exploring ${headerParts.join(", ") || "workspace"}`;

        renderedItems.push(
          <Message key={`explore-group-${explorationStreak[0].id}`} from="assistant" className="max-w-full">
            <MessageContent className="bg-transparent px-0 py-0 text-sm">
              <Task defaultOpen={false} className="w-full">
                <TaskTrigger asChild title={headerText}>
                  <button
                    type="button"
                    className="group flex w-full items-center justify-between gap-2 rounded-md px-0 py-0.5 text-left text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {hasRunningExplore ? (
                      <Shimmer className="text-sm">{headerText}</Shimmer>
                    ) : (
                      <span className="text-sm">{headerText}</span>
                    )}
                  </button>
                </TaskTrigger>
                <TaskContent className="mt-1">
                  {explorationStreak.map((entry) => {
                    const toolStatus = entry.toolStatus || "completed";
                    const isRead = isReadToolName(String(entry.toolName || ""));
                    const readPath = isRead ? formatToolReadPath(String(entry.toolPath || "")) : "";
                    const searchDetail = String(entry.toolDetail || "").trim();
                    const searchPath = String(entry.toolPath || "").trim();
                    const rowTitle = isRead
                      ? (readPath ? `Reading file ${readPath}` : "Reading file")
                      : (searchDetail
                        ? `Searching code ${searchDetail}`
                        : searchPath
                          ? `Searching code ${formatToolPathLabel(searchPath)}`
                          : "Searching code");
                    return (
                      <TaskItem
                        key={entry.id}
                        className={cn("flex items-center gap-2 text-sm", toolStatus === "failed" ? "text-destructive" : "text-muted-foreground")}
                      >
                        {toolStatus === "running" ? (
                          <Shimmer className="text-sm">{rowTitle}</Shimmer>
                        ) : (
                          <span>{rowTitle}</span>
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
      </Message>,
    );
    index += 1;
  }

  return (
    <>
      <div ref={topSentinelRef} className="h-1 w-full shrink-0" />
      {isLoadingOlderHistory ? (
        <div className="py-1 text-center text-[11px] text-muted-foreground">Loading older messages...</div>
      ) : null}
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
