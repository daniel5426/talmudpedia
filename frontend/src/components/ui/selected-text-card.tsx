"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { XIcon, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";

export interface SelectedTextCardProps {
  text: string;
  sourceRef?: string;
  onRemove: () => void;
  className?: string;
}

export function SelectedTextCard({
  text,
  sourceRef,
  onRemove,
  className,
}: SelectedTextCardProps) {
  // Truncate text for display
  const displayText = text.length > 50 ? text.substring(0, 50) + "..." : text;

  return (
    <HoverCard>
      <HoverCardTrigger asChild>
        <div
          className={cn(
            "group relative flex h-8 bg-primary-soft cursor-default select-none items-center gap-1.5 rounded-md border border-border px-1.5 font-medium text-sm transition-all hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
            className
          )}
        >
          <div className="relative size-5 shrink-0">
            <div className="absolute inset-0 flex size-5 items-center justify-center overflow-hidden rounded bg-background transition-opacity group-hover:opacity-0">
              <div className="flex size-5 items-center justify-center text-muted-foreground">
                <FileText className="size-3" />
              </div>
            </div>
            <Button
              aria-label="Remove selected text"
              className="absolute inset-0 size-5 cursor-pointer rounded p-0 opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 [&>svg]:size-2.5"
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
              type="button"
              variant="ghost"
            >
              <XIcon />
              <span className="sr-only">Remove</span>
            </Button>
          </div>

          <span className="flex-1 truncate">{displayText}</span>
        </div>
      </HoverCardTrigger>
      <HoverCardContent className="w-auto max-w-md p-3" dir="rtl">
        <div className="space-y-2">
          {sourceRef && (
            <p className="text-xs text-muted-foreground font-semibold">
              {sourceRef}
            </p>
          )}
          <p className="text-sm whitespace-pre-wrap break-words max-h-96 overflow-y-auto">
            {text}
          </p>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
