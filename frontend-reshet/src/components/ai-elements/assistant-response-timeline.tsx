"use client";

import Link from "next/link";
import { Fragment, useMemo, useState } from "react";
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
import { ArrowUpRight, ChevronDown, ChevronRight } from "lucide-react";
import { MessageResponse } from "./message";
import { Shimmer } from "./shimmer";
import { Task, TaskContent, TaskItem, TaskItemFile, TaskTrigger } from "./task";

type AssistantResponseTimelineProps = {
  animateOnMount?: boolean;
  blocks: ChatRenderBlock[];
  getToolChildCount?: (block: ChatToolCallBlock) => number;
  getToolHref?: (block: ChatToolCallBlock) => string | null;
  renderToolSubthread?: (block: ChatToolCallBlock) => React.ReactNode;
  onApprovalAction?: (decision: "approve" | "reject") => void;
  isLoading?: boolean;
};

function renderToolLink(toolHref: string | null | undefined, label: string) {
  if (!toolHref) return null;
  return (
    <Link
      href={toolHref}
      className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-sm text-muted-foreground/80 transition-colors hover:bg-muted hover:text-foreground focus-visible:bg-muted focus-visible:text-foreground"
      aria-label={`Open thread for ${label}`}
      title="Open thread"
    >
      <ArrowUpRight className="h-3.5 w-3.5" />
    </Link>
  );
}

function renderToolRow(
  block: ChatToolCallBlock,
  isActive = false,
  toolHref?: string | null,
  options?: {
    childCount?: number;
    isSubthreadExpanded?: boolean;
    onToggleSubthread?: () => void;
    subthreadContent?: React.ReactNode;
  },
) {
  const status = block.status;
  const showPathBadge = block.tool.path && !isEditToolName(String(block.tool.toolName || ""));
  const label = block.tool.title || block.tool.displayName || block.tool.summary || block.tool.toolName;
  const summary = String(block.tool.summary || "").trim();
  const hasSummary = Boolean(summary) && summary.toLowerCase() !== String(label || "").trim().toLowerCase();
  const childCount = Math.max(0, options?.childCount || 0);
  const hasSubthreads = childCount > 0 && Boolean(options?.onToggleSubthread);
  const labelContent = isActive ? (
    <Shimmer className="flex items-center gap-2 text-sm">
      <span>{label}</span>
    </Shimmer>
  ) : (
    <span>{label}</span>
  );
  const metaContent = (
    <>
      {showPathBadge ? <TaskItemFile>{formatToolPathLabel(String(block.tool.path || ""))}</TaskItemFile> : null}
      {block.tool.detail ? <TaskItemFile>{block.tool.detail}</TaskItemFile> : null}
    </>
  );
  const subthreadToggle = hasSubthreads ? (
    <button
      type="button"
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        options?.onToggleSubthread?.();
      }}
      className="inline-flex items-center gap-0.5 rounded-md text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:text-foreground"
      aria-expanded={Boolean(options?.isSubthreadExpanded)}
      aria-label={`Toggle ${childCount} subthread${childCount === 1 ? "" : "s"}`}
    >
      <span>{`+${childCount}`}</span>
      {options?.isSubthreadExpanded ? (
        <ChevronDown className="h-3 w-3 opacity-100" />
      ) : (
        <ChevronRight className="h-3 w-3 opacity-0 transition-opacity group-hover/tool-row:opacity-100 group-focus-within/tool-row:opacity-100" />
      )}
    </button>
  ) : null;
  const subthreadContent = options?.isSubthreadExpanded && options?.subthreadContent ? (
    <div className="mt-3">{options.subthreadContent}</div>
  ) : null;

  if (!hasSummary) {
    return (
      <div key={block.id} className="w-full">
        <Task defaultOpen className="w-full">
        <TaskItem
          className={cn(
            "group flex items-center gap-1.5 text-sm",
            status === "error" ? "text-destructive" : "text-muted-foreground",
          )}
        >
            {labelContent}
            {subthreadToggle}
            {renderToolLink(toolHref, String(label))}
            {metaContent}
          </TaskItem>
        </Task>
        {subthreadContent}
      </div>
    );
  }

  return (
    <div key={block.id} className="w-full">
      <Task defaultOpen={false} className="w-full">
        <div
          className={cn(
            "group flex items-center gap-1.5",
            status === "error" ? "text-destructive" : "text-muted-foreground",
          )}
        >
          <TaskTrigger asChild title={label}>
            <button
              type="button"
              className="flex min-w-0 items-center rounded-md px-0 py-0.5 text-left text-sm transition-colors hover:text-foreground"
            >
              {labelContent}
            </button>
          </TaskTrigger>
          {subthreadToggle}
          {renderToolLink(toolHref, String(label))}
          {metaContent}
        </div>
        <TaskContent className="mt-1">
          <div className="text-sm text-muted-foreground">{summary}</div>
        </TaskContent>
      </Task>
      {subthreadContent}
    </div>
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
  getToolChildCount,
  getToolHref,
  renderToolSubthread,
  onApprovalAction,
  isLoading = false,
}: AssistantResponseTimelineProps) {
  const [expandedToolSubthreads, setExpandedToolSubthreads] = useState<Record<string, boolean>>({});
  const renderedBlocks = useMemo(() => {
    const items: React.ReactNode[] = [];
    let index = 0;
    const lastToolCallId = [...blocks]
      .reverse()
      .find((entry): entry is ChatToolCallBlock => entry.kind === "tool_call")
      ?.id;
    const activeToolCallId = [...blocks]
      .reverse()
      .find(
        (entry): entry is ChatToolCallBlock =>
          entry.kind === "tool_call" && (entry.status === "running" || entry.status === "streaming"),
      )?.id || (isLoading ? lastToolCallId : undefined);

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
        const keepShimmer = explorationStreak.some((entry) => entry.id === activeToolCallId);

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
                    {entry.id === activeToolCallId ? (
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
        const childCount = Math.max(0, getToolChildCount?.(block) || 0);
        const isSubthreadExpanded = Boolean(expandedToolSubthreads[block.id]);
        items.push(
          renderToolRow(block, block.id === activeToolCallId, getToolHref?.(block) || null, {
            childCount,
            isSubthreadExpanded,
            onToggleSubthread:
              childCount > 0
                ? () =>
                    setExpandedToolSubthreads((current) => ({
                      ...current,
                      [block.id]: !current[block.id],
                    }))
                : undefined,
            subthreadContent: isSubthreadExpanded ? renderToolSubthread?.(block) : null,
          }),
        );
        index += 1;
        continue;
      }

      if (block.kind === "assistant_text") {
        items.push(
          <MessageResponse
            key={block.id}
            streaming={block.status === "running" || block.status === "streaming"}
          >
            {block.text}
          </MessageResponse>,
        );
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
  }, [blocks, expandedToolSubthreads, getToolChildCount, getToolHref, isLoading, onApprovalAction, renderToolSubthread]);

  return (
    <div className="space-y-3">
      {renderedBlocks.map((item, index) => (
        <Fragment key={index}>{item}</Fragment>
      ))}
    </div>
  );
}
