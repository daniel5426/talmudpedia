"use client";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronDown, Clock } from "lucide-react";
import { AgentChatHistoryItem } from "@/hooks/useAgentThreadHistory";

interface ExecutionHistoryDropdownProps {
  historyItems: AgentChatHistoryItem[];
  loading?: boolean;
  label?: string | null;
  ariaLabel?: string;
  showChevron?: boolean;
  align?: "start" | "end" | "center";
  onSelectHistory: (item: AgentChatHistoryItem) => void;
  onStartNewChat?: () => void;
  className?: string;
  contentClassName?: string;
}

export function ExecutionHistoryDropdown({
  historyItems,
  loading = false,
  label = "History",
  ariaLabel = "History",
  showChevron = false,
  align = "start",
  onSelectHistory,
  onStartNewChat,
  className,
  contentClassName,
}: ExecutionHistoryDropdownProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={ariaLabel}
          className={className || "inline-flex items-center gap-1.5 rounded-md border bg-background/90 px-2.5 py-1 text-xs font-medium text-foreground backdrop-blur hover:bg-muted transition-colors"}
        >
          <Clock className="h-3.5 w-3.5" />
          {label ? <span>{label}</span> : null}
          {showChevron ? <ChevronDown className="h-3 w-3 opacity-70" /> : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} className={contentClassName || "min-w-[220px]"}>
        {loading ? (
          <DropdownMenuItem disabled className="text-muted-foreground">
            Loading...
          </DropdownMenuItem>
        ) : historyItems.length === 0 ? (
          <DropdownMenuItem disabled className="text-muted-foreground">
            No threads yet
          </DropdownMenuItem>
        ) : (
          historyItems.map((item) => (
            <DropdownMenuItem
              key={item.threadId || item.id}
              onClick={() => onSelectHistory(item)}
              className="flex flex-col items-start gap-1"
            >
              <span className="text-xs font-medium text-foreground">{item.title || "Thread"}</span>
              <span className="text-[11px] text-muted-foreground">
                {item.timestamp ? new Date(item.timestamp).toLocaleString() : "Recent"}
              </span>
            </DropdownMenuItem>
          ))
        )}
        {onStartNewChat ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onStartNewChat}>Start new chat</DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
