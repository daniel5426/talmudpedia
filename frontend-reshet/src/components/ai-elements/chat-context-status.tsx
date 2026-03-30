"use client";

import type { ContextWindow } from "@/services/context-window";

import {
  Context,
  ContextContent,
  ContextContentBody,
  ContextContentFooter,
  ContextContentHeader,
  ContextTrigger,
} from "@/components/ai-elements/context";
import { cn } from "@/lib/utils";

type ChatContextStatusProps = {
  contextStatus?: ContextWindow | null;
  className?: string;
  triggerClassName?: string;
};

function compactNumber(value: number | null | undefined): string {
  if (value == null) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", { notation: "compact" }).format(value);
}

function percent(value: number | null | undefined): string {
  if (value == null) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

function StatusRow({
  label,
  value,
}: {
  label: string;
  value: number | null | undefined;
}) {
  if (value == null || value <= 0) {
    return null;
  }
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span>{compactNumber(value)}</span>
    </div>
  );
}

export function ChatContextStatus({
  contextStatus,
  className,
  triggerClassName,
}: ChatContextStatusProps) {
  const maxTokens = Number(contextStatus?.max_tokens || 0);
  if (!contextStatus || !Number.isFinite(maxTokens) || maxTokens <= 0) {
    return null;
  }

  const contextUsedTokens = Number(contextStatus.input_tokens ?? 0);
  const remainingTokens = Math.max(0, Number(contextStatus.remaining_tokens ?? (maxTokens - contextUsedTokens)));
  const usageRatio = contextStatus.usage_ratio ?? (contextUsedTokens / maxTokens);

  return (
    <Context
      maxTokens={maxTokens}
      usedTokens={Math.min(contextUsedTokens, maxTokens)}
    >
      <ContextTrigger
        className={cn(
          "h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground",
          className,
          triggerClassName,
        )}
      />
      <ContextContent className="w-72">
        <ContextContentHeader />
        <ContextContentBody className="space-y-2">
          <StatusRow
            label={contextStatus.source === "exact" ? "Input" : "Estimated input"}
            value={contextStatus.input_tokens}
          />
          <StatusRow label="Remaining" value={contextStatus.remaining_tokens} />
        </ContextContentBody>
        <ContextContentFooter>
          <span className="text-muted-foreground">Context window</span>
          <span>
            {compactNumber(remainingTokens)} left
            <span className="ml-2 text-muted-foreground">
              • {percent(usageRatio)}
            </span>
          </span>
        </ContextContentFooter>
      </ContextContent>
    </Context>
  );
}
