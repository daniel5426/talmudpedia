"use client";

import { Fragment, useMemo } from "react";
import {
  formatToolPathLabel,
  formatToolReadPath,
  isEditToolName,
  isExplorationToolName,
  isReadToolName,
  isSearchToolName,
} from "@/features/apps-builder/workspace/chat/chat-model";
import type {
  ChatApprovalRequestBlock,
  ChatRenderBlock,
  ChatToolCallBlock,
} from "@/services/chat-presentation";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { MessageResponse } from "./message";
import { Shimmer } from "./shimmer";
import { Task, TaskContent, TaskItem, TaskItemFile, TaskTrigger } from "./task";

type AssistantResponseTimelineProps = {
  blocks: ChatRenderBlock[];
  onApprovalAction?: (decision: "approve" | "reject") => void;
  isLoading?: boolean;
};

function renderToolRow(block: ChatToolCallBlock) {
  const status = block.status;
  const showPathBadge = block.tool.path && !isEditToolName(String(block.tool.toolName || ""));
  const label = block.tool.title || block.tool.displayName || block.tool.summary || block.tool.toolName;

  return (
    <Task defaultOpen key={block.id} className="w-full">
      <TaskItem
        className={cn(
          "flex items-center gap-2 text-sm",
          status === "error" ? "text-destructive" : "text-muted-foreground",
        )}
      >
        {status === "running" || status === "streaming" ? (
          <Shimmer className="flex items-center gap-2 text-sm">
            <span>{label}</span>
            {showPathBadge ? <TaskItemFile>{formatToolPathLabel(String(block.tool.path || ""))}</TaskItemFile> : null}
            {block.tool.detail ? <TaskItemFile>{block.tool.detail}</TaskItemFile> : null}
          </Shimmer>
        ) : (
          <>
            <span>{label}</span>
            {showPathBadge ? <TaskItemFile>{formatToolPathLabel(String(block.tool.path || ""))}</TaskItemFile> : null}
            {block.tool.detail ? <TaskItemFile>{block.tool.detail}</TaskItemFile> : null}
          </>
        )}
      </TaskItem>
    </Task>
  );
}

function renderApprovalBlock(
  block: ChatApprovalRequestBlock,
  onApprovalAction?: (decision: "approve" | "reject") => void,
  isLoading?: boolean,
) {
  return (
    <div key={block.id} className="space-y-3">
      <MessageResponse>{block.text}</MessageResponse>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          onClick={() => onApprovalAction?.("approve")}
          disabled={!onApprovalAction || isLoading}
          className="min-w-[96px]"
        >
          Approve
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => onApprovalAction?.("reject")}
          disabled={!onApprovalAction || isLoading}
          className="min-w-[96px]"
        >
          Reject
        </Button>
      </div>
    </div>
  );
}

export function AssistantResponseTimeline({
  blocks,
  onApprovalAction,
  isLoading = false,
}: AssistantResponseTimelineProps) {
  const renderedBlocks = useMemo(() => {
    const items: JSX.Element[] = [];
    let index = 0;

    while (index < blocks.length) {
      const block = blocks[index];
      if (block.kind === "tool_call" && isExplorationToolName(String(block.tool.toolName || ""))) {
        const explorationStreak: ChatToolCallBlock[] = [];
        while (index < blocks.length) {
          const candidate = blocks[index];
          if (candidate.kind !== "tool_call" || !isExplorationToolName(String(candidate.tool.toolName || ""))) {
            break;
          }
          explorationStreak.push(candidate);
          index += 1;
        }

        const readItems = explorationStreak.filter((entry) => isReadToolName(String(entry.tool.toolName || "")));
        const searchItems = explorationStreak.filter((entry) => isSearchToolName(String(entry.tool.toolName || "")));
        const headerParts: string[] = [];
        if (readItems.length > 0) {
          headerParts.push(`${readItems.length} ${readItems.length === 1 ? "file" : "files"}`);
        }
        if (searchItems.length > 0) {
          headerParts.push(`${searchItems.length} ${searchItems.length === 1 ? "search" : "searches"}`);
        }
        const headerText = `Exploring ${headerParts.join(", ") || "workspace"}`;
        const keepShimmer = explorationStreak.some((entry) => entry.status === "running" || entry.status === "streaming");

        items.push(
          <Task defaultOpen={false} key={`explore-${explorationStreak[0].id}`} className="w-full">
            <TaskTrigger asChild title={headerText}>
              <button
                type="button"
                className="group flex w-full items-center justify-between gap-2 rounded-md px-0 py-0.5 text-left text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {keepShimmer ? (
                  <Shimmer className="text-sm">{headerText}</Shimmer>
                ) : (
                  <span className="text-sm">{headerText}</span>
                )}
              </button>
            </TaskTrigger>
            <TaskContent className="mt-1">
              {explorationStreak.map((entry) => {
                const isRead = isReadToolName(String(entry.tool.toolName || ""));
                const readPath = isRead ? formatToolReadPath(String(entry.tool.path || "")) : "";
                const searchPath = String(entry.tool.path || "").trim();
                const label = isRead
                  ? (readPath ? `Reading file ${readPath}` : "Reading file")
                  : (entry.tool.detail
                    ? `Searching code ${entry.tool.detail}`
                    : searchPath
                      ? `Searching code ${formatToolPathLabel(searchPath)}`
                      : entry.tool.title);
                return (
                  <TaskItem
                    key={entry.id}
                    className={cn(
                      "flex items-center gap-2 text-sm",
                      entry.status === "error" ? "text-destructive" : "text-muted-foreground",
                    )}
                  >
                    {entry.status === "running" || entry.status === "streaming" ? (
                      <Shimmer className="text-sm">{label}</Shimmer>
                    ) : (
                      <span>{label}</span>
                    )}
                  </TaskItem>
                );
              })}
            </TaskContent>
          </Task>,
        );
        continue;
      }

      if (block.kind === "tool_call") {
        items.push(renderToolRow(block));
        index += 1;
        continue;
      }

      if (block.kind === "assistant_text") {
        items.push(<MessageResponse key={block.id}>{block.text}</MessageResponse>);
        index += 1;
        continue;
      }

      if (block.kind === "reasoning_note") {
        items.push(
          <div key={block.id} className="text-sm text-muted-foreground">
            {block.status === "running" || block.status === "streaming" ? (
              <Shimmer className="text-sm">{block.description || block.label}</Shimmer>
            ) : (
              <span>{block.description || block.label}</span>
            )}
          </div>,
        );
        index += 1;
        continue;
      }

      if (block.kind === "approval_request") {
        items.push(renderApprovalBlock(block, onApprovalAction, isLoading));
        index += 1;
        continue;
      }

      if (block.kind === "error") {
        items.push(
          <div key={block.id} className="text-sm text-destructive">
            {block.text}
          </div>,
        );
        index += 1;
        continue;
      }

      if (block.kind === "artifact" || block.kind === "user_message") {
        items.push(
          <MessageResponse key={block.id}>
            {"text" in block ? block.text : ""}
          </MessageResponse>,
        );
        index += 1;
        continue;
      }

      index += 1;
    }

    return items;
  }, [blocks, isLoading, onApprovalAction]);

  return (
    <div className="space-y-3">
      {renderedBlocks.map((item, index) => (
        <Fragment key={index}>{item}</Fragment>
      ))}
    </div>
  );
}
