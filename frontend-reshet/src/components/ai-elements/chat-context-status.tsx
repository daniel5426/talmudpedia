"use client";

import type { ContextStatus } from "@/services/context-status";

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
  contextStatus?: ContextStatus | null;
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

  const actualUsage = contextStatus.actual_usage || null;
  const contextUsedTokens = Number(
    contextStatus.estimated_total_tokens
      ?? contextStatus.estimated_input_tokens
      ?? actualUsage?.total_tokens
      ?? 0,
  );
  const remainingTokens = Math.max(0, maxTokens - contextUsedTokens);
  const usageRatio = contextStatus.estimated_usage_ratio ?? (contextUsedTokens / maxTokens);

  return (
    <Context
      maxTokens={maxTokens}
      usedTokens={Math.min(contextUsedTokens, maxTokens)}
      className={className}
    >
      <ContextTrigger
        className={cn(
          "h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground",
          triggerClassName,
        )}
      />
      <ContextContent className="w-72">
        <ContextContentHeader />
        <ContextContentBody className="space-y-2">
          <StatusRow
            label={contextStatus.source === "estimated_plus_actual" ? "Input" : "Estimated input"}
            value={actualUsage?.input_tokens ?? contextStatus.estimated_input_tokens}
          />
          <StatusRow
            label={contextStatus.source === "estimated_plus_actual" ? "Output" : "Reserved output"}
            value={contextStatus.source === "estimated_plus_actual"
              ? actualUsage?.output_tokens
              : contextStatus.reserved_output_tokens}
          />
          <StatusRow label="Reasoning" value={actualUsage?.reasoning_tokens} />
          <StatusRow label="Cache" value={actualUsage?.cached_input_tokens} />
        </ContextContentBody>
        <ContextContentFooter>
          <span className="text-muted-foreground">Context estimate</span>
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
